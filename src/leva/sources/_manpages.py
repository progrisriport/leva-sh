"""Discover the man directories and list the man page files they hold."""

from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from leva.model import IngestError, Origin, is_name
from leva.sources._origin import origin_for

_FALLBACK_MAN_DIRS: Final = (Path("/opt/homebrew/share/man"), Path("/usr/local/share/man"))
_MANPATH_ENV_KEYS: Final = ("PATH", "MANPATH")
_MANPATH_LOCALE: Final = {"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}
_MANPATH_FAILED: Final = "cannot list man directories: manpath failed"
_SECTION: Final = re.compile(r"[a-z0-9]+")

_log = logging.getLogger("leva.sources")


def discover_man_dirs(manpath_output: str, extra: Sequence[Path] = ()) -> tuple[Path, ...]:
    """Return the man directories to scan, in priority order (D-004).

    Order: the `manpath` entries, then `/opt/homebrew/share/man` and `/usr/local/share/man`,
    then `extra`.

    Pre: `manpath_output` is the stdout of `manpath` (colon separated, may be blank).
    Post: every path is absolute and unique by `Path` equality (first occurrence kept);
        missing directories are kept, `ManPageLocator` ignores them. Does no I/O.
    """
    listed = (Path(part) for part in manpath_output.strip().split(":") if part)
    candidates = (*listed, *_FALLBACK_MAN_DIRS, *extra)
    return tuple(dict.fromkeys(path for path in candidates if path.is_absolute()))


def run_manpath(
    env: Mapping[str, str], *, binary: str = "/usr/bin/manpath", timeout: float = 5.0
) -> str:
    """Run `manpath` with the user's `PATH` and `MANPATH` and return its stdout.

    Args:
        env: The user's environment; only `PATH` and `MANPATH` reach the child, which also
            gets fixed `LC_ALL` and `LANG` values.
        binary: Path of the `manpath` executable.
        timeout: Seconds to wait for it to finish.

    Pre: `timeout` is positive.
    Post: the output is decoded as UTF-8 with replacement and returned unmodified; blank
        output is not an error.

    Raises:
        ValueError: `timeout` is not positive.
        IngestError: `manpath` cannot run, times out or exits non-zero.
    """
    if timeout <= 0:
        raise ValueError(f"manpath timeout must be positive, got {timeout}")
    child_env = {key: env[key] for key in _MANPATH_ENV_KEYS if key in env} | _MANPATH_LOCALE
    try:
        result = subprocess.run(
            [binary],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=child_env,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _log.debug("manpath failed: %s", exc)
        raise IngestError(_MANPATH_FAILED) from exc
    if result.returncode != 0:
        _log.debug("manpath exited with status %d", result.returncode)
        raise IngestError(_MANPATH_FAILED)
    return result.stdout.decode("utf-8", errors="replace")


@dataclass(frozen=True, slots=True)
class ManFile:
    """A man page file found in a man directory.

    Attributes:
        path: ``<dir>/man<section>/<file name>`` as listed; symlinks are not resolved.
        name: Command name taken from the file name, a valid `Entry.name`.
        section: Section of the directory the file lives in, not of its extension.
        origin: `origin_for` the man directory.
        mtime_ns: Modification time in nanoseconds, following symlinks.
        dir_index: Position of the man directory in the deduplicated directory list.
    """

    path: Path
    name: str
    section: str
    origin: Origin
    mtime_ns: int
    dir_index: int


def _parse_name(filename: str, section: str) -> str | None:
    """Return the command name of man file `filename` in a `man<section>` directory.

    A `.gz` suffix is dropped; the remaining extension must start with `section` (so
    `openssl-x509.1ssl` gives `openssl-x509`). Anything else gives None.
    """
    base, dot, ext = filename.removesuffix(".gz").rpartition(".")
    if dot and is_name(base) and ext.startswith(section):
        return base
    return None


def _list(subdir: Path) -> list[Path]:
    """Return the children of `subdir` sorted by name; unreadable or missing gives none."""
    try:
        return sorted(subdir.iterdir(), key=lambda child: child.name)
    except OSError as exc:
        _log.debug("skipping man dir %s: %s", subdir, exc)
        return []


def _mtime_ns(path: Path) -> int | None:
    """Return the modification time of the regular file behind `path`, else None."""
    try:
        return path.stat().st_mtime_ns if path.is_file() else None
    except OSError as exc:
        _log.debug("skipping %s: %s", path, exc)
        return None


def _man_file(path: Path, section: str, origin: Origin, dir_index: int) -> ManFile | None:
    """Build the `ManFile` for `path`, or None when it is not a readable man page file."""
    name = _parse_name(path.name, section)
    mtime_ns = None if name is None else _mtime_ns(path)
    if name is None or mtime_ns is None:
        _log.debug("skipping %s: not a man page file", path)
        return None
    return ManFile(path, name, section, origin, mtime_ns, dir_index)


class ManPageLocator:
    """List the man page files of a sequence of man directories in a deterministic order."""

    def __init__(self, man_dirs: Sequence[Path], sections: Sequence[str] = ("1", "8")) -> None:
        """Remember the directories (deduplicated, first kept) and the sections to scan.

        Does no I/O.

        Raises:
            ValueError: `sections` is empty or holds a value not matching ``[a-z0-9]+``.
        """
        if not sections:
            raise ValueError("sections must not be empty")
        for section in sections:
            if _SECTION.fullmatch(section) is None:
                raise ValueError(f"invalid man section: {section!r}")
        self._dirs = tuple(dict.fromkeys(man_dirs))
        self._sections = tuple(sections)

    @property
    def dirs(self) -> tuple[Path, ...]:
        """The man directories, deduplicated, in priority order."""
        return self._dirs

    @property
    def sections(self) -> tuple[str, ...]:
        """The man sections scanned under every man directory, in the given order."""
        return self._sections

    def locate(self) -> Iterator[ManFile]:
        """Yield every man page file, sorted by name, section, directory and file name.

        Rescans the file system on every call. The first yielded `ManFile` of each
        (name, section) is the one ingest keeps (D-005). Missing or unreadable directories,
        files whose extension does not start with the directory's section, names that
        cannot be an `Entry.name`, directories and broken or circular symlinks are skipped.
        """
        found = [
            (man.name, section_index, man.dir_index, man.path.name, man)
            for dir_index, directory in enumerate(self._dirs)
            for section_index, section in enumerate(self._sections)
            for child in _list(directory / f"man{section}")
            if (man := _man_file(child, section, origin_for(directory), dir_index))
        ]
        found.sort(key=lambda item: item[:4])
        for *_, man in found:
            yield man
