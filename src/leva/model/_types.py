"""Immutable domain value objects shared by every package, with runtime invariants."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias, get_args

ExampleSource: TypeAlias = Literal["curated", "tldr"]
Verification: TypeAlias = Literal["exec", "static", "skip", "none"]
NoteKind: TypeAlias = Literal["bsd-gnu", "zsh-bash", "macos", "safety"]

_EXAMPLE_SOURCES: tuple[str, ...] = get_args(ExampleSource)
_VERIFICATIONS: tuple[str, ...] = get_args(Verification)
_NOTE_KINDS: tuple[str, ...] = get_args(NoteKind)


class Origin(StrEnum):
    """Where a command comes from."""

    MACOS = "macos"
    HOMEBREW = "homebrew"
    ZSH = "zsh"
    BASH = "bash"


class Kind(StrEnum):
    """What an index entry is."""

    EXECUTABLE = "executable"
    BUILTIN = "builtin"
    MANPAGE_ONLY = "manpage"


def is_name(value: str) -> bool:
    """Tell whether `value` can be an entry, section, example or subcommand name (D-033).

    Post: true exactly when `value` is non-empty and holds no `str.isspace()` character.
    """
    return value != "" and not any(char.isspace() for char in value)


def _check_name(owner: str, field: str, value: str) -> None:
    if not is_name(value):
        raise ValueError(f"{owner}.{field} must be non-empty without whitespace: {value!r}")


def _check_optional_name(owner: str, field: str, value: str | None) -> None:
    if value is not None:
        _check_name(owner, field, value)


def _check_choice(owner: str, field: str, value: str, choices: tuple[str, ...]) -> None:
    if value not in choices:
        raise ValueError(f"{owner}.{field} must be one of {', '.join(choices)}: {value!r}")


def _check_member(owner: str, field: str, value: object, enum_type: type[StrEnum]) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(f"{owner}.{field} must be a {enum_type.__name__} member: {value!r}")


def _check_non_blank(owner: str, field: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{owner}.{field} must not be blank: {value!r}")


def _check_cmd(value: str) -> None:
    _check_non_blank("Example", "cmd", value)
    if "\r" in value:
        raise ValueError(f"Example.cmd must not contain a carriage return: {value!r}")
    if value.endswith("\n"):
        raise ValueError(f"Example.cmd must not end with a newline: {value!r}")
    for index, char in enumerate(value):
        if char == "\n" and value[index - 1 : index] != "\\":
            raise ValueError(f"Example.cmd newline must follow a backslash: {value!r}")


def _check_danger(value: str | None) -> None:
    if value is None:
        return
    _check_non_blank("Example", "danger", value)
    if "\n" in value or "\r" in value:
        raise ValueError(f"Example.danger must be a single line: {value!r}")


@dataclass(frozen=True, slots=True)
class Entry:
    """A command, builtin or man page in the index.

    Attributes:
        id: Index row id.
        name: Command name.
        section: Man section such as ``1`` or ``3pm``, or ``None``.
        kind: What the entry is.
        origin: Where it comes from.
        summary: One-line description, ``""`` when absent.
        path: Path of the binary, or ``None``.
        has_man: Whether a man page exists.
        curated: Whether curated content exists.

    Raises:
        ValueError: If ``name`` or a set ``section`` is empty or contains whitespace, or if
            ``kind`` or ``origin`` is not an enum member (convert with ``Kind(value)``).
    """

    id: int
    name: str
    section: str | None
    kind: Kind
    origin: Origin
    summary: str
    path: str | None
    has_man: bool
    curated: bool

    def __post_init__(self) -> None:
        _check_name("Entry", "name", self.name)
        _check_optional_name("Entry", "section", self.section)
        _check_member("Entry", "kind", self.kind, Kind)
        _check_member("Entry", "origin", self.origin, Origin)


@dataclass(frozen=True, slots=True)
class Section:
    """A heading and body of a man page.

    Attributes:
        heading: Section heading; may be empty.
        body: Section text; may be empty.
        ord: Position in the page, starting at 0.

    Raises:
        ValueError: If ``ord`` is negative.
    """

    heading: str
    body: str
    ord: int

    def __post_init__(self) -> None:
        if self.ord < 0:
            raise ValueError(f"Section.ord must be >= 0: {self.ord!r}")


@dataclass(frozen=True, slots=True)
class Example:
    """A copyable example command.

    Attributes:
        id: Identifier like ``<command>-<slug>``.
        desc: What the example does.
        cmd: The command, possibly with ``{{placeholder}}`` parts.
        source: Where the example comes from.
        verified: How it was verified.
        danger: Specific reason the command is destructive, or ``None``.

    Raises:
        ValueError: If ``id`` is not a name, ``cmd`` is blank, contains a carriage return,
            ends with a newline or has a newline not preceded by a backslash, ``source`` or
            ``verified`` is not an allowed value, or ``danger`` is blank or spans several lines.
    """

    id: str
    desc: str
    cmd: str
    source: ExampleSource
    verified: Verification
    danger: str | None = None

    def __post_init__(self) -> None:
        _check_name("Example", "id", self.id)
        _check_cmd(self.cmd)
        _check_choice("Example", "source", self.source, _EXAMPLE_SOURCES)
        _check_choice("Example", "verified", self.verified, _VERIFICATIONS)
        _check_danger(self.danger)


@dataclass(frozen=True, slots=True)
class Note:
    """A caveat attached to a command.

    Attributes:
        kind: Category of the note.
        text: The note text.

    Raises:
        ValueError: If ``kind`` is not an allowed value.
    """

    kind: NoteKind
    text: str

    def __post_init__(self) -> None:
        _check_choice("Note", "kind", self.kind, _NOTE_KINDS)


@dataclass(frozen=True, slots=True)
class Subcommand:
    """A subcommand of a command, such as ``commit`` of ``git``.

    Attributes:
        name: Subcommand name.
        summary: One-line description; may be empty.
        entry_name: Name of the entry holding its own man page, or ``None``.
        source: How it was found; ingest decides the values.
        body: Longer description; may be empty.

    Raises:
        ValueError: If ``name`` or a set ``entry_name`` is empty or contains whitespace, or if
            ``source`` is blank.
    """

    name: str
    summary: str
    entry_name: str | None
    source: str
    body: str = ""

    def __post_init__(self) -> None:
        _check_name("Subcommand", "name", self.name)
        _check_optional_name("Subcommand", "entry_name", self.entry_name)
        _check_non_blank("Subcommand", "source", self.source)
