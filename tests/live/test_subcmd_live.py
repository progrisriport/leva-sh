"""Live check of the section-list subcommand extractor on this Mac's man pages (D-008)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from leva.manparse import MandocRenderer, parse_man
from leva.subcmd import SectionListExtractor

LAUNCHCTL_PAGE: Final = Path("/usr/share/man/man1/launchctl.1")
DISKUTIL_PAGE: Final = Path("/usr/share/man/man8/diskutil.8")


def _subcommand_names(page: Path, command: str) -> list[str]:
    parsed = parse_man(MandocRenderer().render(page), name_hint=command)
    return [sub.name for sub in SectionListExtractor().extract(command, parsed, {})]


@pytest.mark.skipif(not LAUNCHCTL_PAGE.exists(), reason="launchctl man page not available")
def test_launchctl_subcommands_are_found() -> None:
    names = _subcommand_names(LAUNCHCTL_PAGE, "launchctl")

    assert len(names) >= 10
    assert {"bootstrap", "print"} <= set(names)
    assert not any("/" in name for name in names)


@pytest.mark.skipif(not DISKUTIL_PAGE.exists(), reason="diskutil man page not available")
def test_diskutil_verbs_are_found() -> None:
    names = _subcommand_names(DISKUTIL_PAGE, "diskutil")

    assert len(names) >= 15
    assert {"list", "eraseDisk"} <= set(names)


PROSE_NOISE: Final = [
    ("launchctl", "/usr/share/man/man1/launchctl.1", {"fundamental", "manages"}),
    ("ktrace", "/usr/share/man/man1/ktrace.1", {"logical"}),
    ("tailspin", "/usr/share/man/man1/tailspin.1", {"logical"}),
]


@pytest.mark.parametrize(("command", "page", "prose"), PROSE_NOISE)
def test_intro_prose_is_not_extracted_as_subcommands(
    command: str, page: str, prose: set[str]
) -> None:
    if not Path(page).exists():
        pytest.skip(f"{command} man page not available")

    names = _subcommand_names(Path(page), command)

    assert command not in names
    assert not prose & set(names)
