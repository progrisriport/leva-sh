"""Validated content records: curated commands, tldr pages and their parts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal, TypeAlias, get_args

from leva.model import Example, Note, Subcommand, is_name

VerifyMode: TypeAlias = Literal["exec", "static", "skip"]

VERIFY_MODES: Final[tuple[str, ...]] = get_args(VerifyMode)
# Own copy of `leva.subcmd.HELP_PROFILES`: content and subcmd are independent layers (a test
# asserts both are equal).
HELP_PROFILES: Final[tuple[str, ...]] = ("two-col", "git-list", "brew-commands")
TLDR_PLATFORMS: Final[tuple[str, ...]] = ("common", "osx")


def _check_choice(owner: str, name: str, value: str, choices: tuple[str, ...]) -> None:
    if value not in choices:
        raise ValueError(f"{owner}.{name} must be one of {', '.join(choices)}: {value!r}")


def _check_name(owner: str, name: str, value: str) -> None:
    if not is_name(value):
        raise ValueError(f"{owner}.{name} must be non-empty without whitespace: {value!r}")


@dataclass(frozen=True, slots=True)
class VerifySpec:
    """How one curated example is verified (D-010).

    Attributes:
        mode: ``exec`` runs it in the sandbox, ``static`` only checks it, ``skip`` never runs it.
        setup: Shell script that prepares the sandbox; exec only.
        bind: Value for each placeholder of the command, as a read-only copy; exec only.
        expect_exit: Expected exit status; exec only.
        stdout_contains: Substrings the output must contain; exec only.
        stdout_regex: Regular expression the output must match; exec only.
        files_exist: Sandbox-relative paths that must exist afterwards; exec only.
        reason: Why the example is not run or what it needs.
        min_macos: Minimum macOS version such as ``14`` or ``14.2``.

    Raises:
        ValueError: If ``mode`` is not one of `VERIFY_MODES`.
    """

    mode: VerifyMode
    setup: str = ""
    bind: Mapping[str, str] = field(default_factory=dict)
    expect_exit: int = 0
    stdout_contains: tuple[str, ...] = ()
    stdout_regex: str | None = None
    files_exist: tuple[str, ...] = ()
    reason: str | None = None
    min_macos: str | None = None

    def __post_init__(self) -> None:
        _check_choice("VerifySpec", "mode", self.mode, VERIFY_MODES)
        object.__setattr__(self, "bind", MappingProxyType(dict(self.bind)))


@dataclass(frozen=True, slots=True)
class ExampleSpec:
    """A curated example with its verification.

    Attributes:
        id: Identifier like ``<command>-<slug>``.
        desc: What the example does.
        cmd: The command, possibly with ``{{placeholder}}`` parts.
        verify: How it is verified.
        danger: Specific reason the command is destructive, or ``None``.

    Raises:
        ValueError: If ``id`` is empty or contains whitespace.
    """

    id: str
    desc: str
    cmd: str
    verify: VerifySpec
    danger: str | None = None

    def __post_init__(self) -> None:
        _check_name("ExampleSpec", "id", self.id)

    def to_example(self) -> Example:
        """Convert to the shared `Example` type.

        Post: source ``curated``, ``verified`` equal to the verify mode.

        Raises:
            ValueError: If ``cmd`` or ``danger`` break the `Example` invariants (D-033);
                `validate_command` rules this out.
        """
        return Example(self.id, self.desc, self.cmd, "curated", self.verify.mode, self.danger)


@dataclass(frozen=True, slots=True)
class HelpProbe:
    """The allowlisted help invocation of a command and how to read its output (D-009).

    Attributes:
        args: Arguments passed to the command; none contains whitespace.
        profile: One of `HELP_PROFILES`.

    Raises:
        ValueError: If ``args`` is empty or has an empty item, or ``profile`` is unknown.
    """

    args: tuple[str, ...]
    profile: str

    def __post_init__(self) -> None:
        if not self.args or not all(self.args):
            raise ValueError(
                f"HelpProbe.args must be non-empty with non-empty items: {self.args!r}"
            )
        _check_choice("HelpProbe", "profile", self.profile, HELP_PROFILES)


@dataclass(frozen=True, slots=True)
class CuratedCommand:
    """One validated ``commands/<name>.yaml`` document.

    Attributes:
        name: Command name, equal to the file stem.
        section: Man section such as ``1``, or ``None``.
        summary: One-line description, at most 120 characters.
        explain: Longer explanation.
        intents: Phrases a user might search for; at least one.
        tags: Free-form tags.
        notes: Caveats such as BSD-versus-GNU differences.
        examples: Curated examples with their verification.
        subcommands: Curated subcommands; ``source`` is ``curated``.
        related: Names of related commands.
        help_probe: How to read the help text of the command, or ``None``.

    Raises:
        ValueError: If ``name`` is empty or contains whitespace.
    """

    name: str
    section: str | None
    summary: str
    explain: str
    intents: tuple[str, ...]
    tags: tuple[str, ...]
    notes: tuple[Note, ...]
    examples: tuple[ExampleSpec, ...]
    subcommands: tuple[Subcommand, ...]
    related: tuple[str, ...]
    help_probe: HelpProbe | None

    def __post_init__(self) -> None:
        _check_name("CuratedCommand", "name", self.name)


@dataclass(frozen=True, slots=True)
class TldrExample:
    """One example of a tldr page.

    Attributes:
        desc: What the command does.
        cmd: The command text.
    """

    desc: str
    cmd: str


@dataclass(frozen=True, slots=True)
class TldrPage:
    """One page of the vendored tldr snapshot.

    Attributes:
        name: Command name.
        platform: One of `TLDR_PLATFORMS`.
        description: Page description; may be empty.
        examples: The page examples in order.

    Raises:
        ValueError: If ``name`` is empty or contains whitespace or ``platform`` is unknown.
    """

    name: str
    platform: str
    description: str
    examples: tuple[TldrExample, ...]

    def __post_init__(self) -> None:
        _check_name("TldrPage", "name", self.name)
        _check_choice("TldrPage", "platform", self.platform, TLDR_PLATFORMS)

    def to_examples(self) -> tuple[Example, ...]:
        """Convert to shared `Example` values, one per tldr example (D-017).

        Post: ids ``<name>-tldr-<n>`` with ``n`` from 1, source ``tldr``, verified ``none``.

        Raises:
            ValueError: If a command breaks the `Example` invariants (D-033); the tldr provider
                drops such examples before it builds the page.
        """
        return tuple(
            Example(f"{self.name}-tldr-{number}", item.desc, item.cmd, "tldr", "none")
            for number, item in enumerate(self.examples, start=1)
        )


ContentRecord: TypeAlias = CuratedCommand | TldrPage
