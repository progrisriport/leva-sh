"""Map a file-system location to the `Origin` of the command found there (D-004)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from leva.model import Origin

_HOMEBREW_PREFIXES: Final = (Path("/opt/homebrew"), Path("/usr/local"))


def origin_for(path: Path) -> Origin:
    """Return `Origin.HOMEBREW` under a Homebrew prefix, else `Origin.MACOS`.

    Pure: compares path components only, never touching the file system. `/usr/local` itself
    is Homebrew, `/usr/localfoo` is not, and a relative path is always macOS.
    """
    if any(path.is_relative_to(prefix) for prefix in _HOMEBREW_PREFIXES):
        return Origin.HOMEBREW
    return Origin.MACOS
