"""Strict validation of one parsed curated YAML document (D-010, D-016, D-030, D-033)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final, get_args

from leva import placeholders
from leva.content._policy import EXEC_DENYLIST, is_destructive, simple_commands
from leva.content._schema import (
    HELP_PROFILES,
    CuratedCommand,
    ExampleSpec,
    HelpProbe,
    VerifyMode,
    VerifySpec,
)
from leva.model import ContentError, Note, NoteKind, Subcommand, is_name

_TOP_KEYS: Final = (
    "schema",
    "kind",
    "name",
    "section",
    "summary",
    "explain",
    "intents",
    "tags",
    "notes",
    "examples",
    "subcommands",
    "related",
    "help_probe",
)
_NOTE_KEYS: Final = ("kind", "text")
_EXAMPLE_KEYS: Final = ("id", "desc", "cmd", "danger", "verify")
_VERIFY_KEYS: Final = (
    "mode",
    "setup",
    "bind",
    "expect_exit",
    "stdout_contains",
    "stdout_regex",
    "files_exist",
    "reason",
    "min_macos",
)
_EXEC_ONLY_KEYS: Final = frozenset(
    {"setup", "bind", "expect_exit", "stdout_contains", "stdout_regex", "files_exist"}
)
_SUBCOMMAND_KEYS: Final = ("name", "summary", "body", "entry_name")
_HELP_PROBE_KEYS: Final = ("args", "profile")

_SCHEMA_VERSION: Final = 1
_KIND: Final = "command"
_MAX_SUMMARY: Final = 120
_MAX_EXIT: Final = 255
_RESERVED_SLUG: Final = "tldr-"
_SECTION: Final = re.compile(r"[a-z0-9]+")
_MIN_MACOS: Final = re.compile(r"[0-9]+(\.[0-9]+){0,2}")
_NOTE_KINDS: Final[dict[str, NoteKind]] = {kind: kind for kind in get_args(NoteKind)}
_VERIFY_MODES: Final[dict[str, VerifyMode]] = {mode: mode for mode in get_args(VerifyMode)}
_UNSPLITTABLE: Final = "cannot be split into words (unbalanced quote or trailing escape)"
_MISSING: Final = object()


@dataclass(frozen=True, slots=True)
class _At:
    """A location in the document, used to build ``file:path: reason`` messages."""

    file: str
    path: str = ""

    def key(self, name: object) -> _At:
        return _At(self.file, f"{self.path}.{name}" if self.path else str(name))

    def item(self, index: int) -> _At:
        return _At(self.file, f"{self.path}[{index}]")

    def fail(self, reason: str) -> ContentError:
        head = f"{self.file}:{self.path}" if self.path else self.file
        return ContentError(f"{head}: {reason}")


class _Fields:
    """A mapping whose keys were checked against an allowed set."""

    def __init__(self, at: _At, value: object, allowed: tuple[str, ...]) -> None:
        if not isinstance(value, dict):
            raise at.fail("must be a mapping")
        for key in value:
            if key not in allowed:
                raise at.fail(f"unknown key {key!r}")
        self.at = at
        self._data: dict[object, object] = value

    def __iter__(self) -> Iterator[object]:
        return iter(self._data)

    def get(self, key: str) -> object:
        """Return the value of `key`, or `_MISSING`."""
        return self._data.get(key, _MISSING)

    def require(self, key: str) -> object:
        value = self.get(key)
        if value is _MISSING:
            raise self.at.key(key).fail("required")
        return value


def _string(at: _At, value: object) -> str:
    if not isinstance(value, str):
        raise at.fail("must be a string")
    return value


def _multiline(at: _At, value: object) -> str:
    text = _string(at, value).strip()
    if not text:
        raise at.fail("must not be blank")
    return text


def _line(at: _At, value: object) -> str:
    text = _multiline(at, value)
    if len(text.splitlines()) != 1:
        raise at.fail("must be a single line")
    return text


def _name(at: _At, value: object) -> str:
    text = _string(at, value)
    if not is_name(text):
        raise at.fail("must not contain whitespace")
    return text


def _list(at: _At, value: object) -> list[object]:
    if not isinstance(value, list):
        raise at.fail("must be a list")
    return value


def _items(at: _At, value: object) -> Iterator[tuple[_At, object]]:
    for index, item in enumerate(_list(at, value)):
        yield at.item(index), item


def _integer(at: _At, value: object) -> int:
    if type(value) is not int:
        raise at.fail("must be an integer")
    return value


def _choice(at: _At, value: object, choices: tuple[str, ...]) -> str:
    text = _string(at, value)
    if text not in choices:
        raise at.fail(f"must be one of {', '.join(choices)}")
    return text


def _unique(at: _At, seen: set[str], key: str, label: str) -> None:
    if key in seen:
        raise at.fail(f"duplicate {label}")
    seen.add(key)


def _lines(at: _At, value: object, label: str) -> tuple[str, ...]:
    """Read a list of single-line texts that are unique ignoring case."""
    seen: set[str] = set()
    texts: list[str] = []
    for item_at, item in _items(at, value):
        text = _line(item_at, item)
        _unique(item_at, seen, text.casefold(), label)
        texts.append(text)
    return tuple(texts)


def _intents(at: _At, value: object) -> tuple[str, ...]:
    if not _list(at, value):
        raise at.fail("must not be empty")
    return _lines(at, value, "intent")


def _check_header(at: _At, data: object) -> dict[object, object]:
    if not isinstance(data, dict):
        raise at.fail("expected a mapping")
    if "schema" not in data:
        raise at.key("schema").fail("required")
    schema = data["schema"]
    if type(schema) is not int or schema != _SCHEMA_VERSION:
        raise at.key("schema").fail(f"unsupported schema {schema!r} (expected {_SCHEMA_VERSION})")
    if "kind" not in data:
        raise at.key("kind").fail("required")
    kind = _string(at.key("kind"), data["kind"])
    if kind != _KIND:
        raise at.key("kind").fail(f"{kind!r} not supported in schema {_SCHEMA_VERSION}")
    return data


def _command_name(fields: _Fields) -> str:
    at = fields.at.key("name")
    name = _name(at, fields.require("name"))
    stem = PurePosixPath(fields.at.file).stem
    if name != stem:
        raise at.fail(f"must equal the file name {stem!r}")
    return name


def _section(fields: _Fields) -> str | None:
    value = fields.get("section")
    if value is _MISSING:
        return None
    at = fields.at.key("section")
    section = _string(at, value)
    if not _SECTION.fullmatch(section):
        raise at.fail("must match [a-z0-9]+")
    return section


def _summary(fields: _Fields) -> str:
    at = fields.at.key("summary")
    summary = _line(at, fields.require("summary"))
    if len(summary) > _MAX_SUMMARY:
        raise at.fail(f"longer than {_MAX_SUMMARY} characters")
    return summary


def _tags(fields: _Fields) -> tuple[str, ...]:
    value = fields.get("tags")
    return () if value is _MISSING else _lines(fields.at.key("tags"), value, "tag")


def _note(at: _At, value: object) -> Note:
    fields = _Fields(at, value, _NOTE_KEYS)
    kind_at = at.key("kind")
    kind = _string(kind_at, fields.require("kind"))
    if kind not in _NOTE_KINDS:
        raise kind_at.fail(f"must be one of {', '.join(_NOTE_KINDS)}")
    return Note(_NOTE_KINDS[kind], _multiline(at.key("text"), fields.require("text")))


def _notes(fields: _Fields) -> tuple[Note, ...]:
    value = fields.get("notes")
    if value is _MISSING:
        return ()
    return tuple(_note(at, item) for at, item in _items(fields.at.key("notes"), value))


def _example_id(fields: _Fields, name: str, seen: set[str]) -> str:
    at = fields.at.key("id")
    example_id = _string(at, fields.require("id"))
    slug = re.fullmatch(f"{re.escape(name)}-([a-z0-9-]+)", example_id)
    if slug is None:
        raise at.fail(f"must look like {name}-<slug> (lowercase letters, digits, hyphens)")
    if slug.group(1).startswith(_RESERVED_SLUG):
        raise at.fail(f"slug '{_RESERVED_SLUG}...' is reserved")
    if example_id in seen:
        raise at.fail(f"duplicate example id {example_id!r}")
    seen.add(example_id)
    return example_id


def _cmd(at: _At, value: object) -> str:
    cmd = _string(at, value).strip()
    if not cmd:
        raise at.fail("must not be blank")
    if "\r" in cmd:
        raise at.fail("must not contain a carriage return")
    if re.search(r"(?<!\\)\n", cmd):
        raise at.fail("newline must follow a backslash")
    if cmd.endswith("\\"):
        raise at.fail("must not end with a backslash")
    problems = placeholders.problems(cmd)
    if problems:
        raise at.fail(problems[0])
    _split(at, cmd)
    return cmd


def _split(at: _At, text: str) -> list[tuple[str, ...]]:
    try:
        return simple_commands(text)
    except ValueError:
        raise at.fail(_UNSPLITTABLE) from None


def _denied_word(at: _At, text: str) -> str | None:
    return next((argv[0] for argv in _split(at, text) if argv[0] in EXEC_DENYLIST), None)


def _danger(fields: _Fields, cmd: str) -> str | None:
    at = fields.at.key("danger")
    value = fields.get("danger")
    if value is not _MISSING:
        return _line(at, value)
    if is_destructive(cmd):
        raise at.fail("required, the command is destructive (D-030)")
    return None


def _example(at: _At, value: object, name: str, seen: set[str]) -> ExampleSpec:
    fields = _Fields(at, value, _EXAMPLE_KEYS)
    example_id = _example_id(fields, name, seen)
    desc = _line(at.key("desc"), fields.require("desc"))
    cmd = _cmd(at.key("cmd"), fields.require("cmd"))
    danger = _danger(fields, cmd)
    verify = _verify(at.key("verify"), fields.require("verify"), cmd)
    return ExampleSpec(example_id, desc, cmd, verify, danger)


def _examples(fields: _Fields, name: str) -> tuple[ExampleSpec, ...]:
    value = fields.get("examples")
    if value is _MISSING:
        return ()
    seen: set[str] = set()
    return tuple(
        _example(at, item, name, seen) for at, item in _items(fields.at.key("examples"), value)
    )


def _check_exec_only(fields: _Fields, mode: VerifyMode) -> None:
    if mode == "exec":
        return
    for key in fields:
        if key in _EXEC_ONLY_KEYS:
            raise fields.at.key(key).fail("only valid with mode exec")


def _setup(fields: _Fields) -> str:
    value = fields.get("setup")
    if value is _MISSING:
        return ""
    at = fields.at.key("setup")
    setup = _string(at, value).strip()
    denied = _denied_word(at, setup)
    if denied is not None:
        raise at.fail(f"{denied!r} is on the exec denylist (D-016)")
    return setup


def _bind(fields: _Fields, cmd: str) -> dict[str, str]:
    """Read ``bind``: it must hold a value for exactly the placeholders of `cmd`."""
    at = fields.at.key("bind")
    value = fields.get("bind")
    if value is _MISSING:
        value = {}
    if not isinstance(value, dict):
        raise at.fail("must be a mapping")
    texts = {key: _string(at.key(key), item) for key, item in value.items()}
    wanted = placeholders.names(cmd)
    for name in wanted:
        if name not in texts:
            raise at.fail(f"missing placeholder {name!r}")
    for key in texts:
        if key not in wanted:
            raise at.fail(f"unknown placeholder {key!r}")
    return {name: texts[name] for name in wanted}


def _expect_exit(fields: _Fields) -> int:
    value = fields.get("expect_exit")
    if value is _MISSING:
        return 0
    at = fields.at.key("expect_exit")
    code = _integer(at, value)
    if not 0 <= code <= _MAX_EXIT:
        raise at.fail(f"must be between 0 and {_MAX_EXIT}")
    return code


def _stdout_contains(fields: _Fields) -> tuple[str, ...]:
    value = fields.get("stdout_contains")
    if value is _MISSING:
        return ()
    texts: list[str] = []
    for at, item in _items(fields.at.key("stdout_contains"), value):
        text = _string(at, item)
        if not text:
            raise at.fail("must not be empty")
        texts.append(text)
    return tuple(texts)


def _stdout_regex(fields: _Fields) -> str | None:
    value = fields.get("stdout_regex")
    if value is _MISSING:
        return None
    at = fields.at.key("stdout_regex")
    pattern = _string(at, value)
    try:
        re.compile(pattern)
    except re.error as exc:
        raise at.fail(f"invalid regex: {exc.msg}") from exc
    except (OverflowError, RecursionError) as exc:  # pathological repeat counts or nesting
        raise at.fail("invalid regex: too large or too deeply nested") from exc
    return pattern


def _is_sandbox_path(text: str) -> bool:
    path = PurePosixPath(text)
    return bool(text) and not path.is_absolute() and ".." not in path.parts


def _files_exist(fields: _Fields) -> tuple[str, ...]:
    value = fields.get("files_exist")
    if value is _MISSING:
        return ()
    at = fields.at.key("files_exist")
    paths: list[str] = []
    for item_at, item in _items(at, value):
        path = _string(item_at, item)
        if not _is_sandbox_path(path):
            raise item_at.fail("must be a relative path inside the sandbox")
        paths.append(path)
    return tuple(paths)


def _reason(fields: _Fields, mode: VerifyMode) -> str | None:
    value = fields.get("reason")
    if value is not _MISSING:
        return _line(fields.at.key("reason"), value)
    if mode == "skip":
        raise fields.at.key("reason").fail("required for mode skip")
    return None


def _min_macos(fields: _Fields) -> str | None:
    value = fields.get("min_macos")
    if value is _MISSING:
        return None
    at = fields.at.key("min_macos")
    version = _string(at, value)
    if not _MIN_MACOS.fullmatch(version):
        raise at.fail("must look like 14 or 14.2")
    return version


def _mode(fields: _Fields) -> VerifyMode:
    at = fields.at.key("mode")
    mode = _choice(at, fields.require("mode"), tuple(_VERIFY_MODES))
    return _VERIFY_MODES[mode]


def _check_exec_command(fields: _Fields, cmd: str) -> None:
    denied = _denied_word(fields.at, cmd)
    if denied is not None:
        raise fields.at.key("mode").fail(f"{denied!r} is on the exec denylist (D-016)")


def _verify(at: _At, value: object, cmd: str) -> VerifySpec:
    fields = _Fields(at, value, _VERIFY_KEYS)
    mode = _mode(fields)
    _check_exec_only(fields, mode)
    setup = _setup(fields)
    bind = _bind(fields, cmd) if mode == "exec" else {}
    if mode == "exec":
        _check_exec_command(fields, cmd)
    return VerifySpec(
        mode=mode,
        setup=setup,
        bind=bind,
        expect_exit=_expect_exit(fields),
        stdout_contains=_stdout_contains(fields),
        stdout_regex=_stdout_regex(fields),
        files_exist=_files_exist(fields),
        reason=_reason(fields, mode),
        min_macos=_min_macos(fields),
    )


def _subcommand(at: _At, value: object, seen: set[str]) -> Subcommand:
    fields = _Fields(at, value, _SUBCOMMAND_KEYS)
    name_at = at.key("name")
    name = _name(name_at, fields.require("name"))
    _unique(name_at, seen, name, f"subcommand {name!r}")
    summary = _summary_or_empty(at.key("summary"), fields.require("summary"))
    body = fields.get("body")
    entry_name = fields.get("entry_name")
    return Subcommand(
        name,
        summary,
        None if entry_name is _MISSING else _name(at.key("entry_name"), entry_name),
        "curated",
        "" if body is _MISSING else _multiline(at.key("body"), body),
    )


def _summary_or_empty(at: _At, value: object) -> str:
    text = _string(at, value).strip()
    return _line(at, text) if text else ""


def _subcommands(fields: _Fields) -> tuple[Subcommand, ...]:
    value = fields.get("subcommands")
    if value is _MISSING:
        return ()
    seen: set[str] = set()
    return tuple(
        _subcommand(at, item, seen) for at, item in _items(fields.at.key("subcommands"), value)
    )


def _related(fields: _Fields, name: str) -> tuple[str, ...]:
    value = fields.get("related")
    if value is _MISSING:
        return ()
    seen: set[str] = set()
    related: list[str] = []
    for at, item in _items(fields.at.key("related"), value):
        other = _name(at, item)
        if other == name:
            raise at.fail("must not be the command itself")
        _unique(at, seen, other, f"name {other!r}")
        related.append(other)
    return tuple(related)


def _help_args(at: _At, value: object) -> tuple[str, ...]:
    if not _list(at, value):
        raise at.fail("must not be empty")
    args: list[str] = []
    for item_at, item in _items(at, value):
        arg = _string(item_at, item)
        if not arg.strip():
            raise item_at.fail("must not be blank")
        if not is_name(arg):
            raise item_at.fail("must not contain whitespace")
        args.append(arg)
    return tuple(args)


def _help_probe(fields: _Fields) -> HelpProbe | None:
    value = fields.get("help_probe")
    if value is _MISSING:
        return None
    probe = _Fields(fields.at.key("help_probe"), value, _HELP_PROBE_KEYS)
    args = _help_args(probe.at.key("args"), probe.require("args"))
    profile = _choice(probe.at.key("profile"), probe.require("profile"), HELP_PROFILES)
    return HelpProbe(args, profile)


def validate_command(data: object, file: str) -> CuratedCommand:
    """Validate one parsed ``commands/<name>.yaml`` document (D-010).

    Pre: `data` is whatever the YAML loader returned for the file.
    Post: the first problem found, in document order of the rules, is reported; no other
    exception type escapes.

    Args:
        data: The parsed YAML value.
        file: Label used in messages, e.g. ``commands/tar.yaml``; its stem is the command name.

    Returns:
        The validated command with stripped texts and tuples in document order.

    Raises:
        ContentError: With a message like ``commands/tar.yaml:examples[2].cmd: <reason>``.
    """
    at = _At(file)
    header = _check_header(at, data)
    fields = _Fields(at, header, _TOP_KEYS)
    name = _command_name(fields)
    section = _section(fields)
    summary = _summary(fields)
    explain = _multiline(at.key("explain"), fields.require("explain"))
    intents = _intents(at.key("intents"), fields.require("intents"))
    tags = _tags(fields)
    notes = _notes(fields)
    examples = _examples(fields, name)
    subcommands = _subcommands(fields)
    related = _related(fields, name)
    help_probe = _help_probe(fields)
    return CuratedCommand(
        name,
        section,
        summary,
        explain,
        intents,
        tags,
        notes,
        examples,
        subcommands,
        related,
        help_probe,
    )
