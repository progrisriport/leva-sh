"""Test harness: clean environment, Hypothesis profile, directory markers, fake_bin, no network."""

from __future__ import annotations

import os
import shlex
import socket
import subprocess
import tomllib
from pathlib import Path

import pytest
from hypothesis import settings
from pytest_socket import SocketBlockedError

from tests.support.fake_bin import fake_bin

REPO = Path(__file__).resolve().parents[2]
CONFTEST = REPO / "tests" / "conftest.py"
PYPROJECT = REPO / "pyproject.toml"


# clean_env ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TZ", "UTC"),
        ("LC_ALL", "en_US.UTF-8"),
        ("LANG", "en_US.UTF-8"),
        ("LANGUAGE", "en"),
        ("MANWIDTH", "80"),
        ("COLUMNS", "120"),
    ],
)
def test_clean_env_pins_locale_and_terminal_variables(name: str, value: str) -> None:
    assert os.environ[name] == value


def test_clean_env_points_leva_home_at_the_test_tmp_dir(tmp_path: Path) -> None:
    assert os.environ["LEVA_HOME"] == str(tmp_path)


def test_clean_env_isolates_home_inside_the_test_tmp_dir(tmp_path: Path) -> None:
    home = tmp_path / "home"

    assert os.environ["HOME"] == str(home)
    assert home.is_dir()
    assert Path.home() == home
    assert Path("~").expanduser() == home


# Hypothesis profile ---------------------------------------------------------------------------


def test_hypothesis_profile_is_deterministic_without_deadline() -> None:
    current = settings()

    assert current.derandomize is True
    assert current.deadline is None
    assert current.print_blob is True


# directory markers ----------------------------------------------------------------------------

MARKER_LAYOUT = {
    "integration/test_in_integration.py": ["integration"],
    "integration/nested/test_in_nested_integration.py": ["integration"],
    "tui/test_in_tui.py": ["tui"],
    "live/test_in_live.py": ["macos_live"],
    "unit/test_in_unit.py": [],
    "test_at_top_level.py": [],
}

MARKER_PROBE = """
def test_markers(request):
    assert sorted(mark.name for mark in request.node.iter_markers()) == {expected!r}
"""

# Real pytest options that cannot carry over: the throwaway tree has no tests/ dir, and an
# inner per-test SIGALRM would cancel the outer test's timeout.
INNER_EXCLUDED_OPTIONS = frozenset({"testpaths", "timeout"})
# The snapshot plugin keeps one temp dir per process, which an in-process inner session deletes.
INNER_ARGS = ("-p", "no:cacheprovider", "-p", "no:textual-snapshot")


def ini_entry(key: str, value: object) -> str:
    if key == "addopts" and isinstance(value, list):
        return f"addopts = {shlex.join(value)}"
    if isinstance(value, list):
        return f"{key} =" + "".join(f"\n    {item}" for item in value)
    if isinstance(value, bool):
        return f"{key} = {str(value).lower()}"
    return f"{key} = {value}"


@pytest.fixture
def marker_tree(pytester: pytest.Pytester) -> pytest.Pytester:
    """A throwaway test tree run with the real conftest and the real pytest options."""
    options = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["pytest"]
    entries = [
        ini_entry(key, value)
        for key, value in options["ini_options"].items()
        if key not in INNER_EXCLUDED_OPTIONS
    ]
    pytester.makeini("[pytest]\n" + "\n".join(entries) + "\n")
    pytester.makeconftest(CONFTEST.read_text(encoding="utf-8"))
    for relative, expected in MARKER_LAYOUT.items():
        path = pytester.path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MARKER_PROBE.format(expected=expected), encoding="utf-8")
    return pytester


def test_directory_markers_are_applied_and_live_tests_are_excluded_by_default(
    marker_tree: pytest.Pytester,
) -> None:
    result = marker_tree.runpytest(*INNER_ARGS)

    result.assert_outcomes(passed=5, deselected=1)


def test_live_directory_tests_are_selected_by_the_macos_live_marker(
    marker_tree: pytest.Pytester,
) -> None:
    result = marker_tree.runpytest(*INNER_ARGS, "-m", "macos_live")

    result.assert_outcomes(passed=1, deselected=5)


# fake_bin -------------------------------------------------------------------------------------


def test_fake_bin_writes_an_executable_sh_script(tmp_path: Path) -> None:
    path = fake_bin(tmp_path, "greet", 'echo "hello $1"')

    assert path == tmp_path / "greet"
    assert path.read_text(encoding="utf-8") == '#!/bin/sh\necho "hello $1"\n'
    assert os.access(path, os.X_OK)
    assert path.stat().st_mode & 0o777 == 0o755


def test_fake_bin_script_runs_and_propagates_output_and_exit_status(tmp_path: Path) -> None:
    path = fake_bin(tmp_path, "tool", 'echo "out:$1"\necho "err:$2" >&2\nexit 3\n')

    completed = subprocess.run(
        [str(path), "a", "b"], capture_output=True, text=True, check=False, timeout=10
    )

    assert completed.returncode == 3
    assert completed.stdout == "out:a\n"
    assert completed.stderr == "err:b\n"


def test_fake_bin_creates_missing_directories(tmp_path: Path) -> None:
    path = fake_bin(tmp_path / "a" / "bin", "tool", "exit 0")

    assert path.parent.is_dir()
    assert os.access(path, os.X_OK)


def test_fake_bin_replaces_an_existing_script(tmp_path: Path) -> None:
    fake_bin(tmp_path, "tool", "exit 1")
    path = fake_bin(tmp_path, "tool", "exit 0")

    completed = subprocess.run([str(path)], check=False, timeout=10)

    assert completed.returncode == 0


def test_fake_bin_accepts_shell_special_names(tmp_path: Path) -> None:
    path = fake_bin(tmp_path, "[", "exit 0")

    assert path.name == "["
    assert os.access(path, os.X_OK)


@pytest.mark.parametrize("name", ["", ".", "..", "sub/tool", "/abs"])
def test_fake_bin_rejects_names_that_are_not_bare_file_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="bare file name"):
        fake_bin(tmp_path, name, "exit 0")

    assert list(tmp_path.iterdir()) == [tmp_path / "home"]


# network guard --------------------------------------------------------------------------------


def test_network_sockets_are_blocked() -> None:
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_inet_connect_is_blocked_before_any_traffic() -> None:
    with pytest.raises(SocketBlockedError):
        socket.create_connection(("127.0.0.1", 9), timeout=1)


def test_unix_socketpair_is_allowed_for_event_loops() -> None:
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b"ping")

        assert right.recv(4) == b"ping"
