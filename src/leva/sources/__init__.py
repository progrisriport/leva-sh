"""Read raw material from the OS.

Executables, man files, system info and allowlisted help probes.
"""

from __future__ import annotations

from leva.sources._executables import DEFAULT_BIN_DIRS, Executable, ExecutableScanner
from leva.sources._manpages import ManFile, ManPageLocator, discover_man_dirs, run_manpath
from leva.sources._origin import origin_for
from leva.sources._probe import ProbeRunner
from leva.sources._system import SystemInfo

__all__ = [
    "DEFAULT_BIN_DIRS",
    "Executable",
    "ExecutableScanner",
    "ManFile",
    "ManPageLocator",
    "ProbeRunner",
    "SystemInfo",
    "discover_man_dirs",
    "origin_for",
    "run_manpath",
]
