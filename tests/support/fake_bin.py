"""Write fake executables (``/bin/sh`` scripts) for tests that spawn subprocesses."""

from __future__ import annotations

from pathlib import Path

SHEBANG = "#!/bin/sh\n"


def fake_bin(directory: Path, name: str, script: str) -> Path:
    """Write the executable ``/bin/sh`` script ``directory/name`` and return its path.

    Args:
        directory: Directory to write into; created with its parents when missing.
        name: Bare file name of the executable, e.g. ``pbcopy`` or ``[``.
        script: Shell script body; the ``#!/bin/sh`` line is prepended and a final newline
            is added when missing.

    Returns:
        The script path, with mode ``0o755``. An existing file of that name is replaced.

    Raises:
        ValueError: If ``name`` is empty, ``.``, ``..`` or contains ``/``.
    """
    if name in {"", ".", ".."} or "/" in name:
        raise ValueError(f"fake_bin name must be a bare file name, got {name!r}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    body = script if script.endswith("\n") else f"{script}\n"
    path.write_text(SHEBANG + body, encoding="utf-8")
    path.chmod(0o755)
    return path
