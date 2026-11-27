"""Fingerprint what an index was built from and compare it with an existing index."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from leva.model import IndexUnavailableError
from leva.repo import Repository
from leva.sources import SystemInfo
from leva.store import SCHEMA_VERSION, open_readonly

META_VERSION: Final = "fingerprint_version"
META_SYSTEM: Final = "fingerprint_system"

_HEX64: Final = re.compile(r"[0-9a-f]{64}")


class Staleness(StrEnum):
    """How an existing index relates to the current Leva and system state."""

    MISSING = "missing"
    VERSION_CHANGED = "version_changed"
    SYSTEM_CHANGED = "system_changed"
    FRESH = "fresh"


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """Two digests of what an index is built from.

    Attributes:
        version_part: Digest of the Leva version, the content version and the schema version.
        system_part: Digest of the macOS version and build, the man and bin directory stats
            and the config digest.

    Raises:
        ValueError: If a part is not 64 lowercase hex characters.
    """

    version_part: str
    system_part: str

    def __post_init__(self) -> None:
        for part in (self.version_part, self.system_part):
            if not _HEX64.fullmatch(part):
                raise ValueError(f"fingerprint part must be 64 lowercase hex characters: {part!r}")

    def meta(self) -> dict[str, str]:
        """Return the two meta items to store in the index."""
        return {META_VERSION: self.version_part, META_SYSTEM: self.system_part}


def dir_stat(path: Path) -> tuple[int, int]:
    """Count the entries of a directory and find its newest modification time.

    Entries are read with ``lstat`` semantics, so broken symlinks are counted and a re-linked
    file changes the result.

    Args:
        path: Directory to inspect.

    Returns:
        ``(entry count, max mtime_ns)`` where the mtime covers the directory itself and every
        entry; ``(-1, 0)`` when `path` is missing, not a directory or unreadable. An entry whose
        stat fails is counted but its mtime is ignored. Never raises.
    """
    try:
        newest = path.stat().st_mtime_ns
        with os.scandir(path) as scan:
            count = 0
            for entry in scan:
                count += 1
                newest = max(newest, _entry_mtime(entry, default=newest))
    except OSError:
        return (-1, 0)
    return (count, newest)


def _entry_mtime(entry: os.DirEntry[str], *, default: int) -> int:
    try:
        return entry.stat(follow_symlinks=False).st_mtime_ns
    except OSError:
        return default


def _canonical_sha256(payload: object) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dedup(paths: Sequence[Path]) -> list[Path]:
    return list(dict.fromkeys(paths))


def _man_stats(man_dirs: Sequence[Path], sections: Sequence[str]) -> list[list[object]]:
    return [
        [str(man_dir), section, *dir_stat(man_dir / f"man{section}")]
        for man_dir in _dedup(man_dirs)
        for section in sections
    ]


def _bin_stats(bin_dirs: Sequence[Path]) -> list[list[object]]:
    return [[str(bin_dir), *dir_stat(bin_dir)] for bin_dir in _dedup(bin_dirs)]


def compute_fingerprint(
    *,
    leva_version: str,
    content_version: str,
    system: SystemInfo,
    man_dirs: Sequence[Path],
    sections: Sequence[str],
    bin_dirs: Sequence[Path],
    config_digest: str,
) -> Fingerprint:
    """Compute the fingerprint of the current Leva and system state.

    Args:
        leva_version: Leva's own version, injected by the composition root.
        content_version: Digest of the curated content and tldr snapshot.
        system: macOS version and build; the CPU architecture is not part of the fingerprint.
        man_dirs: Man roots in search order (duplicates are dropped, the order is hashed).
        sections: Man sections to stat under every man root (``man<sec>`` directories).
        bin_dirs: Executable directories in search order (duplicates are dropped).
        config_digest: ``LevaConfig.digest()``.

    Returns:
        The two-part fingerprint. Reads directory metadata only.
    """
    version = {"content": content_version, "leva": leva_version, "schema": SCHEMA_VERSION}
    system_state = {
        "bin": _bin_stats(bin_dirs),
        "config": config_digest,
        "macos_build": system.macos_build,
        "macos_version": system.macos_version,
        "man": _man_stats(man_dirs, sections),
    }
    return Fingerprint(_canonical_sha256(version), _canonical_sha256(system_state))


def staleness(index_db: Path, current: Fingerprint) -> Staleness:
    """Compare the fingerprint stored in an index with the current one.

    Args:
        index_db: Path of the index file.
        current: Fingerprint of the current state.

    Returns:
        ``MISSING`` when the index is missing, unreadable or corrupt; ``VERSION_CHANGED`` when
        the version part differs or is absent (checked first); ``SYSTEM_CHANGED`` when only the
        system part differs; else ``FRESH``. The connection is closed before returning.
    """
    try:
        repo = Repository(open_readonly(index_db))
    except IndexUnavailableError:
        return Staleness.MISSING
    try:
        meta = repo.meta()
    except IndexUnavailableError:
        return Staleness.MISSING
    finally:
        repo.close()
    if meta.get(META_VERSION) != current.version_part:
        return Staleness.VERSION_CHANGED
    if meta.get(META_SYSTEM) != current.system_part:
        return Staleness.SYSTEM_CHANGED
    return Staleness.FRESH
