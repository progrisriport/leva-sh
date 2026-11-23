"""leva.sources.ProbeRunner: allowlist, child env, cwd/HOME, timeout, output cap, failures."""

from __future__ import annotations

import select
from collections.abc import Mapping
from pathlib import Path

import pytest

from leva.model import IngestError
from leva.sources import ProbeRunner
from tests.support.fake_bin import fake_bin

BASE_ENV = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "LC_ALL": "en_US.UTF-8",
    "LANG": "en_US.UTF-8",
    "LANGUAGE": "en",
    "NO_COLOR": "1",
    "TERM": "dumb",
    "HOMEBREW_NO_AUTO_UPDATE": "1",
    "HOMEBREW_NO_ANALYTICS": "1",
    "HOMEBREW_NO_ENV_HINTS": "1",
}
SHELL_VARS = {"PWD", "SHLVL", "_", "OLDPWD"}


def probe(
    tmp_path: Path,
    script: str,
    *args: str,
    timeout: float = 5.0,
    max_bytes: int = 262_144,
) -> ProbeRunner:
    """Return a runner whose allowlist maps `tool` to a fake script run with `args`."""
    path = fake_bin(tmp_path / "bin", "tool", script)
    return ProbeRunner({"tool": (str(path), *args)}, timeout=timeout, max_bytes=max_bytes)


def test_stdout_is_returned_unstripped(tmp_path: Path) -> None:
    assert probe(tmp_path, 'echo "usage: tool"').run("tool") == "usage: tool\n"


def test_stderr_used_when_stdout_empty_and_exit_status_ignored(tmp_path: Path) -> None:
    runner = probe(tmp_path, 'echo "usage: tool" >&2; exit 1')
    assert runner.run("tool") == "usage: tool\n"


def test_stderr_used_when_stdout_blank(tmp_path: Path) -> None:
    runner = probe(tmp_path, 'echo "   "; echo "usage: tool" >&2')
    assert runner.run("tool") == "usage: tool\n"


def test_stdout_wins_over_stderr(tmp_path: Path) -> None:
    runner = probe(tmp_path, 'echo "out"; echo "err" >&2')
    assert runner.run("tool") == "out\n"


@pytest.mark.parametrize(
    "script",
    ["true", 'echo "  " ; echo "" >&2', 'echo "   "; echo "  " >&2; exit 3'],
)
def test_empty_output_raises(tmp_path: Path, script: str) -> None:
    with pytest.raises(IngestError, match=r"^probe output empty: tool$"):
        probe(tmp_path, script).run("tool")


def test_exit_255_with_stdout_returns_text(tmp_path: Path) -> None:
    assert probe(tmp_path, 'echo "usage: defaults"; exit 255').run("tool") == "usage: defaults\n"


def test_command_outside_allowlist_is_never_executed(tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    other = fake_bin(tmp_path / "bin", "other", f'/usr/bin/touch "{marker}"')
    runner = probe(tmp_path, f'/usr/bin/touch "{marker}"')
    for command in ("other", str(other), ""):
        with pytest.raises(IngestError, match=r"^probe not allowed: "):
            runner.run(command)
    assert not marker.exists()


def test_not_allowed_message_names_the_command(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match=r"^probe not allowed: other$"):
        probe(tmp_path, "true").run("other")


def test_argv_is_passed_through_in_order(tmp_path: Path) -> None:
    runner = probe(tmp_path, 'for a in "$@"; do echo "$a"; done', "--help", "two words", "-x")
    assert runner.run("tool").splitlines() == ["--help", "two words", "-x"]


def test_child_env_is_exactly_the_d009_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEVA_SENTINEL", "1")
    monkeypatch.setenv("SECRET_TOKEN", "x")
    runner = probe(tmp_path, "/usr/bin/env")
    env = dict(line.split("=", 1) for line in runner.run("tool").splitlines() if "=" in line)
    home = env.pop("HOME")
    for var in SHELL_VARS:
        env.pop(var, None)
    assert env == BASE_ENV
    assert Path(home).name == "home"


def test_cwd_and_home_are_one_throwaway_dir(tmp_path: Path) -> None:
    lines = probe(tmp_path, '/bin/pwd; echo "$HOME"').run("tool").splitlines()
    cwd, home = (Path(line).resolve() for line in lines)
    assert cwd == home
    assert home.name == "home"
    assert home.parent.name.startswith("leva-probe-")
    assert not home.parent.exists()


def test_temp_dir_removed_after_empty_output(tmp_path: Path) -> None:
    seen = tmp_path / "home.txt"
    with pytest.raises(IngestError, match=r"^probe output empty: tool$"):
        probe(tmp_path, f'echo "$HOME" > "{seen}"').run("tool")
    assert not Path(seen.read_text(encoding="utf-8").strip()).parent.exists()


def test_timeout_raises_and_returns_promptly(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match=r"^probe timed out: tool$"):
        probe(tmp_path, "exec /bin/sleep 30", timeout=0.3).run("tool")


def exits_within(pid: int, timeout: float) -> bool:
    """Return whether process `pid` is gone or exits within `timeout` seconds (kqueue)."""
    kq = select.kqueue()
    try:
        event = select.kevent(
            pid,
            filter=select.KQ_FILTER_PROC,
            flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
            fflags=select.KQ_NOTE_EXIT,
        )
        try:
            return bool(kq.control([event], 1, timeout))
        except ProcessLookupError:
            return True
    finally:
        kq.close()


def test_timeout_kills_process_group_and_removes_temp_dir(tmp_path: Path) -> None:
    # The script must write both files before the kill; 3 s leaves room for a slow first
    # exec under load and is still far below the 30 s sleeps.
    pid_file = tmp_path / "grandchild.pid"
    seen = tmp_path / "home.txt"
    script = f'echo "$HOME" > "{seen}"\n/bin/sleep 30 &\necho $! > "{pid_file}"\nexec /bin/sleep 30'
    with pytest.raises(IngestError, match=r"^probe timed out: tool$"):
        probe(tmp_path, script, timeout=3.0).run("tool")
    assert exits_within(int(pid_file.read_text(encoding="utf-8")), timeout=5.0)
    assert not Path(seen.read_text(encoding="utf-8").strip()).parent.exists()


def test_output_capped_at_default_max_bytes(tmp_path: Path) -> None:
    runner = probe(tmp_path, "/usr/bin/head -c 300000 /dev/zero | /usr/bin/tr '\\0' a")
    assert runner.run("tool") == "a" * 262_144


def test_output_capped_at_custom_max_bytes(tmp_path: Path) -> None:
    runner = probe(tmp_path, "/usr/bin/head -c 300 /dev/zero | /usr/bin/tr '\\0' a", max_bytes=10)
    assert runner.run("tool") == "a" * 10


def test_multibyte_char_cut_by_cap_becomes_replacement(tmp_path: Path) -> None:
    runner = probe(tmp_path, "printf 'é%.0s' 1 2 3 4 5", max_bytes=3)
    assert runner.run("tool") == "é�"


def test_cap_applies_to_stderr_text_too(tmp_path: Path) -> None:
    runner = probe(
        tmp_path, "/usr/bin/head -c 300 /dev/zero | /usr/bin/tr '\\0' b >&2", max_bytes=4
    )
    assert runner.run("tool") == "bbbb"


@pytest.mark.parametrize("mode", [None, 0o644])
def test_spawn_failure_raises_probe_failed(tmp_path: Path, mode: int | None) -> None:
    path = tmp_path / "bin" / "tool"
    if mode is not None:
        path = fake_bin(tmp_path / "bin", "tool", "true")
        path.chmod(mode)
    with pytest.raises(IngestError, match=r"^probe failed: tool$") as info:
        ProbeRunner({"tool": (str(path),)}).run("tool")
    assert isinstance(info.value.__cause__, OSError)


def test_stdin_is_devnull(tmp_path: Path) -> None:
    runner = probe(tmp_path, "/bin/cat; echo x >&2")
    assert runner.run("tool") == "x\n"


@pytest.mark.parametrize(
    ("allowlist", "timeout", "max_bytes", "message"),
    [
        ({"tool": ("/bin/echo",)}, 0, 10, r"^probe timeout must be positive"),
        ({"tool": ("/bin/echo",)}, -1, 10, r"^probe timeout must be positive"),
        ({"tool": ("/bin/echo",)}, 5, 0, r"^probe max_bytes must be positive"),
        ({"tool": ()}, 5, 10, r"^probe 'tool': argv\[0\] must be an absolute path"),
        ({"tool": ("tool",)}, 5, 10, r"^probe 'tool': argv\[0\] must be an absolute path"),
        (
            {"ok": ("/bin/echo",), "bad": ("./echo", "x")},
            5,
            10,
            r"^probe 'bad': argv\[0\] must be an absolute path",
        ),
    ],
)
def test_invalid_construction_raises(
    allowlist: Mapping[str, tuple[str, ...]], timeout: float, max_bytes: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ProbeRunner(allowlist, timeout=timeout, max_bytes=max_bytes)


def test_allowlist_is_copied_at_construction(tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    script = fake_bin(tmp_path / "bin", "tool", f'/usr/bin/touch "{marker}"; echo hi')
    allowlist = {"tool": (str(script),)}
    runner = ProbeRunner(allowlist)
    allowlist["tool"] = ("/bin/echo", "changed")
    allowlist["new"] = (str(script),)
    assert runner.run("tool") == "hi\n"
    with pytest.raises(IngestError, match="probe not allowed: new"):
        runner.run("new")
