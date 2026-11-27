"""Tests for ``leva.ingest`` fingerprint and staleness."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from leva.ingest import (
    META_SYSTEM,
    META_VERSION,
    Fingerprint,
    Staleness,
    compute_fingerprint,
    dir_stat,
    staleness,
)
from leva.sources import SystemInfo
from leva.store import SCHEMA_VERSION, IndexWriter
from tests.support.index_factory import build_fixture_index

SYSTEM = SystemInfo("26.2", "25C56", "arm64")
HEX64 = re.compile(r"[0-9a-f]{64}")
T0, T1, T2, T3 = (
    1_700_000_000 * 10**9,
    1_700_000_100 * 10**9,
    1_700_000_200 * 10**9,
    1_700_000_300 * 10**9,
)


def _touch(path: Path, mtime_ns: int = T1) -> Path:
    path.write_text("x")
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def _set_mtime(path: Path, mtime_ns: int) -> None:
    os.utime(path, ns=(mtime_ns, mtime_ns))


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "man" / "man1").mkdir(parents=True)
    (tmp_path / "man" / "man8").mkdir()
    (tmp_path / "bin").mkdir()
    _touch(tmp_path / "man" / "man1" / "ls.1")
    _touch(tmp_path / "man" / "man8" / "mount.8")
    _touch(tmp_path / "bin" / "ls")
    _touch(tmp_path / "bin" / "cat")
    for directory in (tmp_path / "man" / "man1", tmp_path / "man" / "man8", tmp_path / "bin"):
        _set_mtime(directory, T0)
    return tmp_path


def fingerprint(root: Path, **over: object) -> Fingerprint:
    args: dict[str, object] = {
        "leva_version": "0.1.0",
        "content_version": "c" * 64,
        "system": SYSTEM,
        "man_dirs": [root / "man"],
        "sections": ["1", "8"],
        "bin_dirs": [root / "bin"],
        "config_digest": "d" * 64,
    }
    args.update(over)
    return compute_fingerprint(**args)  # type: ignore[arg-type]  # kwargs built from a dict of objects


def write_index(path: Path, fp: Fingerprint) -> Path:
    with IndexWriter(path) as writer:
        for key, value in fp.meta().items():
            writer.set_meta(key, value)
        writer.finalize(built_at=datetime(2026, 1, 1, tzinfo=UTC))
    return path


# --- dir_stat ---------------------------------------------------------------


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    directory = tmp_path / "scratch"
    directory.mkdir()
    return directory


def test_dir_stat_takes_max_entry_mtime(scratch: Path) -> None:
    _touch(scratch / "a", T1)
    _touch(scratch / "b", T2)
    _set_mtime(scratch, T0)
    assert dir_stat(scratch) == (2, T2)


def test_dir_stat_takes_directory_mtime_when_newer(scratch: Path) -> None:
    _touch(scratch / "a", T1)
    _touch(scratch / "b", T2)
    _set_mtime(scratch, T3)
    assert dir_stat(scratch) == (2, T3)


def test_dir_stat_missing_path(tmp_path: Path) -> None:
    assert dir_stat(tmp_path / "nope") == (-1, 0)


def test_dir_stat_regular_file(tmp_path: Path) -> None:
    assert dir_stat(_touch(tmp_path / "f")) == (-1, 0)


def test_dir_stat_empty_directory(scratch: Path) -> None:
    _set_mtime(scratch, T2)
    assert dir_stat(scratch) == (0, T2)


def test_dir_stat_counts_broken_symlink_and_subdirectory(scratch: Path) -> None:
    (scratch / "dangling").symlink_to(scratch / "gone")
    (scratch / "sub").mkdir()
    _set_mtime(scratch / "sub", T1)
    os.utime(scratch / "dangling", ns=(T2, T2), follow_symlinks=False)
    _set_mtime(scratch, T0)
    assert dir_stat(scratch) == (2, T2)


def test_dir_stat_counts_hidden_entries(scratch: Path) -> None:
    _touch(scratch / ".hidden")
    assert dir_stat(scratch)[0] == 1


class _BrokenEntry:
    def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
        raise PermissionError("denied")


class _FakeScan:
    def __init__(self, entries: list[_BrokenEntry]) -> None:
        self._entries = entries

    def __enter__(self) -> list[_BrokenEntry]:
        return self._entries

    def __exit__(self, *exc: object) -> None:
        return None


def test_dir_stat_keeps_entry_whose_stat_fails(
    scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_mtime(scratch, T2)
    monkeypatch.setattr(os, "scandir", lambda _path: _FakeScan([_BrokenEntry(), _BrokenEntry()]))
    assert dir_stat(scratch) == (2, T2)


def test_dir_stat_failed_entry_stat_ignored_for_pre_epoch_directory(
    scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_mtime(scratch, -T1)
    monkeypatch.setattr(os, "scandir", lambda _path: _FakeScan([_BrokenEntry()]))
    assert dir_stat(scratch) == (1, -T1)


def test_dir_stat_unreadable_directory(scratch: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(_path: Path) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(os, "scandir", deny)
    assert dir_stat(scratch) == (-1, 0)


# --- compute_fingerprint ----------------------------------------------------


def test_fingerprint_is_deterministic_hex(tree: Path) -> None:
    first, second = fingerprint(tree), fingerprint(tree)
    assert first == second
    assert HEX64.fullmatch(first.version_part)
    assert HEX64.fullmatch(first.system_part)


@pytest.mark.parametrize(
    "over",
    [{"leva_version": "0.2.0"}, {"content_version": "e" * 64}],
)
def test_version_part_changes_with_versions(tree: Path, over: dict[str, object]) -> None:
    base, changed = fingerprint(tree), fingerprint(tree, **over)
    assert changed.version_part != base.version_part
    assert changed.system_part == base.system_part


@pytest.mark.parametrize(
    "over",
    [
        {"system": SystemInfo("26.3", "25C56", "arm64")},
        {"system": SystemInfo("26.2", "25D1", "arm64")},
        {"config_digest": "e" * 64},
    ],
)
def test_system_part_changes_with_system_and_config(tree: Path, over: dict[str, object]) -> None:
    base, changed = fingerprint(tree), fingerprint(tree, **over)
    assert changed.system_part != base.system_part
    assert changed.version_part == base.version_part


def test_system_part_changes_with_bin_file(tree: Path) -> None:
    base = fingerprint(tree)
    _touch(tree / "bin" / "wc")
    assert fingerprint(tree).system_part != base.system_part


def test_system_part_changes_with_man_file(tree: Path) -> None:
    base = fingerprint(tree)
    _touch(tree / "man" / "man1" / "cat.1")
    assert fingerprint(tree).system_part != base.system_part


def test_system_part_changes_with_man_file_mtime(tree: Path) -> None:
    base = fingerprint(tree)
    _set_mtime(tree / "man" / "man1" / "ls.1", T3)
    assert fingerprint(tree).system_part != base.system_part


def test_system_part_changes_with_bin_dir_order(tree: Path) -> None:
    other = tree / "other"
    other.mkdir()
    ab = fingerprint(tree, bin_dirs=[tree / "bin", other])
    ba = fingerprint(tree, bin_dirs=[other, tree / "bin"])
    assert ab.system_part != ba.system_part


def test_arch_does_not_change_fingerprint(tree: Path) -> None:
    assert fingerprint(tree, system=SystemInfo("26.2", "25C56", "x86_64")) == fingerprint(tree)


def test_leva_version_does_not_change_system_part(tree: Path) -> None:
    assert fingerprint(tree, leva_version="9.9.9").system_part == fingerprint(tree).system_part


def test_duplicate_dirs_are_ignored(tree: Path) -> None:
    doubled = fingerprint(tree, bin_dirs=[tree / "bin", tree / "bin"], man_dirs=[tree / "man"] * 2)
    assert doubled == fingerprint(tree)


def test_missing_man_dir_differs_from_empty(tree: Path) -> None:
    missing = fingerprint(tree, man_dirs=[tree / "absent"])
    (tree / "empty" / "man1").mkdir(parents=True)
    (tree / "empty" / "man8").mkdir()
    for sub in ("man1", "man8"):
        _set_mtime(tree / "empty" / sub, 0)
    empty = fingerprint(tree, man_dirs=[tree / "empty"])
    assert missing.system_part != empty.system_part


# --- Fingerprint ------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_fingerprint_rejects_malformed_parts(bad: str) -> None:
    with pytest.raises(ValueError, match="64 lowercase hex"):
        Fingerprint(version_part=bad, system_part="a" * 64)
    with pytest.raises(ValueError, match="64 lowercase hex"):
        Fingerprint(version_part="a" * 64, system_part=bad)


def test_fingerprint_meta_has_exactly_two_keys() -> None:
    fp = Fingerprint(version_part="a" * 64, system_part="b" * 64)
    assert fp.meta() == {META_VERSION: "a" * 64, META_SYSTEM: "b" * 64}


# --- staleness --------------------------------------------------------------


def test_staleness_missing_file(tmp_path: Path, tree: Path) -> None:
    assert staleness(tmp_path / "none.db", fingerprint(tree)) is Staleness.MISSING


def test_staleness_garbage_file(tmp_path: Path, tree: Path) -> None:
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not sqlite")
    assert staleness(bad, fingerprint(tree)) is Staleness.MISSING


def test_staleness_directory_at_path(tmp_path: Path, tree: Path) -> None:
    (tmp_path / "dir.db").mkdir()
    assert staleness(tmp_path / "dir.db", fingerprint(tree)) is Staleness.MISSING


def test_staleness_index_without_meta_table(tmp_path: Path, tree: Path) -> None:
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.close()
    assert staleness(db, fingerprint(tree)) is Staleness.MISSING


def test_staleness_fresh(tmp_path: Path, tree: Path) -> None:
    fp = fingerprint(tree)
    assert staleness(write_index(tmp_path / "i.db", fp), fp) is Staleness.FRESH


@pytest.mark.parametrize(
    "over",
    [{"leva_version": "0.2.0"}, {"content_version": "e" * 64}],
)
def test_staleness_version_changed(tmp_path: Path, tree: Path, over: dict[str, object]) -> None:
    db = write_index(tmp_path / "i.db", fingerprint(tree, **over))
    assert staleness(db, fingerprint(tree)) is Staleness.VERSION_CHANGED


def test_staleness_fixture_index_without_fingerprint(tmp_path: Path, tree: Path) -> None:
    db = build_fixture_index(tmp_path / "fixture.db")
    assert staleness(db, fingerprint(tree)) is Staleness.VERSION_CHANGED


def test_staleness_system_changed_by_build(tmp_path: Path, tree: Path) -> None:
    db = write_index(tmp_path / "i.db", fingerprint(tree))
    newer = fingerprint(tree, system=SystemInfo("26.2", "25C99", "arm64"))
    assert staleness(db, newer) is Staleness.SYSTEM_CHANGED


def test_staleness_system_changed_by_config(tmp_path: Path, tree: Path) -> None:
    db = write_index(tmp_path / "i.db", fingerprint(tree))
    assert staleness(db, fingerprint(tree, config_digest="e" * 64)) is Staleness.SYSTEM_CHANGED


def test_staleness_system_changed_by_new_bin_file(tmp_path: Path, tree: Path) -> None:
    db = write_index(tmp_path / "i.db", fingerprint(tree))
    _touch(tree / "bin" / "wc")
    assert staleness(db, fingerprint(tree)) is Staleness.SYSTEM_CHANGED


def test_staleness_version_wins_over_system(tmp_path: Path, tree: Path) -> None:
    db = write_index(tmp_path / "i.db", fingerprint(tree))
    both = fingerprint(tree, leva_version="0.2.0", config_digest="e" * 64)
    assert staleness(db, both) is Staleness.VERSION_CHANGED


def test_staleness_releases_the_index_file(tmp_path: Path, tree: Path) -> None:
    fp = fingerprint(tree)
    db = write_index(tmp_path / "i.db", fp)
    assert staleness(db, fp) is Staleness.FRESH
    db.unlink()
    write_index(db, fp)
    assert staleness(db, fp) is Staleness.FRESH
