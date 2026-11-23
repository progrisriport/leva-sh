"""Read man page sources and detect ``.so`` stub pages."""

from __future__ import annotations

import gzip
import zlib
from pathlib import Path
from typing import Final

from leva.model import ManRenderError

_COMMENT_PREFIXES: Final = ('.\\"', "'\\\"", ".\\#")


def read_man_source(path: Path) -> str:
    """Return the roff source of the man page at `path`, decompressing ``.gz`` files.

    Invalid UTF-8 is replaced by U+FFFD.

    Raises:
        ManRenderError: The file is missing, unreadable, or not valid or complete gzip.
    """
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rb") as handle:
                data = handle.read()
        else:
            data = path.read_bytes()
    except (OSError, EOFError, zlib.error) as exc:
        raise ManRenderError(f"cannot read man page: {path}") from exc
    return data.decode("utf-8", errors="replace")


def stub_target(source: str) -> str | None:
    """Return the raw ``.so`` argument when the first roff request of `source` is ``.so``.

    Blank lines, a lone ``.`` and roff comments before the first request are skipped.
    The argument is returned as written (not resolved against the man root).

    Returns:
        The argument, or None when the page is not a stub or the ``.so`` has no argument.
    """
    for line in source.splitlines():
        stripped = line.strip()
        if stripped in {"", "."} or stripped.startswith(_COMMENT_PREFIXES):
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) == 2 and parts[0] == ".so":
            return parts[1].strip()
        return None
    return None
