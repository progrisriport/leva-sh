"""Unit tests for ``leva.model``: errors, enums and value objects."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st

import leva.model
from leva.model import (
    ClipboardError,
    ConfigError,
    ContentError,
    Entry,
    Example,
    ExampleSource,
    IndexUnavailableError,
    IngestError,
    Kind,
    LevaError,
    ManRenderError,
    Note,
    NoteKind,
    Origin,
    Section,
    Subcommand,
    Verification,
    VerificationError,
    is_name,
)

ERROR_TYPES: list[type[LevaError]] = [
    IngestError,
    ManRenderError,
    ContentError,
    IndexUnavailableError,
    ClipboardError,
    VerificationError,
    ConfigError,
]

NBSP = chr(0xA0)
VALID_NAMES = ["ls", "[", "[[", ".", ":", "git-commit", "c++", "7z", "élan"]
INVALID_NAMES = ["", " ", "a b", "a\tb", "ls\n", NBSP + "ls"]


def make_entry(**overrides: object) -> Entry:
    fields: dict[str, object] = {
        "id": 1,
        "name": "ls",
        "section": "1",
        "kind": Kind.EXECUTABLE,
        "origin": Origin.MACOS,
        "summary": "list directory contents",
        "path": "/bin/ls",
        "has_man": True,
        "curated": False,
    }
    fields.update(overrides)
    return Entry(**fields)  # type: ignore[arg-type]  # kwargs built dynamically for overrides


def make_section(**overrides: object) -> Section:
    fields: dict[str, object] = {"heading": "NAME", "body": "ls - list", "ord": 0}
    fields.update(overrides)
    return Section(**fields)  # type: ignore[arg-type]  # kwargs built dynamically for overrides


def make_example(**overrides: object) -> Example:
    fields: dict[str, object] = {
        "id": "ls-long",
        "desc": "long listing",
        "cmd": "ls -la {{dir}}",
        "source": "curated",
        "verified": "exec",
    }
    fields.update(overrides)
    return Example(**fields)  # type: ignore[arg-type]  # kwargs built dynamically for overrides


def make_note(**overrides: object) -> Note:
    fields: dict[str, object] = {"kind": "macos", "text": "BSD ls has no --color"}
    fields.update(overrides)
    return Note(**fields)  # type: ignore[arg-type]  # kwargs built dynamically for overrides


def make_subcommand(**overrides: object) -> Subcommand:
    fields: dict[str, object] = {
        "name": "commit",
        "summary": "record changes",
        "entry_name": "git-commit",
        "source": "hyphen",
    }
    fields.update(overrides)
    return Subcommand(**fields)  # type: ignore[arg-type]  # kwargs built dynamically for overrides


ValueObject = Entry | Section | Example | Note | Subcommand
Factory = Callable[..., ValueObject]

VALUE_FACTORIES: list[Factory] = [
    make_entry,
    make_section,
    make_example,
    make_note,
    make_subcommand,
]

# One (field, other value) pair per type: replacing the field must break equality.
CHANGES: list[tuple[Factory, str, object]] = [
    (make_entry, "name", "cat"),
    (make_section, "body", "other"),
    (make_example, "cmd", "ls"),
    (make_note, "text", "other"),
    (make_subcommand, "summary", "other"),
]

FIELD_ORDER: list[tuple[type, list[str]]] = [
    (
        Entry,
        ["id", "name", "section", "kind", "origin", "summary", "path", "has_man", "curated"],
    ),
    (Section, ["heading", "body", "ord"]),
    (Example, ["id", "desc", "cmd", "source", "verified", "danger"]),
    (Note, ["kind", "text"]),
    (Subcommand, ["name", "summary", "entry_name", "source", "body"]),
]


# --- errors -------------------------------------------------------------------------------


def test_leva_error_exposes_message_without_hint() -> None:
    err = LevaError("boom")
    assert err.message == "boom"
    assert err.hint is None
    assert str(err) == "boom"
    assert err.args == ("boom",)


def test_leva_error_keeps_hint_by_keyword_and_position() -> None:
    by_keyword = LevaError("boom", hint="run leva --rebuild")
    by_position = LevaError("boom", "run leva --rebuild")
    assert by_keyword.hint == by_position.hint == "run leva --rebuild"
    assert str(by_keyword) == str(by_position) == "boom"


@pytest.mark.parametrize("error_type", ERROR_TYPES)
def test_error_subclass_is_caught_as_leva_error(error_type: type[LevaError]) -> None:
    assert issubclass(error_type, LevaError)
    assert issubclass(error_type, Exception)
    with pytest.raises(LevaError) as caught:
        raise error_type("failed", hint="try again")
    assert isinstance(caught.value, error_type)
    assert caught.value.message == "failed"
    assert caught.value.hint == "try again"
    assert str(caught.value) == "failed"


def test_error_keeps_cause_when_raised_from_another_exception() -> None:
    cause = ValueError("x")
    with pytest.raises(ContentError) as caught:
        raise ContentError("a.yaml:name: must equal file stem") from cause
    assert caught.value.__cause__ is cause


@pytest.mark.parametrize("error_type", ERROR_TYPES)
def test_error_subclasses_are_distinct(error_type: type[LevaError]) -> None:
    others = [other for other in ERROR_TYPES if other is not error_type]
    assert all(not isinstance(error_type("x"), other) for other in others)


# --- enums --------------------------------------------------------------------------------


def test_origin_members_are_exact() -> None:
    assert {m.name: m.value for m in Origin} == {
        "MACOS": "macos",
        "HOMEBREW": "homebrew",
        "ZSH": "zsh",
        "BASH": "bash",
    }


def test_kind_members_are_exact() -> None:
    assert {m.name: m.value for m in Kind} == {
        "EXECUTABLE": "executable",
        "BUILTIN": "builtin",
        "MANPAGE_ONLY": "manpage",
    }


def test_enums_behave_as_strings() -> None:
    assert Kind("manpage") is Kind.MANPAGE_ONLY
    assert Origin.ZSH == "zsh"
    assert str(Origin.HOMEBREW) == "homebrew"


def test_origin_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="windows"):
        Origin("windows")


# --- value objects: structure ---------------------------------------------------------------


@pytest.mark.parametrize("factory", VALUE_FACTORIES)
def test_value_objects_with_equal_fields_are_equal_and_hash_alike(factory: Factory) -> None:
    first, second = factory(), factory()
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


@pytest.mark.parametrize(("factory", "field", "other"), CHANGES)
def test_value_objects_differ_when_a_field_differs(
    factory: Factory, field: str, other: object
) -> None:
    base = factory()
    changed = factory(**{field: other})
    assert base != changed
    assert len({base, changed}) == 2


@pytest.mark.parametrize("factory", VALUE_FACTORIES)
def test_value_objects_are_immutable(factory: Factory) -> None:
    obj = factory()
    for field in dataclasses.fields(obj):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, field.name, getattr(obj, field.name))


@pytest.mark.parametrize("factory", VALUE_FACTORIES)
def test_value_objects_use_slots(factory: Factory) -> None:
    obj = factory()
    assert not hasattr(obj, "__dict__")
    assert "__slots__" in type(obj).__dict__


@pytest.mark.parametrize(("cls", "names"), FIELD_ORDER)
def test_value_objects_keep_field_order(cls: type, names: list[str]) -> None:
    assert [f.name for f in dataclasses.fields(cls)] == names


def test_example_danger_defaults_to_none() -> None:
    example = Example("ls-long", "long", "ls -l", "curated", "exec")
    assert example.danger is None


def test_subcommand_body_defaults_to_empty_and_accepts_positional_args() -> None:
    sub = Subcommand("commit", "record changes", "git-commit", "hyphen")
    assert sub.body == ""
    assert sub.entry_name == "git-commit"


# --- name rule ------------------------------------------------------------------------------

NAME_FIELDS: list[tuple[Factory, str, str]] = [
    (make_entry, "name", "Entry.name"),
    (make_entry, "section", "Entry.section"),
    (make_example, "id", "Example.id"),
    (make_subcommand, "name", "Subcommand.name"),
    (make_subcommand, "entry_name", "Subcommand.entry_name"),
]


@pytest.mark.parametrize("name", VALID_NAMES)
@pytest.mark.parametrize(("factory", "field", "label"), NAME_FIELDS)
def test_name_fields_accept_valid_names(
    factory: Factory, field: str, label: str, name: str
) -> None:
    obj = factory(**{field: name})
    assert getattr(obj, field) == name, label


@pytest.mark.parametrize("name", INVALID_NAMES)
@pytest.mark.parametrize(("factory", "field", "label"), NAME_FIELDS)
def test_name_fields_reject_empty_or_whitespace_names(
    factory: Factory, field: str, label: str, name: str
) -> None:
    with pytest.raises(ValueError, match=label):
        factory(**{field: name})


@pytest.mark.parametrize("name", VALID_NAMES)
def test_is_name_accepts_valid_names(name: str) -> None:
    assert is_name(name)


@pytest.mark.parametrize("name", INVALID_NAMES)
def test_is_name_rejects_empty_or_whitespace_names(name: str) -> None:
    assert not is_name(name)


WHITESPACE = [" ", "\t", "\n", "\x0b", "\x0c", "\r", "\x85", NBSP, "\u2003", "\u3000"]
VISIBLE_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Zs", "Zl", "Zp", "Cc")), min_size=1
)


@given(st.text(), st.sampled_from(WHITESPACE), st.data())
def test_is_name_rejects_text_with_an_inserted_whitespace_character(
    value: str, whitespace: str, data: st.DataObject
) -> None:
    index = data.draw(st.integers(min_value=0, max_value=len(value)))

    assert not is_name(value[:index] + whitespace + value[index:])


@given(VISIBLE_TEXT)
def test_is_name_accepts_any_non_empty_text_without_whitespace(value: str) -> None:
    assert is_name(value)


def test_entry_section_none_is_accepted() -> None:
    assert make_entry(section=None).section is None


def test_subcommand_entry_name_none_is_accepted() -> None:
    assert make_subcommand(entry_name=None).entry_name is None


def test_name_error_message_has_documented_format() -> None:
    with pytest.raises(ValueError, match=r"Entry\.name") as caught:
        make_entry(name="a b")
    assert str(caught.value) == "Entry.name must be non-empty without whitespace: 'a b'"


# --- Entry enums ----------------------------------------------------------------------------


def test_entry_rejects_plain_string_kind() -> None:
    with pytest.raises(ValueError, match=r"Entry\.kind"):
        make_entry(kind="builtin")


def test_entry_rejects_plain_string_origin() -> None:
    with pytest.raises(ValueError, match=r"Entry\.origin"):
        make_entry(origin="macos")


def test_entry_accepts_enum_members() -> None:
    entry = make_entry(kind=Kind.BUILTIN, origin=Origin.ZSH)
    assert (entry.kind, entry.origin) == (Kind.BUILTIN, Origin.ZSH)


# --- Section --------------------------------------------------------------------------------


@pytest.mark.parametrize("ord_value", [0, 5])
def test_section_accepts_non_negative_ord(ord_value: int) -> None:
    assert make_section(ord=ord_value).ord == ord_value


def test_section_rejects_negative_ord() -> None:
    with pytest.raises(ValueError, match=r"Section\.ord") as caught:
        make_section(ord=-1)
    assert str(caught.value) == "Section.ord must be >= 0: -1"


def test_section_accepts_empty_heading_and_body() -> None:
    section = make_section(heading="", body="")
    assert (section.heading, section.body) == ("", "")


# --- Example --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "ls -la",
        "tar -czf {{archive}}.tgz {{dir}}",
        "find . -name '*.py' \\\n  -print",
        "find . \\\n  -name '*.py' \\\n  -print",
    ],
)
def test_example_accepts_valid_cmd(cmd: str) -> None:
    assert make_example(cmd=cmd).cmd == cmd


@pytest.mark.parametrize("cmd", ["", "   ", "ls\nrm x", "ls \\\n", "\nls", "ls\r\n", "ls\rrm"])
def test_example_rejects_invalid_cmd(cmd: str) -> None:
    with pytest.raises(ValueError, match=r"Example\.cmd"):
        make_example(cmd=cmd)


@pytest.mark.parametrize("source", get_args(ExampleSource))
def test_example_accepts_every_source(source: str) -> None:
    assert make_example(source=source).source == source


@pytest.mark.parametrize("source", ["official", "CURATED", ""])
def test_example_rejects_unknown_source(source: str) -> None:
    with pytest.raises(ValueError, match=r"Example\.source"):
        make_example(source=source)


@pytest.mark.parametrize("verified", get_args(Verification))
def test_example_accepts_every_verification(verified: str) -> None:
    assert make_example(verified=verified).verified == verified


@pytest.mark.parametrize("verified", ["maybe", "EXEC", ""])
def test_example_rejects_unknown_verification(verified: str) -> None:
    with pytest.raises(ValueError, match=r"Example\.verified") as caught:
        make_example(verified=verified)
    assert str(caught.value).startswith(
        "Example.verified must be one of exec, static, skip, none: "
    )


@pytest.mark.parametrize("danger", [None, "deletes permanently, no Trash, no undo"])
def test_example_accepts_danger(danger: str | None) -> None:
    assert make_example(danger=danger).danger == danger


@pytest.mark.parametrize("danger", ["", "  ", "line1\nline2", "a\rb"])
def test_example_rejects_blank_or_multiline_danger(danger: str) -> None:
    with pytest.raises(ValueError, match=r"Example\.danger"):
        make_example(danger=danger)


# --- Note and Subcommand --------------------------------------------------------------------


@pytest.mark.parametrize("kind", get_args(NoteKind))
def test_note_accepts_every_kind(kind: str) -> None:
    assert make_note(kind=kind).kind == kind


@pytest.mark.parametrize("kind", ["linux", "BSD-GNU", ""])
def test_note_rejects_unknown_kind(kind: str) -> None:
    with pytest.raises(ValueError, match=r"Note\.kind"):
        make_note(kind=kind)


@pytest.mark.parametrize("source", ["", "  "])
def test_subcommand_rejects_blank_source(source: str) -> None:
    with pytest.raises(ValueError, match=r"Subcommand\.source"):
        make_subcommand(source=source)


def test_subcommand_accepts_non_blank_source() -> None:
    assert make_subcommand(source="curated").source == "curated"


@given(st.text(min_size=1))
def test_subcommand_name_accepted_iff_no_whitespace(name: str) -> None:
    has_space = any(c.isspace() for c in name)
    if has_space:
        with pytest.raises(ValueError, match=r"Subcommand\.name"):
            make_subcommand(name=name)
    else:
        assert make_subcommand(name=name).name == name


# --- public surface -------------------------------------------------------------------------

EXPECTED_ALL = [
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
    "is_name",
]


def test_model_all_is_sorted_and_complete() -> None:
    assert leva.model.__all__ == EXPECTED_ALL


def test_model_all_names_are_attributes() -> None:
    assert all(hasattr(leva.model, name) for name in leva.model.__all__)
