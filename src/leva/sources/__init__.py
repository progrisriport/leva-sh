"""Read raw material from the OS.

Executables, man files, system info and allowlisted help probes.
"""

from __future__ import annotations

from leva.sources._executables import DEFAULT_BIN_DIRS, Executable, ExecutableScanner
from leva.sources._origin import origin_for
from leva.sources._system import SystemInfo

__all__ = [
    "DEFAULT_BIN_DIRS",
    "Executable",
    "ExecutableScanner",
    "SystemInfo",
    "origin_for",
]
