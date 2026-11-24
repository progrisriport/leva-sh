"""Load and strictly validate curated YAML and the tldr snapshot; content version; attribution."""

from __future__ import annotations

from leva.content._policy import EXEC_DENYLIST, is_destructive
from leva.content._schema import (
    HELP_PROFILES,
    TLDR_PLATFORMS,
    VERIFY_MODES,
    ContentRecord,
    CuratedCommand,
    ExampleSpec,
    HelpProbe,
    TldrExample,
    TldrPage,
    VerifyMode,
    VerifySpec,
)
from leva.content._validate import validate_command

__all__ = [
    "EXEC_DENYLIST",
    "HELP_PROFILES",
    "TLDR_PLATFORMS",
    "VERIFY_MODES",
    "ContentRecord",
    "CuratedCommand",
    "ExampleSpec",
    "HelpProbe",
    "TldrExample",
    "TldrPage",
    "VerifyMode",
    "VerifySpec",
    "is_destructive",
    "validate_command",
]
