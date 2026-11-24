"""List the executables found in the bin directories."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from leva.model import Origin, is_name
from leva.sources._origin import origin_for

DEFAULT_BIN_DIRS: Final[tuple[Path, ...]] = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
    Path("/bin"),
    Path("/usr/sbin"),
    Path("/sbin"),
)

_log = logging.getLogger("leva.sources")


@dataclass(frozen=True, slots=True)
class Executable:
    """An executable file found in a bin directory.

    Attributes:
        name: File name, a valid `Entry.name`.
        path: ``directory / name`` as listed; symlinks are not resolved.
        origin: `origin_for` the directory.
    """

    name: str
    path: Path
    origin: Origin


def _list_dir(directory: Path) -> list[Path]:
    """Return the children of `directory`; unreadable or missing directories give none."""
    try:
        return list(directory.iterdir())
    except OSError as exc:
        _log.debug("skipping bin dir %s: %s", directory, exc)
        return []


def _is_executable(path: Path) -> bool:
    """Tell whether `path` is, after following symlinks, a file the user may execute."""
    try:
        return is_name(path.name) and path.is_file() and os.access(path, os.X_OK)
    except OSError as exc:
        _log.debug("skipping %s: %s", path, exc)
        return False


class ExecutableScanner:
    """List every executable of a sequence of directories in a deterministic order."""

    def __init__(self, dirs: Sequence[Path]) -> None:
        """Remember `dirs`, deduplicated by equality keeping the first occurrence.

        Does no I/O.
        """
        self._dirs = tuple(dict.fromkeys(dirs))

    def scan(self) -> Iterator[Executable]:
        """Yield the executables, sorted by name and then by directory position.

        Rescans the file system on every call. A same-named file in several directories is
        yielded once per directory (the first in PATH order wins in ingest). Missing or
        unreadable directories, non-executables, directories, broken or circular symlinks and
        names that cannot be an `Entry.name` are skipped.
        """
        found = [
            (path.name, index, Executable(path.name, path, origin_for(directory)))
            for index, directory in enumerate(self._dirs)
            for path in _list_dir(directory)
            if _is_executable(path)
        ]
        found.sort(key=lambda item: (item[0], item[1]))
        for _, _, executable in found:
            yield executable
