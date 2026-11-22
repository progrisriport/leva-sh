r"""Parse ``{{name}}`` placeholders in example commands.

A placeholder runs from ``{{`` to the first following ``}}``. ``\{{`` is a literal ``{{``.
Parsing is total: malformed placeholders stay literal text and are reported by `problems`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "EMPTY_PLACEHOLDER",
    "UNCLOSED_PLACEHOLDER",
    "Segment",
    "names",
    "parse",
    "problems",
    "to_plain",
]

EMPTY_PLACEHOLDER: Final = "empty placeholder"
UNCLOSED_PLACEHOLDER: Final = "unclosed placeholder"

_OPEN: Final = "{{"
_CLOSE: Final = "}}"
_ESCAPED_OPEN: Final = "\\{{"


@dataclass(frozen=True, slots=True)
class Segment:
    """A run of a command: literal text or the name inside a placeholder.

    Attributes:
        text: Literal text, or the placeholder name without delimiters.
        is_placeholder: True when `text` came from a ``{{...}}`` placeholder.

    Raises:
        ValueError: `text` is empty.
    """

    text: str
    is_placeholder: bool

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("Segment.text must be non-empty")


class _Scanner:
    """Single left-to-right pass that feeds both `parse` and `problems`."""

    def __init__(self, cmd: str) -> None:
        self._cmd = cmd
        self._literal: list[str] = []
        self.segments: list[Segment] = []
        self.problems: list[str] = []

    def run(self) -> None:
        pos = 0
        while pos < len(self._cmd):
            pos = self._step(pos)
        self._flush()

    def _step(self, pos: int) -> int:
        if self._cmd.startswith(_ESCAPED_OPEN, pos):
            self._literal.append(_OPEN)
            return pos + len(_ESCAPED_OPEN)
        if self._cmd.startswith(_OPEN, pos):
            return self._placeholder(pos)
        self._literal.append(self._cmd[pos])
        return pos + 1

    def _placeholder(self, start: int) -> int:
        """Handle the ``{{`` at `start`; return the position to continue from."""
        inner_start = start + len(_OPEN)
        end = self._cmd.find(_CLOSE, inner_start)
        if end == -1:
            self._literal.append(self._cmd[start:])
            self.problems.append(UNCLOSED_PLACEHOLDER)
            return len(self._cmd)
        inner = self._cmd[inner_start:end]
        if not inner.strip():
            self.problems.append(EMPTY_PLACEHOLDER)
        if inner:
            self._flush()
            self.segments.append(Segment(inner, True))
        else:
            self._literal.append(_OPEN + _CLOSE)
        return end + len(_CLOSE)

    def _flush(self) -> None:
        if self._literal:
            self.segments.append(Segment("".join(self._literal), False))
            self._literal.clear()


def _scan(cmd: str) -> _Scanner:
    scanner = _Scanner(cmd)
    scanner.run()
    return scanner


def parse(cmd: str) -> list[Segment]:
    """Split a command into literal and placeholder segments.

    Pre: any string. Post: segments are never empty, adjacent literals are merged, and
    joining the segment texts gives `cmd` with the placeholder delimiters removed. Never raises.

    Args:
        cmd: Command text, e.g. ``tar -xzf {{archive.tar.gz}}``.

    Returns:
        The segments in source order; ``[]`` for an empty command.
    """
    return _scan(cmd).segments


def to_plain(cmd: str) -> str:
    """Return `cmd` with every placeholder replaced by its bare name (``{{a}}`` -> ``a``)."""
    return "".join(segment.text for segment in parse(cmd))


def names(cmd: str) -> list[str]:
    """Return the distinct placeholder names of `cmd` in order of first appearance."""
    return list(dict.fromkeys(s.text for s in parse(cmd) if s.is_placeholder))


def problems(cmd: str) -> list[str]:
    r"""Report malformed placeholders for strict content validation.

    Args:
        cmd: Command text.

    Returns:
        In source order, `EMPTY_PLACEHOLDER` for each closed placeholder with blank inner
        text and `UNCLOSED_PLACEHOLDER` for a ``{{`` without ``}}``; ``[]`` when well formed.
        Escaped ``\{{`` never produces a problem.
    """
    return _scan(cmd).problems
