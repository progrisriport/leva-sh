"""Ports for reporting build progress and for cancelling a build cooperatively."""

from __future__ import annotations

from typing import Final, Protocol

CANCELLED: Final = "build cancelled"


class ProgressSink(Protocol):
    """Port: receive the progress of an index build (DITS §13)."""

    def phase(self, name: str, total: int | None) -> None:
        """Start a new phase of `total` units (None when unknown)."""
        ...

    def advance(self, n: int = 1) -> None:
        """Report `n` units of the current phase done."""
        ...

    def warn(self, message: str) -> None:
        """Report one non-fatal problem."""
        ...


class NullProgress:
    """A `ProgressSink` that ignores everything."""

    def phase(self, name: str, total: int | None) -> None:
        """Ignore the phase."""

    def advance(self, n: int = 1) -> None:
        """Ignore the advance."""

    def warn(self, message: str) -> None:
        """Ignore the warning."""


class CancelToken(Protocol):
    """Port: tell a running build to stop; `threading.Event` satisfies it."""

    def is_set(self) -> bool:
        """Return True once the build must stop."""
        ...
