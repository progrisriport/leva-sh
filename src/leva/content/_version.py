"""Locate the bundled content and identify it: root directory, version hash, attribution text."""

from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path
from typing import Final

from leva.content._tldr_provider import TLDR_DIR
from leva.content._yaml_provider import command_files, is_curated_file
from leva.model import ContentError

_SOURCE_FILE: Final = "SOURCE.json"
_ATTRIBUTION_FILE: Final = "ATTRIBUTION.md"


def default_root() -> Path:
    """Return the directory of the bundled content (the ``leva.content`` package)."""
    return Path(__file__).resolve().parent


def content_version(root: Path) -> str:
    """Hash the curated files and the tldr source description (D-046).

    The hash covers every ``commands/*.yaml`` regular file sorted by name, then
    ``tldr/SOURCE.json`` when it exists; each file contributes its POSIX relative path, a NUL
    byte and the SHA-256 of its bytes.

    Args:
        root: Content root that holds ``commands/`` and ``tldr/``.

    Returns:
        64 lowercase hex characters; the SHA-256 of nothing when there are no such files.

    Raises:
        ContentError: If a file or the ``commands`` directory cannot be read.
    """
    files = [path for path in command_files(root) if is_curated_file(path)]
    source = root / TLDR_DIR / _SOURCE_FILE
    if source.is_file():
        files.append(source)
    digest = hashlib.sha256()
    for path in files:
        relpath = path.relative_to(root).as_posix()
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ContentError(f"{relpath}: cannot read file") from exc
        digest.update(relpath.encode() + b"\0" + hashlib.sha256(data).digest())
    return digest.hexdigest()


def attribution_text() -> str:
    """Return the bundled ``ATTRIBUTION.md``.

    Raises:
        ContentError: If the file cannot be read or decoded.
    """
    try:
        return (
            resources.files("leva.content").joinpath(_ATTRIBUTION_FILE).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError) as exc:
        raise ContentError(f"{_ATTRIBUTION_FILE}: cannot read file") from exc
