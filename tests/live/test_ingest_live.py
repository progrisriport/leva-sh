"""Live ingest of this Mac: the PRD/NFR numbers on a real index (T-6.6)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from leva.repo import Repository
from leva.sources import ExecutableScanner
from leva.store import open_readonly

if TYPE_CHECKING:
    # pytest loads conftest itself; importing it at runtime would execute it a second time.
    from tests.live.conftest import LiveIndex

SYSTEM_DIRS: Final = (Path("/bin"), Path("/sbin"), Path("/usr/bin"), Path("/usr/sbin"))
MIN_SUMMARY_SHARE: Final = 0.95
MAX_BUILD_SECONDS: Final = 30.0
MAX_INDEX_BYTES: Final = 100 * 1024 * 1024
LISTED: Final = 20

_log = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def repo(real_index: LiveIndex) -> Iterator[Repository]:
    repository = Repository(open_readonly(real_index.path))
    _log.info("index stats: %s", repository.stats())
    yield repository
    repository.close()


def test_every_system_executable_resolves(repo: Repository) -> None:
    names = sorted({exe.name for exe in ExecutableScanner(SYSTEM_DIRS).scan()})

    missing = [name for name in names if repo.get_entry(name) is None]

    _log.info("system executables: %d, missing: %d", len(names), len(missing))
    assert names
    assert not missing, f"{len(missing)} of {len(names)} unresolved: {missing[:LISTED]}"


def test_man_backed_entries_have_summaries(repo: Repository) -> None:
    rows = [row for row in repo.names() if row.section is not None]
    assert rows

    blank = [f"{row.name}({row.section})" for row in rows if not row.summary.strip()]
    share = 1 - len(blank) / len(rows)

    _log.info(
        "man-backed entries: %d, summary share: %.4f, blank: %s", len(rows), share, blank[:LISTED]
    )
    assert share >= MIN_SUMMARY_SHARE, f"summary share {share:.4f}; first blank: {blank[:LISTED]}"


def test_build_is_fast_enough(real_index: LiveIndex) -> None:
    _log.info("build seconds: %.2f (wall %.2f)", real_index.report.seconds, real_index.wall_seconds)

    assert real_index.report.seconds <= MAX_BUILD_SECONDS


def test_index_is_small_enough(real_index: LiveIndex) -> None:
    size = real_index.path.stat().st_size

    _log.info("index size: %.2f MB", size / (1024 * 1024))
    assert size <= MAX_INDEX_BYTES


@pytest.mark.parametrize(("name", "minimum"), [("git", 20), ("diskutil", 15), ("launchctl", 10)])
def test_subcommand_thresholds(repo: Repository, name: str, minimum: int) -> None:
    entry = repo.get_entry(name)
    if entry is None:
        pytest.skip(f"{name} has no entry on this Mac")

    found = repo.subcommands(entry.id)

    _log.info("subcommands of %s: %d", name, len(found))
    assert len(found) >= minimum
