"""The ``LevaError`` hierarchy: user-facing failures that cross package boundaries."""

from __future__ import annotations


class LevaError(Exception):
    """Base of user-facing failures.

    Attributes:
        message: Short, displayable description of what went wrong.
        hint: Suggested action for the user, or ``None``.
    """

    message: str
    hint: str | None

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        return self.message


class IngestError(LevaError):
    """Building or updating the index failed."""


class ManRenderError(LevaError):
    """Rendering a man page to text failed."""


class ContentError(LevaError):
    """Curated or tldr content is invalid; messages read ``file:field: reason``."""


class IndexUnavailableError(LevaError):
    """The index is missing, unreadable or has an unsupported schema version."""


class ClipboardError(LevaError):
    """Copying to the system clipboard failed."""


class VerificationError(LevaError):
    """Verifying a curated example in the sandbox failed."""


class ConfigError(LevaError):
    """``config.toml`` is unreadable or holds an invalid value."""
