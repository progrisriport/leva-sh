"""Copy text to the system clipboard."""

from __future__ import annotations

import logging
import subprocess
from types import MappingProxyType
from typing import Final, Protocol

from leva.model import ClipboardError

__all__ = ["MAX_TEXT_BYTES", "Clipboard", "FakeClipboard", "PbcopyClipboard"]

MAX_TEXT_BYTES: Final = 65_536
_UNAVAILABLE: Final = "clipboard unavailable"

_PBCOPY_ENV: Final = MappingProxyType({"LANG": "en_US.UTF-8", "LC_CTYPE": "en_US.UTF-8"})

_log = logging.getLogger("leva.clipboard")


class Clipboard(Protocol):
    """Port: put text on the system clipboard."""

    def copy(self, text: str) -> None:
        """Replace the clipboard content with `text`.

        Pre: `text` is non-empty and at most `MAX_TEXT_BYTES` bytes in UTF-8.
        Post: the clipboard holds exactly `text`.

        Raises:
            ValueError: `text` is empty or too long.
            ClipboardError: The clipboard cannot be written.
        """
        ...


def _check_text(text: str) -> None:
    """Raise `ValueError` unless `text` meets the `Clipboard.copy` precondition."""
    if text == "":
        raise ValueError("clipboard text must not be empty")
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("clipboard text exceeds 64 KiB")


class PbcopyClipboard:
    """`Clipboard` adapter that pipes the text into macOS ``pbcopy``."""

    def __init__(self, *, binary: str = "/usr/bin/pbcopy", timeout: float = 2.0) -> None:
        """Configure the adapter.

        Args:
            binary: Path of the ``pbcopy`` executable.
            timeout: Seconds to wait for it to finish.

        Raises:
            ValueError: `timeout` is not positive.
        """
        if timeout <= 0:
            raise ValueError(f"clipboard timeout must be positive, got {timeout}")
        self._binary = binary
        self._timeout = timeout

    def copy(self, text: str) -> None:
        """Copy `text` through ``pbcopy`` (UTF-8 on stdin, minimal environment).

        Raises:
            ValueError: `text` is empty or over `MAX_TEXT_BYTES` bytes.
            ClipboardError: The binary cannot run, times out or exits non-zero.
        """
        _check_text(text)
        try:
            result = subprocess.run(
                [self._binary],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=_PBCOPY_ENV,
                timeout=self._timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            _log.debug("pbcopy failed: %s", exc)
            raise ClipboardError(_UNAVAILABLE) from exc
        if result.returncode != 0:
            _log.debug("pbcopy exited with status %d", result.returncode)
            raise ClipboardError(_UNAVAILABLE)


class FakeClipboard:
    """In-memory `Clipboard` for tests; records successful copies.

    Attributes:
        fail: When true, `copy` raises `ClipboardError` and records nothing.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self._history: list[str] = []

    @property
    def last(self) -> str | None:
        """The most recent successful copy, or None before the first one."""
        return self._history[-1] if self._history else None

    @property
    def history(self) -> tuple[str, ...]:
        """Successful copies, oldest first (a snapshot)."""
        return tuple(self._history)

    def copy(self, text: str) -> None:
        """Record `text`, with the same preconditions as `PbcopyClipboard.copy`.

        Raises:
            ValueError: `text` is empty or over `MAX_TEXT_BYTES` bytes.
            ClipboardError: `fail` is set.
        """
        _check_text(text)
        if self.fail:
            raise ClipboardError(_UNAVAILABLE)
        self._history.append(text)
