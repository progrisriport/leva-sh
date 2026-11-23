"""leva.sources: origin mapping, entry-name rule and ExecutableScanner over tmp trees."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from leva.model import Origin
from leva.sources import DEFAULT_BIN_DIRS, Executable, ExecutableScanner, origin_for
from leva.sources._names import is_entry_name

NO_BREAK_SPACE = chr(0xA0)


def make_file(directory: Path, name: str, mode: int = 0o755) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(mode)
    return path


def names(scanner: ExecutableScanner) -> list[str]:
    return [exe.name for exe in scanner.scan()]


@pytest.mark.parametrize(
    ("path", "origin"),
    [
        ("/opt/homebrew/bin/git", Origin.HOMEBREW),
        ("/usr/local/bin/x", Origin.HOMEBREW),
        ("/usr/local", Origin.HOMEBREW),
        ("/usr/localfoo/bin/x", Origin.MACOS),
        ("/usr/bin/ls", Origin.MACOS),
        ("relative/x", Origin.MACOS),
        ("/opt/homebrewx/y", Origin.MACOS),
    ],
)
def test_origin_for(path: str, origin: Origin) -> None:
    assert origin_for(Path(path)) is origin


@pytest.mark.parametrize("name", ["ls", "[", "[[", ".", ":"])
def test_is_entry_name_accepts(name: str) -> None:
    assert is_entry_name(name)


@pytest.mark.parametrize("name", ["", "a b", f"a{NO_BREAK_SPACE}b", "a\tb", "a\nb"])
def test_is_entry_name_rejects(name: str) -> None:
    assert not is_entry_name(name)


def test_default_bin_dirs_follow_d004_order() -> None:
    assert [str(path) for path in DEFAULT_BIN_DIRS] == [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]


def test_scan_yields_executable_file_with_listed_path(tmp_path: Path) -> None:
    exe = make_file(tmp_path / "bin", "tool")
    assert list(ExecutableScanner([tmp_path / "bin"]).scan()) == [
        Executable("tool", exe, Origin.MACOS)
    ]


def test_scan_skips_non_executable_and_directories(tmp_path: Path) -> None:
    directory = tmp_path / "bin"
    make_file(directory, "plain", 0o644)
    (directory / "subdir").mkdir(mode=0o755)
    make_file(directory, "ok")
    assert names(ExecutableScanner([directory])) == ["ok"]


def test_scan_keeps_symlink_path_unresolved(tmp_path: Path) -> None:
    directory = tmp_path / "bin"
    target = make_file(tmp_path / "real", "real-tool")
    link = directory / "alias"
    directory.mkdir()
    link.symlink_to(target)
    assert list(ExecutableScanner([directory]).scan()) == [Executable("alias", link, Origin.MACOS)]


def test_scan_skips_dir_broken_and_circular_symlinks(tmp_path: Path) -> None:
    directory = tmp_path / "bin"
    directory.mkdir()
    (tmp_path / "somedir").mkdir()
    (directory / "to-dir").symlink_to(tmp_path / "somedir")
    (directory / "broken").symlink_to(tmp_path / "nowhere")
    (directory / "a").symlink_to("b")
    (directory / "b").symlink_to("a")
    assert names(ExecutableScanner([directory])) == []


def test_scan_ignores_missing_dir_and_file_dir(tmp_path: Path) -> None:
    not_a_dir = make_file(tmp_path, "file")
    good = tmp_path / "good"
    make_file(good, "ok")
    scanner = ExecutableScanner([tmp_path / "missing", not_a_dir, good])
    assert names(scanner) == ["ok"]


def test_scan_sorts_by_name_then_dir_index(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    # No two names differ only by case: the default macOS file system is case-insensitive.
    for name in ("c", "[", "A", "b"):
        make_file(second, name)
    make_file(first, "b")
    result = list(ExecutableScanner([first, second]).scan())
    assert [(exe.name, exe.path.parent.name) for exe in result] == [
        ("A", "second"),
        ("[", "second"),
        ("b", "first"),
        ("b", "second"),
        ("c", "second"),
    ]


def test_scan_dedups_repeated_dirs(tmp_path: Path) -> None:
    directory = tmp_path / "bin"
    make_file(directory, "tool")
    assert names(ExecutableScanner([directory, tmp_path / "other", directory])) == ["tool"]


def test_scan_skips_names_with_whitespace(tmp_path: Path) -> None:
    directory = tmp_path / "bin"
    make_file(directory, "has space")
    make_file(directory, "fine")
    assert names(ExecutableScanner([directory])) == ["fine"]


def test_scan_origin_outside_homebrew_prefixes_is_macos(tmp_path: Path) -> None:
    make_file(tmp_path / "bin", "tool")
    assert {exe.origin for exe in ExecutableScanner([tmp_path / "bin"]).scan()} == {Origin.MACOS}


def test_scan_rescans_on_every_call(tmp_path: Path) -> None:
    directory = tmp_path / "bin"
    make_file(directory, "one")
    scanner = ExecutableScanner([directory])
    before = list(scanner.scan())
    assert before == list(scanner.scan())
    make_file(directory, "two")
    assert names(scanner) == ["one", "two"]


@contextmanager
def unreadable(directory: Path) -> Iterator[None]:
    directory.chmod(0o000)
    try:
        yield
    finally:
        directory.chmod(0o755)


def test_scan_skips_symlink_whose_target_cannot_be_inspected(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("chmod 0o000 does not block root")
    locked = tmp_path / "locked"
    target = make_file(locked, "tool")
    directory = tmp_path / "bin"
    directory.mkdir()
    (directory / "tool").symlink_to(target)
    make_file(directory, "ok")
    with unreadable(locked):
        assert names(ExecutableScanner([directory])) == ["ok"]


def test_scan_skips_unreadable_dir(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("chmod 0o000 does not block root")
    locked = tmp_path / "locked"
    make_file(locked, "hidden")
    good = tmp_path / "good"
    make_file(good, "ok")
    with unreadable(locked):
        assert names(ExecutableScanner([locked, good])) == ["ok"]
