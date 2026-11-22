"""Live clipboard check against the real macOS ``pbcopy`` / ``pbpaste``."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final

import pytest

from leva.clipboard import PbcopyClipboard

pytestmark = pytest.mark.clipboard

PBCOPY: Final = "/usr/bin/pbcopy"
PBPASTE: Final = "/usr/bin/pbpaste"
UTF8_ENV: Final = {"LANG": "en_US.UTF-8", "LC_CTYPE": "en_US.UTF-8"}


@pytest.mark.skipif(
    not (Path(PBCOPY).exists() and Path(PBPASTE).exists()),
    reason="pbcopy/pbpaste not available",
)
def test_pbcopy_round_trip_through_pbpaste() -> None:
    """Copy text with `PbcopyClipboard`, read it back with ``pbpaste``, restore the clipboard.

    Only text content is restored; an image or other non-text clipboard content is lost.
    """
    saved = subprocess.run(
        [PBPASTE], capture_output=True, check=True, env=UTF8_ENV, timeout=5
    ).stdout
    text = "leva live check: café ✓"
    try:
        PbcopyClipboard().copy(text)
        pasted = subprocess.run(
            [PBPASTE], capture_output=True, check=True, env=UTF8_ENV, timeout=5
        ).stdout
        assert pasted.decode("utf-8") == text
    finally:
        subprocess.run([PBCOPY], input=saved, check=True, env=UTF8_ENV, timeout=5)
