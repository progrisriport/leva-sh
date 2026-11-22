"""Immutable shared domain types and the ``LevaError`` hierarchy."""

from __future__ import annotations

from leva.model._errors import (
    ClipboardError,
    ConfigError,
    ContentError,
    IndexUnavailableError,
    IngestError,
    LevaError,
    ManRenderError,
    VerificationError,
)
from leva.model._types import (
    Entry,
    Example,
    ExampleSource,
    Kind,
    Note,
    NoteKind,
    Origin,
    Section,
    Subcommand,
    Verification,
)

__all__ = [
    "ClipboardError",
    "ConfigError",
    "ContentError",
    "Entry",
    "Example",
    "ExampleSource",
    "IndexUnavailableError",
    "IngestError",
    "Kind",
    "LevaError",
    "ManRenderError",
    "Note",
    "NoteKind",
    "Origin",
    "Section",
    "Subcommand",
    "Verification",
    "VerificationError",
]
