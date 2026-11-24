"""Live smoke of `leva.sources` and man page rendering on this Mac."""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final

import pytest

from leva.manparse import MandocRenderer, parse_man
from leva.model import ManRenderError, Origin
from leva.sources import (
    DEFAULT_BIN_DIRS,
    ExecutableScanner,
    ManFile,
    ManPageLocator,
    SystemInfo,
    discover_man_dirs,
    run_manpath,
)

MANDOC: Final = Path("/usr/bin/mandoc")
MAN_ROOT: Final = Path("/usr/share/man")
MIN_EXECUTABLES: Final = 500
MIN_PAGES: Final = 500
MAX_FAILURE_RATE: Final = 0.02
WORKERS: Final = 8
LISTED_FAILURES: Final = 20

_log = logging.getLogger(__name__)


def test_usr_bin_has_at_least_500_executables() -> None:
    found = list(ExecutableScanner([Path("/usr/bin")]).scan())
    names = [exe.name for exe in found]

    assert len(found) >= MIN_EXECUTABLES
    assert len(set(names)) == len(names)
    assert {exe.origin for exe in found} == {Origin.MACOS}


def test_ls_is_found_in_the_default_bin_dirs() -> None:
    found = ExecutableScanner(DEFAULT_BIN_DIRS).scan()

    assert any(exe.name == "ls" and exe.path == Path("/bin/ls") for exe in found)


def test_system_info_detects_this_mac() -> None:
    info = SystemInfo.detect()

    assert re.fullmatch(r"\d+(\.\d+)*", info.macos_version)
    assert info.macos_build.strip()
    assert info.arch in {"arm64", "x86_64"}


def test_manpath_includes_usr_share_man() -> None:
    assert MAN_ROOT in discover_man_dirs(run_manpath(os.environ))


def _winners(man_files: list[ManFile]) -> list[ManFile]:
    """Keep the first `ManFile` of each name (the D-005 winner)."""
    first: dict[str, ManFile] = {}
    for man_file in man_files:
        first.setdefault(man_file.name, man_file)
    return list(first.values())


def _render(renderer: MandocRenderer, man_file: ManFile) -> tuple[str | None, str]:
    """Render one page; return its text (None on failure) and the failure message."""
    try:
        return renderer.render(man_file.path), ""
    except ManRenderError as exc:
        return None, str(exc)


@pytest.mark.skipif(not MANDOC.exists(), reason="mandoc not available")
def test_man1_renders_with_at_most_2_percent_failures() -> None:
    winners = _winners(list(ManPageLocator([MAN_ROOT], sections=("1",)).locate()))
    renderer = MandocRenderer()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda man_file: _render(renderer, man_file), winners))

    failures = [
        (man.path, message)
        for man, (text, message) in zip(winners, results, strict=True)
        if text is None
    ]
    for man_file, (text, _) in zip(winners, results, strict=True):
        if text is not None:
            parse_man(text, name_hint=man_file.name)
    _log.info("man1 pages: %d, render failures: %d", len(winners), len(failures))

    listed = "\n".join(f"{path}: {message}" for path, message in failures[:LISTED_FAILURES])
    assert len(winners) >= MIN_PAGES
    assert len(failures) / len(winners) <= MAX_FAILURE_RATE, (
        f"{len(failures)} of {len(winners)} man1 pages failed to render:\n{listed}"
    )
