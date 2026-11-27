"""leva.ingest: the index lock and the null progress sink."""

from __future__ import annotations

import fcntl
from pathlib import Path

import pytest

from leva.ingest import NullProgress
from leva.ingest._lock import BUSY, LOCK_NAME, index_lock
from leva.model import IngestError


def test_lock_creates_the_file_and_keeps_it_after_release(tmp_path: Path) -> None:
    path = tmp_path / LOCK_NAME
    with index_lock(path):
        assert path.is_file()
    assert path.is_file()


def test_lock_is_released_after_the_block(tmp_path: Path) -> None:
    path = tmp_path / LOCK_NAME
    with index_lock(path):
        pass
    with index_lock(path):
        pass


def test_lock_is_released_when_the_block_raises(tmp_path: Path) -> None:
    path = tmp_path / LOCK_NAME
    with pytest.raises(RuntimeError, match="boom"), index_lock(path):
        raise RuntimeError("boom")
    with index_lock(path):
        pass


def test_second_lock_on_the_same_path_is_busy_with_a_hint(tmp_path: Path) -> None:
    path = tmp_path / LOCK_NAME
    with index_lock(path), pytest.raises(IngestError) as caught, index_lock(path):
        pass
    assert caught.value.message == BUSY == "another leva is building the index"
    assert caught.value.hint == "wait for it to finish, then try again"
    assert isinstance(caught.value.__cause__, BlockingIOError)


def test_lock_in_a_missing_directory_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "missing" / LOCK_NAME
    with pytest.raises(IngestError) as caught, index_lock(path):
        pass
    assert caught.value.message == f"cannot lock index: {path}"
    assert isinstance(caught.value.__cause__, OSError)


def test_lock_maps_other_flock_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_flock(fd: int, operation: int) -> None:
        raise OSError("flock failed")

    monkeypatch.setattr(fcntl, "flock", failing_flock)
    path = tmp_path / LOCK_NAME
    with pytest.raises(IngestError) as caught, index_lock(path):
        pass
    assert caught.value.message == f"cannot lock index: {path}"
    assert caught.value.hint is None


def test_null_progress_ignores_everything() -> None:
    progress = NullProgress()
    assert progress.phase("scan", None) is None
    assert progress.phase("render", 3) is None
    assert progress.advance() is None
    assert progress.advance(5) is None
    assert progress.warn("something") is None
