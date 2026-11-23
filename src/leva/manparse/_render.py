"""Render man pages to plain text through ``mandoc``."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from types import MappingProxyType
from typing import Final, Protocol

from leva.manparse._overstrike import strip_overstrike
from leva.model import ManRenderError

_MIN_BODY_LINES: Final = 3
_log = logging.getLogger("leva.manparse")


class ManRenderer(Protocol):
    """Port: render one man page file to plain text."""

    def render(self, path: Path) -> str:
        """Return the rendered text of the man page at `path`.

        Raises:
            ManRenderError: The page cannot be rendered or renders to nothing.
        """
        ...


def _has_body(text: str) -> bool:
    """Tell whether `text` has a line between its header and footer."""
    return sum(1 for line in text.splitlines() if line.strip()) >= _MIN_BODY_LINES


class MandocRenderer:
    """`ManRenderer` adapter that runs ``mandoc -T ascii`` from the page's man root."""

    def __init__(
        self, binary: str = "/usr/bin/mandoc", width: int = 80, timeout: float = 10.0
    ) -> None:
        """Configure the adapter.

        Args:
            binary: Path of the ``mandoc`` executable.
            width: Output width in columns, also exported as ``MANWIDTH``.
            timeout: Seconds to wait for one page.

        Raises:
            ValueError: `width` or `timeout` is not positive.
        """
        if width <= 0:
            raise ValueError(f"render width must be positive, got {width}")
        if timeout <= 0:
            raise ValueError(f"render timeout must be positive, got {timeout}")
        self._binary = binary
        self._width = width
        self._timeout = timeout
        self._env = MappingProxyType(
            {
                "LC_ALL": "en_US.UTF-8",
                "LANG": "en_US.UTF-8",
                "MANWIDTH": str(width),
                "TZ": "UTC",
            }
        )

    def _run(self, path: Path) -> subprocess.CompletedProcess[bytes]:
        """Run mandoc on `path` with the man root (`path.parent.parent`) as cwd."""
        argv = [self._binary, "-T", "ascii", "-O", f"width={self._width}", str(path)]
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            cwd=path.parent.parent,
            env=self._env,
            timeout=self._timeout,
            check=False,
        )

    def render(self, path: Path) -> str:
        """Render `path` to text, overstrike removed, header and footer kept.

        mandoc exits 0 for empty, garbage or ``.so``-broken input, so an output with no
        line between the header and the footer counts as a failure.

        Raises:
            ManRenderError: mandoc cannot run, exits non-zero, times out, or the output
                has fewer than three non-blank lines.
        """
        try:
            result = self._run(path)
        except subprocess.TimeoutExpired as exc:
            _log.debug("mandoc timed out after %ss: %s", self._timeout, path)
            raise ManRenderError(f"mandoc timed out: {path}") from exc
        except OSError as exc:
            _log.debug("mandoc could not run on %s: %s", path, exc)
            raise ManRenderError(f"mandoc failed: {path}") from exc
        if result.returncode != 0:
            first = result.stderr.decode("utf-8", errors="replace").partition("\n")[0]
            _log.debug("mandoc exited %d on %s: %s", result.returncode, path, first)
            raise ManRenderError(f"mandoc failed: {path}")
        text = strip_overstrike(result.stdout.decode("utf-8", errors="replace"))
        if not _has_body(text):
            raise ManRenderError(f"empty man page: {path}")
        return text
