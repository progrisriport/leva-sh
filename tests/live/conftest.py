"""Session fixture: build this Mac's real index once for the live ingest checks (T-6.6)."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

import leva
from leva.config import LevaConfig
from leva.content import CuratedYamlProvider, TldrSnapshotProvider, default_root
from leva.ingest import BuildReport, IndexBuilder, NullProgress
from leva.manparse import MandocRenderer
from leva.sources import (
    DEFAULT_BIN_DIRS,
    ExecutableScanner,
    ManPageLocator,
    SystemInfo,
    discover_man_dirs,
    run_manpath,
)

LISTED_SKIPS: Final = 20

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveIndex:
    """The index built from this Mac and how long building it took.

    Attributes:
        path: Location of the index file.
        report: The report of the build.
        wall_seconds: ``time.perf_counter`` around ``build()``.
    """

    path: Path
    report: BuildReport
    wall_seconds: float


@pytest.fixture(scope="session")
def real_index(tmp_path_factory: pytest.TempPathFactory) -> LiveIndex:
    """Build this Mac's index once into ``tmp_path_factory.mktemp("leva-live")/index.db``."""
    path = tmp_path_factory.mktemp("leva-live") / "index.db"
    man_dirs = discover_man_dirs(run_manpath(dict(os.environ)))
    system = SystemInfo.detect()
    _log.info("live system: %s; man dirs: %d", system, len(man_dirs))
    config = LevaConfig()
    root = default_root()
    builder = IndexBuilder(
        executables=ExecutableScanner(DEFAULT_BIN_DIRS),
        man=ManPageLocator(man_dirs, config.sections),
        renderer=MandocRenderer(),
        providers=(CuratedYamlProvider(root), TldrSnapshotProvider(root)),
        system=system,
        config_digest=config.digest(),
        clock=lambda: datetime.now(UTC),
        leva_version=leva.__version__,
        content_root=root,
    )
    started = time.perf_counter()
    report = builder.build(path, NullProgress())
    wall_seconds = time.perf_counter() - started
    _log.info(
        "live build: entries=%d man_pages=%d skipped=%d curated=%d seconds=%.2f wall=%.2f",
        report.entries,
        report.man_pages,
        len(report.skipped),
        report.curated,
        report.seconds,
        wall_seconds,
    )
    for label, reason in report.skipped[:LISTED_SKIPS]:
        _log.info("live build skipped: %s: %s", label, reason)
    return LiveIndex(path=path, report=report, wall_seconds=wall_seconds)
