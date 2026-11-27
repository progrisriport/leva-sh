"""leva.sources: man dir discovery, manpath runner and ManPageLocator over tmp trees."""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterable
from pathlib import Path

import pytest

from leva.model import IngestError, Origin
from leva.sources import ManFile, ManPageLocator, discover_man_dirs, run_manpath
from tests.support.fake_bin import fake_bin

FALLBACKS = [Path("/opt/homebrew/share/man"), Path("/usr/local/share/man")]
MANPATH_FAILED = "cannot list man directories: manpath failed"


def dirs(*paths: str) -> list[Path]:
    return [Path(path) for path in paths]


def test_discover_orders_manpath_then_fallbacks_then_extra() -> None:
    result = discover_man_dirs("/a/man:/b/man\n", [Path("/c")])
    assert result == (*dirs("/a/man", "/b/man"), *FALLBACKS, Path("/c"))


def test_discover_deduplicates_keeping_first_occurrence() -> None:
    result = discover_man_dirs(
        "/opt/homebrew/share/man:/usr/share/man/:/usr/share/man\n",
        dirs("/x", "/x", "/usr/share/man"),
    )
    assert result == (
        Path("/opt/homebrew/share/man"),
        Path("/usr/share/man"),
        Path("/usr/local/share/man"),
        Path("/x"),
    )


@pytest.mark.parametrize("output", ["", "\n", "   \n", "::", ":\n:"])
def test_discover_blank_output_gives_fallbacks_and_extra(output: str) -> None:
    assert discover_man_dirs(output, [Path("/c")]) == (*FALLBACKS, Path("/c"))


def test_discover_drops_relative_paths_from_every_source() -> None:
    result = discover_man_dirs("man:/a", [Path("rel/man"), Path("/c")])
    assert result == (Path("/a"), *FALLBACKS, Path("/c"))


def test_discover_keeps_missing_dirs(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert missing in discover_man_dirs(str(missing))


def manpath_printing(tmp_path: Path, text: str) -> str:
    return str(fake_bin(tmp_path / "bin", "manpath", f"printf '%s\\n' '{text}'"))


def test_run_manpath_returns_stdout_verbatim(tmp_path: Path) -> None:
    binary = manpath_printing(tmp_path, "/x/man:/y/man")
    assert run_manpath({}, binary=binary) == "/x/man:/y/man\n"


def child_env(tmp_path: Path, env: dict[str, str]) -> dict[str, str]:
    dump = tmp_path / "env.txt"
    binary = fake_bin(tmp_path / "bin", "manpath", f'/usr/bin/env > "{dump}"')
    run_manpath(env, binary=str(binary))
    pairs = (line.partition("=") for line in dump.read_text(encoding="utf-8").splitlines())
    ignored = {"PWD", "SHLVL", "_", "OLDPWD"}
    return {key: value for key, _, value in pairs if key not in ignored}


def test_run_manpath_passes_only_path_manpath_and_locale(tmp_path: Path) -> None:
    env = {"PATH": "/p", "MANPATH": "/m", "HOME": "/h", "SECRET": "s"}
    assert child_env(tmp_path, env) == {
        "PATH": "/p",
        "MANPATH": "/m",
        "LC_ALL": "en_US.UTF-8",
        "LANG": "en_US.UTF-8",
    }


def test_run_manpath_empty_env_has_no_path_or_manpath(tmp_path: Path) -> None:
    assert child_env(tmp_path, {}) == {"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}


def test_run_manpath_blank_output_is_not_an_error(tmp_path: Path) -> None:
    binary = fake_bin(tmp_path / "bin", "manpath", "exit 0")
    assert run_manpath({}, binary=str(binary)) == ""


def test_run_manpath_decodes_invalid_utf8_with_replacement(tmp_path: Path) -> None:
    binary = fake_bin(tmp_path / "bin", "manpath", "printf '/a\\377/man'")
    assert run_manpath({}, binary=str(binary)) == "/a�/man"


def test_run_manpath_non_zero_exit_raises(tmp_path: Path) -> None:
    binary = fake_bin(tmp_path / "bin", "manpath", "exit 3")
    with pytest.raises(IngestError, match=MANPATH_FAILED):
        run_manpath({}, binary=str(binary))


def test_run_manpath_missing_binary_raises_from_oserror(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match=MANPATH_FAILED) as info:
        run_manpath({}, binary=str(tmp_path / "nope"))
    assert isinstance(info.value.__cause__, OSError)


def test_run_manpath_timeout_raises(tmp_path: Path) -> None:
    binary = fake_bin(tmp_path / "bin", "manpath", "exec /bin/sleep 10")
    with pytest.raises(IngestError, match=MANPATH_FAILED):
        run_manpath({}, binary=str(binary), timeout=0.2)


@pytest.mark.parametrize("timeout", [0, -1.0])
def test_run_manpath_rejects_non_positive_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        run_manpath({}, timeout=timeout)


def touch(root: Path, relative: str, *, ns: int | None = None) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(".TH X 1\n", encoding="utf-8")
    if ns is not None:
        os.utime(path, ns=(ns, ns))
    return path


def listing(locator: ManPageLocator) -> list[tuple[str, str]]:
    return [(man.name, man.section) for man in locator.locate()]


def keys(locator: ManPageLocator) -> list[tuple[str, str, int, str]]:
    return [(m.name, m.section, m.dir_index, m.path.name) for m in locator.locate()]


def test_locate_extracts_name_and_directory_section(tmp_path: Path) -> None:
    for relative in (
        "man1/ls.1",
        "man1/openssl-x509.1ssl",
        "man1/less.1.gz",
        "man1/tcl.1tcl",
        "man8/mount.8",
    ):
        touch(tmp_path, relative)
    assert listing(ManPageLocator([tmp_path])) == [
        ("less", "1"),
        ("ls", "1"),
        ("mount", "8"),
        ("openssl-x509", "1"),
        ("tcl", "1"),
    ]


def test_locate_keeps_dots_inside_the_name(tmp_path: Path) -> None:
    touch(tmp_path, "man1/python3.13.1")
    assert listing(ManPageLocator([tmp_path])) == [("python3.13", "1")]


def test_locate_path_is_dir_man_section_file(tmp_path: Path) -> None:
    touch(tmp_path, "man1/ls.1.gz")
    (man,) = ManPageLocator([tmp_path]).locate()
    assert man.path == tmp_path / "man1" / "ls.1.gz"


def test_locate_skips_files_that_are_not_man_pages(tmp_path: Path) -> None:
    for relative in (
        "man1/x.8",
        "man1/README.md",
        "man1/.DS_Store",
        "man1/noext",
        "man1/.1",
        "man1/a b.1",
        "man1/x.1.bz2",
        "man5/x.5",
    ):
        touch(tmp_path, relative)
    (tmp_path / "man1" / "sub.1").mkdir()
    (tmp_path / "man1" / "gone.1").symlink_to(tmp_path / "man1" / "absent")
    (tmp_path / "man1" / "loop.1").symlink_to(tmp_path / "man1" / "loop.1")
    (tmp_path / "man1" / "ping.1").symlink_to(tmp_path / "man1" / "pong.1")
    (tmp_path / "man1" / "pong.1").symlink_to(tmp_path / "man1" / "ping.1")
    assert listing(ManPageLocator([tmp_path])) == []


def test_locate_yields_symlink_path_with_target_mtime(tmp_path: Path) -> None:
    real = touch(tmp_path, "man1/real.1")
    os.utime(real, ns=(1, 1_000_000_000))
    link = tmp_path / "man1" / "link.1"
    link.symlink_to(real)
    by_name = {man.name: man for man in ManPageLocator([tmp_path]).locate()}
    assert by_name["link"].path == link
    assert by_name["link"].mtime_ns == 1_000_000_000


def test_locate_mtime_ns_matches_stat(tmp_path: Path) -> None:
    path = touch(tmp_path, "man1/ls.1", ns=1_700_000_000_123_456_789)
    (man,) = ManPageLocator([tmp_path]).locate()
    assert man.mtime_ns == path.stat().st_mtime_ns


def test_locate_skips_file_that_cannot_be_statted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    touch(tmp_path, "man1/bad.1")
    touch(tmp_path, "man1/ok.1")
    real_stat = Path.stat

    def stat(self: Path, **kwargs: bool) -> os.stat_result:
        if self.name == "bad.1":
            raise PermissionError(13, "denied")
        return real_stat(self, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    assert listing(ManPageLocator([tmp_path])) == [("ok", "1")]


def test_locate_orders_by_name_section_dir_and_file_name(tmp_path: Path) -> None:
    first, second = tmp_path / "d0", tmp_path / "d1"
    for root, relative in (
        (second, "man1/git.1"),
        (first, "man8/git.8"),
        (first, "man1/git.1.gz"),
        (second, "man1/a.1"),
        (first, "man1/git.1"),
    ):
        touch(root, relative)
    assert keys(ManPageLocator([first, second])) == [
        ("a", "1", 1, "a.1"),
        ("git", "1", 0, "git.1"),
        ("git", "1", 0, "git.1.gz"),
        ("git", "1", 1, "git.1"),
        ("git", "8", 0, "git.8"),
    ]


def test_locate_orders_same_dir_copies_by_file_name(tmp_path: Path) -> None:
    touch(tmp_path, "man1/x.1m")
    touch(tmp_path, "man1/x.1")
    assert [m.path.name for m in ManPageLocator([tmp_path]).locate()] == ["x.1", "x.1m"]


def test_locate_follows_the_section_order_given(tmp_path: Path) -> None:
    touch(tmp_path, "man1/ls.1")
    touch(tmp_path, "man8/ls.8")
    assert listing(ManPageLocator([tmp_path], sections=("8", "1"))) == [("ls", "8"), ("ls", "1")]


def test_locate_uses_configured_sections(tmp_path: Path) -> None:
    touch(tmp_path, "man5/passwd.5")
    touch(tmp_path, "man1/ls.1")
    assert listing(ManPageLocator([tmp_path], sections=("5",))) == [("passwd", "5")]


def test_locate_ignores_missing_file_and_man_less_dirs(tmp_path: Path) -> None:
    regular = tmp_path / "regular"
    regular.write_text("x", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    good = tmp_path / "good"
    touch(good, "man1/ls.1")
    locator = ManPageLocator([tmp_path / "missing", regular, tmp_path / "empty", good])
    assert keys(locator) == [("ls", "1", 3, "ls.1")]


def test_locate_ignores_unreadable_section_dir(tmp_path: Path) -> None:
    touch(tmp_path, "man1/ls.1")
    touch(tmp_path, "man8/mount.8")
    (tmp_path / "man8").chmod(0)
    try:
        assert listing(ManPageLocator([tmp_path])) == [("ls", "1")]
    finally:
        (tmp_path / "man8").chmod(0o755)


def test_locate_deduplicates_dirs_keeping_first_index(tmp_path: Path) -> None:
    other = tmp_path / "other"
    touch(tmp_path, "man1/ls.1")
    touch(other, "man1/cp.1")
    locator = ManPageLocator([tmp_path, tmp_path, other])
    assert keys(locator) == [("cp", "1", 1, "cp.1"), ("ls", "1", 0, "ls.1")]


def test_locate_origin_follows_the_directory(tmp_path: Path) -> None:
    touch(tmp_path, "man1/ls.1")
    (man,) = ManPageLocator([tmp_path]).locate()
    assert man.origin is Origin.MACOS


def test_locate_does_not_resolve_dir_dots(tmp_path: Path) -> None:
    touch(tmp_path, "man1/ls.1")
    (tmp_path / "sub").mkdir()
    root = tmp_path / "sub" / ".."
    (man,) = ManPageLocator([root]).locate()
    assert man.path == root / "man1" / "ls.1"


@pytest.mark.parametrize("sections", [(), ("1/../x",), ("",), ("1", "A"), ("1 ",)])
def test_locator_rejects_invalid_sections(sections: Iterable[str]) -> None:
    with pytest.raises(ValueError, match="section"):
        ManPageLocator([Path("/x")], sections=tuple(sections))


def test_locate_is_repeatable_and_rescans(tmp_path: Path) -> None:
    touch(tmp_path, "man1/ls.1")
    locator = ManPageLocator([tmp_path])
    assert list(locator.locate()) == list(locator.locate())
    touch(tmp_path, "man1/cp.1")
    assert listing(locator) == [("cp", "1"), ("ls", "1")]


def test_man_file_is_frozen_and_slotted() -> None:
    man = ManFile(Path("/m/man1/ls.1"), "ls", "1", Origin.MACOS, 5, 0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        man.name = "x"  # type: ignore[misc]  # frozen dataclass: assignment must fail
    assert not hasattr(man, "__dict__")


def test_dirs_property_is_deduplicated_in_order(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    locator = ManPageLocator([first, second, first])
    assert locator.dirs == (first, second)


def test_sections_property_returns_the_given_sections() -> None:
    assert ManPageLocator([Path("/m")]).sections == ("1", "8")
    assert ManPageLocator([Path("/m")], ["8", "1", "3pm"]).sections == ("8", "1", "3pm")
