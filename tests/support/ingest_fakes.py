"""Test doubles for the ingest pipeline: a fake renderer, progress sink and cancel token."""

from __future__ import annotations

import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path

from leva.model import ManRenderError


def rendered_page(
    name: str,
    section: str = "1",
    summary: str = "",
    *,
    names: Sequence[str] = (),
    sections: Sequence[tuple[str, str]] = (),
) -> str:
    """Return synthetic mandoc-like text that `parse_man` reads back.

    Header line, blank line, a NAME section (`names` or `name`, joined by ", ", then
    ` - <summary>` unless `summary` is empty), each extra (heading, body) with the body
    indented by five spaces per line, then a footer line.
    """
    header = f"{name.upper()}({section}) General Commands Manual {name.upper()}({section})"
    name_line = ", ".join(names or (name,))
    if summary:
        name_line = f"{name_line} - {summary}"
    lines = [header, "", "NAME", f"     {name_line}"]
    for heading, body in sections:
        lines += ["", heading, *(f"     {line}" for line in body.splitlines())]
    lines += ["", "macOS 14.0 January 1, 2026 macOS 14.0"]
    return "\n".join(lines) + "\n"


class FakeRenderer:
    """`ManRenderer` for tests; thread-safe.

    Attributes:
        calls: Rendered paths in call order, appended after `before_render` returns.
    """

    def __init__(
        self,
        texts: Mapping[Path, str] | None = None,
        *,
        failing: Collection[Path] = (),
        before_render: Callable[[Path], None] | None = None,
    ) -> None:
        self._texts = dict(texts or {})
        self._failing = frozenset(failing)
        self._before_render = before_render
        self._lock = threading.Lock()
        self.calls: list[Path] = []

    def render(self, path: Path) -> str:
        """Run the hook, record the call, then fail or return the text of `path`."""
        if self._before_render is not None:
            self._before_render(path)
        with self._lock:
            self.calls.append(path)
        if path in self._failing:
            raise ManRenderError(f"mandoc failed: {path}")
        if path in self._texts:
            return self._texts[path]
        return rendered_page(path.name.removesuffix(".gz").rpartition(".")[0])


class RecordingProgress:
    """`ProgressSink` that records every call; hooks let a test act in the middle of a build.

    Attributes:
        events: ``("phase", (name, total))``, ``("advance", n)`` and ``("warn", message)``.
    """

    def __init__(
        self,
        *,
        on_phase: Callable[[str, int | None], None] | None = None,
        on_advance: Callable[[int], None] | None = None,
    ) -> None:
        self.events: list[tuple[str, object]] = []
        self._on_phase = on_phase
        self._on_advance = on_advance

    def phase(self, name: str, total: int | None) -> None:
        self.events.append(("phase", (name, total)))
        if self._on_phase is not None:
            self._on_phase(name, total)

    def advance(self, n: int = 1) -> None:
        self.events.append(("advance", n))
        if self._on_advance is not None:
            self._on_advance(n)

    def warn(self, message: str) -> None:
        self.events.append(("warn", message))


class FakeCancel:
    """`CancelToken` driven by hand."""

    def __init__(self) -> None:
        self.flag = False

    def set(self) -> None:
        self.flag = True

    def is_set(self) -> bool:
        return self.flag
