"""Tests for `validate_command`: strict validation of one parsed curated YAML document."""

from __future__ import annotations

import contextlib
import copy
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from leva.content import (
    CuratedCommand,
    ExampleSpec,
    HelpProbe,
    VerifySpec,
    validate_command,
)
from leva.model import ContentError, Note, Subcommand

FILE = "commands/tar.yaml"


def example(**overrides: Any) -> dict[str, Any]:
    """Return a fresh minimal valid example mapping."""
    data: dict[str, Any] = {
        "id": "tar-list",
        "desc": "List an archive",
        "cmd": "tar -tf {{archive}}",
        "verify": {"mode": "exec", "bind": {"archive": "a.tar"}},
    }
    data.update(overrides)
    return data


def valid_doc(**overrides: Any) -> dict[str, Any]:
    """Return a fresh minimal valid document for `commands/tar.yaml`."""
    data: dict[str, Any] = {
        "schema": 1,
        "kind": "command",
        "name": "tar",
        "summary": "Create, list and extract archives.",
        "explain": "tar bundles files into one archive.",
        "intents": ["extract an archive"],
        "examples": [example()],
    }
    data.update(overrides)
    return data


def full_doc() -> dict[str, Any]:
    return valid_doc(
        section="1",
        summary="  Create, list and extract archives.  ",
        explain="\n  tar bundles files.\n  Second line.\n",
        intents=["extract an archive", " list archive contents "],
        tags=["archive", "backup"],
        notes=[
            {"kind": "bsd-gnu", "text": " macOS tar is bsdtar. "},
            {"kind": "safety", "text": "Mind the paths."},
        ],
        examples=[
            example(),
            {
                "id": "tar-extract-gz",
                "desc": "Extract a .tar.gz",
                "cmd": "tar -xzf {{archive.tar.gz}} \\\n  -C {{dir}}\n",
                "verify": {
                    "mode": "exec",
                    "setup": "mkdir d && echo hi > d/a",
                    "bind": {"archive.tar.gz": "a.tgz", "dir": "d"},
                    "expect_exit": 2,
                    "stdout_contains": ["a", "b"],
                    "stdout_regex": "^d/",
                    "files_exist": ["d/a"],
                    "reason": "needs a fixture",
                    "min_macos": "14.2",
                },
            },
            {
                "id": "tar-remove",
                "desc": "Remove the archive",
                "cmd": "rm {{archive}}",
                "danger": "deletes the archive",
                "verify": {"mode": "skip", "reason": "destructive"},
            },
            {
                "id": "tar-static",
                "desc": "Static one",
                "cmd": "brew list",
                "verify": {"mode": "static"},
            },
        ],
        subcommands=[
            {"name": "x", "summary": " extract ", "body": "\n long\n", "entry_name": "tar-x"},
            {"name": "c", "summary": ""},
        ],
        related=["gzip", "zip"],
        help_probe={"args": ["--help"], "profile": "two-col"},
    )


def error_of(data: object, file: str = FILE) -> ContentError:
    with pytest.raises(ContentError) as info:
        validate_command(data, file)
    assert info.value.hint is None
    return info.value


def with_example(**overrides: Any) -> dict[str, Any]:
    return valid_doc(examples=[example(**overrides)])


def with_verify(**verify: Any) -> dict[str, Any]:
    return valid_doc(examples=[example(cmd="tar -tf a", verify=verify)])


def test_full_document_is_validated_into_exact_values() -> None:
    command = validate_command(full_doc(), FILE)
    assert command.name == "tar"
    assert command.section == "1"
    assert command.summary == "Create, list and extract archives."
    assert command.explain == "tar bundles files.\n  Second line."
    assert command.intents == ("extract an archive", "list archive contents")
    assert command.tags == ("archive", "backup")
    assert command.notes == (
        Note("bsd-gnu", "macOS tar is bsdtar."),
        Note("safety", "Mind the paths."),
    )
    assert [e.id for e in command.examples] == [
        "tar-list",
        "tar-extract-gz",
        "tar-remove",
        "tar-static",
    ]
    assert command.subcommands == (
        Subcommand("x", "extract", "tar-x", "curated", "long"),
        Subcommand("c", "", None, "curated", ""),
    )
    assert command.related == ("gzip", "zip")
    assert command.help_probe == HelpProbe(("--help",), "two-col")


def test_full_document_example_details() -> None:
    command = validate_command(full_doc(), FILE)
    first, second, third, fourth = command.examples
    assert first == ExampleSpec(
        "tar-list",
        "List an archive",
        "tar -tf {{archive}}",
        VerifySpec(mode="exec", bind={"archive": "a.tar"}),
    )
    assert second.cmd == "tar -xzf {{archive.tar.gz}} \\\n  -C {{dir}}"
    assert second.verify == VerifySpec(
        mode="exec",
        setup="mkdir d && echo hi > d/a",
        bind={"archive.tar.gz": "a.tgz", "dir": "d"},
        expect_exit=2,
        stdout_contains=("a", "b"),
        stdout_regex="^d/",
        files_exist=("d/a",),
        reason="needs a fixture",
        min_macos="14.2",
    )
    assert third.danger == "deletes the archive"
    assert fourth.verify.mode == "static"


def test_bind_of_validated_document_is_read_only_and_equal_to_the_input() -> None:
    data = full_doc()
    command = validate_command(data, FILE)
    bind = command.examples[1].verify.bind
    assert bind == data["examples"][1]["verify"]["bind"]
    with pytest.raises(TypeError):
        bind["x"] = "y"  # type: ignore[index] # read-only mapping on purpose
    data["examples"][1]["verify"]["bind"]["dir"] = "changed"
    assert bind["dir"] == "d"


def test_minimal_document_gets_defaults() -> None:
    command = validate_command(
        {
            "schema": 1,
            "kind": "command",
            "name": "tar",
            "summary": "s",
            "explain": "e",
            "intents": ["i"],
        },
        FILE,
    )
    assert command == CuratedCommand("tar", None, "s", "e", ("i",), (), (), (), (), (), None)


def test_yaml_block_cmd_loses_trailing_newline_and_converts() -> None:
    doc = valid_doc(
        examples=[
            example(
                cmd="tar -xzf {{a}} \\\n  -C {{d}}\n",
                verify={"mode": "exec", "bind": {"a": "x", "d": "y"}},
            )
        ]
    )
    spec = validate_command(doc, FILE).examples[0]
    assert spec.cmd == "tar -xzf {{a}} \\\n  -C {{d}}"
    converted = spec.to_example()
    assert (converted.source, converted.verified, converted.danger) == ("curated", "exec", None)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (None, "commands/tar.yaml: expected a mapping"),
        ([], "commands/tar.yaml: expected a mapping"),
        ("schema: 1", "commands/tar.yaml: expected a mapping"),
        ({}, "commands/tar.yaml:schema: required"),
        (valid_doc(schema=2), "commands/tar.yaml:schema: unsupported schema 2 (expected 1)"),
        (valid_doc(schema="1"), "commands/tar.yaml:schema: unsupported schema '1' (expected 1)"),
        (valid_doc(schema=True), "commands/tar.yaml:schema: unsupported schema True (expected 1)"),
        (valid_doc(schema=None), "commands/tar.yaml:schema: unsupported schema None (expected 1)"),
        ({"schema": 1}, "commands/tar.yaml:kind: required"),
        (valid_doc(kind=3), "commands/tar.yaml:kind: must be a string"),
        (valid_doc(kind="recipe"), "commands/tar.yaml:kind: 'recipe' not supported in schema 1"),
        (valid_doc(kind="path"), "commands/tar.yaml:kind: 'path' not supported in schema 1"),
        (valid_doc(foo=1), "commands/tar.yaml: unknown key 'foo'"),
        ({**valid_doc(), 1: "x"}, "commands/tar.yaml: unknown key 1"),
    ],
)
def test_document_level_errors(data: object, message: str) -> None:
    assert error_of(data).message == message


def _missing(key: str) -> dict[str, Any]:
    doc = valid_doc()
    del doc[key]
    return doc


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_missing("name"), "commands/tar.yaml:name: required"),
        (valid_doc(name=3), "commands/tar.yaml:name: must be a string"),
        (valid_doc(name="t ar"), "commands/tar.yaml:name: must not contain whitespace"),
        (valid_doc(name=""), "commands/tar.yaml:name: must not contain whitespace"),
        (valid_doc(name="gzip"), "commands/tar.yaml:name: must equal the file name 'tar'"),
        (valid_doc(section=1), "commands/tar.yaml:section: must be a string"),
        (valid_doc(section="1 x"), "commands/tar.yaml:section: must match [a-z0-9]+"),
        (valid_doc(section="1\n"), "commands/tar.yaml:section: must match [a-z0-9]+"),
        (valid_doc(section=""), "commands/tar.yaml:section: must match [a-z0-9]+"),
        (valid_doc(section=None), "commands/tar.yaml:section: must be a string"),
        (_missing("summary"), "commands/tar.yaml:summary: required"),
        (valid_doc(summary="   "), "commands/tar.yaml:summary: must not be blank"),
        (valid_doc(summary=["a"]), "commands/tar.yaml:summary: must be a string"),
        (valid_doc(summary="a\nb"), "commands/tar.yaml:summary: must be a single line"),
        (valid_doc(summary="a\x85b"), "commands/tar.yaml:summary: must be a single line"),
        (valid_doc(summary="x" * 121), "commands/tar.yaml:summary: longer than 120 characters"),
        (_missing("explain"), "commands/tar.yaml:explain: required"),
        (valid_doc(explain=" \n "), "commands/tar.yaml:explain: must not be blank"),
        (valid_doc(explain=1), "commands/tar.yaml:explain: must be a string"),
        (_missing("intents"), "commands/tar.yaml:intents: required"),
        (valid_doc(intents="a"), "commands/tar.yaml:intents: must be a list"),
        (valid_doc(intents=[]), "commands/tar.yaml:intents: must not be empty"),
        (valid_doc(intents=["a", " "]), "commands/tar.yaml:intents[1]: must not be blank"),
        (valid_doc(intents=["a", 3]), "commands/tar.yaml:intents[1]: must be a string"),
        (valid_doc(intents=["a\nb"]), "commands/tar.yaml:intents[0]: must be a single line"),
        (
            valid_doc(intents=["a", "b", "c", "A"]),
            "commands/tar.yaml:intents[3]: duplicate intent",
        ),
        (valid_doc(tags="a"), "commands/tar.yaml:tags: must be a list"),
        (valid_doc(tags=["a", "a"]), "commands/tar.yaml:tags[1]: duplicate tag"),
        (valid_doc(tags=[""]), "commands/tar.yaml:tags[0]: must not be blank"),
    ],
)
def test_text_field_errors(data: object, message: str) -> None:
    assert error_of(data).message == message


def test_summary_of_exactly_120_characters_passes() -> None:
    assert validate_command(valid_doc(summary="x" * 120), FILE).summary == "x" * 120


@pytest.mark.parametrize(
    ("notes", "message"),
    [
        ("n", "commands/tar.yaml:notes: must be a list"),
        (["n"], "commands/tar.yaml:notes[0]: must be a mapping"),
        (
            [{"kind": "bsd", "text": "t"}],
            "commands/tar.yaml:notes[0].kind: must be one of bsd-gnu, zsh-bash, macos, safety",
        ),
        ([{"kind": "macos"}], "commands/tar.yaml:notes[0].text: required"),
        ([{"text": "t"}], "commands/tar.yaml:notes[0].kind: required"),
        ([{"kind": 1, "text": "t"}], "commands/tar.yaml:notes[0].kind: must be a string"),
        ([{"kind": "macos", "text": " "}], "commands/tar.yaml:notes[0].text: must not be blank"),
        (
            [{"kind": "macos", "text": "t", "extra": 1}],
            "commands/tar.yaml:notes[0]: unknown key 'extra'",
        ),
    ],
)
def test_note_errors(notes: object, message: str) -> None:
    assert error_of(valid_doc(notes=notes)).message == message


@pytest.mark.parametrize(
    ("examples", "message"),
    [
        ("e", "commands/tar.yaml:examples: must be a list"),
        (["e"], "commands/tar.yaml:examples[0]: must be a mapping"),
        ([example(extra=1)], "commands/tar.yaml:examples[0]: unknown key 'extra'"),
        ([{**example(), 5: "x"}], "commands/tar.yaml:examples[0]: unknown key 5"),
    ],
)
def test_example_container_errors(examples: object, message: str) -> None:
    assert error_of(valid_doc(examples=examples)).message == message


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"id": "tar_x"},
            "examples[0].id: must look like tar-<slug> (lowercase letters, digits, hyphens)",
        ),
        (
            {"id": "gzip-x"},
            "examples[0].id: must look like tar-<slug> (lowercase letters, digits, hyphens)",
        ),
        (
            {"id": "tar-"},
            "examples[0].id: must look like tar-<slug> (lowercase letters, digits, hyphens)",
        ),
        (
            {"id": "tar-X"},
            "examples[0].id: must look like tar-<slug> (lowercase letters, digits, hyphens)",
        ),
        (
            {"id": "tar-x\n"},
            "examples[0].id: must look like tar-<slug> (lowercase letters, digits, hyphens)",
        ),
        ({"id": 1}, "examples[0].id: must be a string"),
        ({"id": "tar-tldr-1"}, "examples[0].id: slug 'tldr-...' is reserved"),
        ({"desc": " "}, "examples[0].desc: must not be blank"),
        ({"desc": "a\nb"}, "examples[0].desc: must be a single line"),
        ({"cmd": "  \n"}, "examples[0].cmd: must not be blank"),
        ({"cmd": 3}, "examples[0].cmd: must be a string"),
        ({"cmd": "tar\rx"}, "examples[0].cmd: must not contain a carriage return"),
        ({"cmd": "tar -x\n  -f a"}, "examples[0].cmd: newline must follow a backslash"),
        ({"cmd": "tar -x \\"}, "examples[0].cmd: must not end with a backslash"),
        ({"cmd": "tar {{x"}, "examples[0].cmd: unclosed placeholder"),
        ({"cmd": "tar {{ }}"}, "examples[0].cmd: empty placeholder"),
        (
            {"cmd": "tar 'x"},
            "examples[0].cmd: cannot be split into words (unbalanced quote or trailing escape)",
        ),
        (
            {"cmd": "rm -rf {{dir}}", "verify": {"mode": "skip", "reason": "r"}},
            "examples[0].danger: required, the command is destructive (D-030)",
        ),
        ({"danger": " "}, "examples[0].danger: must not be blank"),
        ({"danger": "a\nb"}, "examples[0].danger: must be a single line"),
        ({"danger": 1}, "examples[0].danger: must be a string"),
        ({"verify": None}, "examples[0].verify: must be a mapping"),
        ({"verify": {"mode": "exec", "stdout": "x"}}, "examples[0].verify: unknown key 'stdout'"),
    ],
)
def test_example_errors(overrides: dict[str, Any], message: str) -> None:
    assert error_of(with_example(**overrides)).message == f"{FILE}:{message}"


def test_example_missing_keys() -> None:
    for key in ("id", "desc", "cmd", "verify"):
        data = with_example()
        del data["examples"][0][key]
        assert error_of(data).message == f"{FILE}:examples[0].{key}: required"


def test_duplicate_example_id_is_reported_on_the_second() -> None:
    doc = valid_doc(examples=[example(), example(id="tar-b"), example()])
    assert error_of(doc).message == f"{FILE}:examples[2].id: duplicate example id 'tar-list'"


def test_example_error_path_uses_the_example_index() -> None:
    doc = valid_doc(examples=[example(), example(id="tar-b", desc="")])
    assert error_of(doc).message == f"{FILE}:examples[1].desc: must not be blank"


@pytest.mark.parametrize(
    ("verify", "message"),
    [
        ({}, "examples[0].verify.mode: required"),
        ({"mode": 1}, "examples[0].verify.mode: must be a string"),
        ({"mode": "run"}, "examples[0].verify.mode: must be one of exec, static, skip"),
        ({"mode": "static", "setup": "ls"}, "examples[0].verify.setup: only valid with mode exec"),
        ({"mode": "skip", "bind": {}}, "examples[0].verify.bind: only valid with mode exec"),
        (
            {"mode": "static", "expect_exit": 0},
            "examples[0].verify.expect_exit: only valid with mode exec",
        ),
        (
            {"mode": "static", "stdout_contains": ["a"]},
            "examples[0].verify.stdout_contains: only valid with mode exec",
        ),
        (
            {"mode": "static", "stdout_regex": "a"},
            "examples[0].verify.stdout_regex: only valid with mode exec",
        ),
        (
            {"mode": "static", "files_exist": ["a"]},
            "examples[0].verify.files_exist: only valid with mode exec",
        ),
        ({"mode": "exec", "setup": 1}, "examples[0].verify.setup: must be a string"),
        (
            {"mode": "exec", "setup": "echo 'x"},
            "examples[0].verify.setup: cannot be split into words "
            "(unbalanced quote or trailing escape)",
        ),
        (
            {"mode": "exec", "setup": "mkdir d && curl x"},
            "examples[0].verify.setup: 'curl' is on the exec denylist (D-016)",
        ),
        ({"mode": "exec", "bind": []}, "examples[0].verify.bind: must be a mapping"),
        (
            {"mode": "exec", "bind": {"archive": "a", "x": "y"}},
            "examples[0].verify.bind: unknown placeholder 'x'",
        ),
        (
            {"mode": "exec", "bind": {"archive": 1}},
            "examples[0].verify.bind.archive: must be a string",
        ),
        ({"mode": "exec", "bind": {}}, "examples[0].verify.bind: missing placeholder 'archive'"),
        ({"mode": "exec"}, "examples[0].verify.bind: missing placeholder 'archive'"),
        (
            {"mode": "exec", "bind": {"archive": "a", 1: "b"}},
            "examples[0].verify.bind: unknown placeholder 1",
        ),
        (
            {"mode": "exec", "bind": {"archive": "a"}, "expect_exit": True},
            "examples[0].verify.expect_exit: must be an integer",
        ),
        (
            {"mode": "exec", "bind": {"archive": "a"}, "expect_exit": -1},
            "examples[0].verify.expect_exit: must be between 0 and 255",
        ),
        (
            {"mode": "exec", "bind": {"archive": "a"}, "expect_exit": 256},
            "examples[0].verify.expect_exit: must be between 0 and 255",
        ),
        (
            {"mode": "exec", "bind": {"archive": "a"}, "expect_exit": "0"},
            "examples[0].verify.expect_exit: must be an integer",
        ),
        (
            {"mode": "exec", "bind": {"archive": "a"}, "stdout_contains": "a"},
            "examples[0].verify.stdout_contains: must be a list",
        ),
        (
            {"mode": "exec", "bind": {"archive": "a"}, "stdout_contains": ["a", ""]},
            "examples[0].verify.stdout_contains[1]: must not be empty",
        ),
        (
            {"mode": "exec", "bind": {"archive": "a"}, "stdout_contains": [1]},
            "examples[0].verify.stdout_contains[0]: must be a string",
        ),
        (
            {"mode": "exec", "bind": {"archive": "a"}, "stdout_regex": 1},
            "examples[0].verify.stdout_regex: must be a string",
        ),
        (
            {"mode": "exec", "bind": {"archive": "a"}, "reason": " "},
            "examples[0].verify.reason: must not be blank",
        ),
        (
            {"mode": "exec", "bind": {"archive": "a"}, "reason": "a\nb"},
            "examples[0].verify.reason: must be a single line",
        ),
        ({"mode": "skip"}, "examples[0].verify.reason: required for mode skip"),
        (
            {"mode": "skip", "reason": "r", "min_macos": 14.0},
            "examples[0].verify.min_macos: must be a string",
        ),
        (
            {"mode": "skip", "reason": "r", "min_macos": "fourteen"},
            "examples[0].verify.min_macos: must look like 14 or 14.2",
        ),
        (
            {"mode": "skip", "reason": "r", "min_macos": "14.2.1.0"},
            "examples[0].verify.min_macos: must look like 14 or 14.2",
        ),
        (
            {"mode": "skip", "reason": "r", "min_macos": "14.\n"},
            "examples[0].verify.min_macos: must look like 14 or 14.2",
        ),
    ],
)
def test_verify_errors(verify: dict[str, Any], message: str) -> None:
    assert error_of(valid_doc(examples=[example(verify=verify)])).message == f"{FILE}:{message}"


@pytest.mark.parametrize(
    ("cmd", "word"),
    [
        ("brew list", "brew"),
        ("/usr/bin/curl -s x", "curl"),
        ("sudo ls", "sudo"),
        ("ls | pbcopy", "pbcopy"),
        ("env FOO=1 ssh host", "ssh"),
    ],
)
def test_exec_denylist_applies_to_cmd(cmd: str, word: str) -> None:
    doc = valid_doc(examples=[example(cmd=cmd, verify={"mode": "exec"})])
    message = f"{FILE}:examples[0].verify.mode: '{word}' is on the exec denylist (D-016)"
    assert error_of(doc).message == message


def test_stdout_regex_error_carries_the_regex_message() -> None:
    doc = with_verify(mode="exec", stdout_regex="(")
    message = error_of(doc).message
    assert message.startswith(f"{FILE}:examples[0].verify.stdout_regex: invalid regex: ")
    assert "missing )" in message


@pytest.mark.parametrize("pattern", ["a{99999999999999999999}", "(" * 5000 + ")" * 5000])
def test_pathological_stdout_regex_is_a_content_error(pattern: str) -> None:
    message = error_of(with_verify(mode="exec", stdout_regex=pattern)).message
    assert message == (
        f"{FILE}:examples[0].verify.stdout_regex: invalid regex: too large or too deeply nested"
    )


@pytest.mark.parametrize("path", ["/etc/x", "../x", "a/../../x", "", "a/.."])
def test_files_exist_must_be_relative_inside_the_sandbox(path: str) -> None:
    message = error_of(with_verify(mode="exec", files_exist=["ok", path])).message
    assert message == (
        f"{FILE}:examples[0].verify.files_exist[1]: must be a relative path inside the sandbox"
    )


def test_files_exist_type_errors() -> None:
    assert (
        error_of(with_verify(mode="exec", files_exist="a")).message
        == f"{FILE}:examples[0].verify.files_exist: must be a list"
    )
    assert (
        error_of(with_verify(mode="exec", files_exist=[1])).message
        == f"{FILE}:examples[0].verify.files_exist[0]: must be a string"
    )


@pytest.mark.parametrize("code", [0, 255])
def test_expect_exit_bounds_pass(code: int) -> None:
    spec = validate_command(with_verify(mode="exec", expect_exit=code), FILE).examples[0]
    assert spec.verify.expect_exit == code


@pytest.mark.parametrize("version", ["14", "14.2", "14.2.1"])
def test_min_macos_patterns_pass(version: str) -> None:
    spec = validate_command(with_verify(mode="exec", min_macos=version), FILE).examples[0]
    assert spec.verify.min_macos == version


def test_skip_with_reason_and_static_with_reason_pass() -> None:
    skip = validate_command(with_verify(mode="skip", reason=" needs root "), FILE)
    assert skip.examples[0].verify == VerifySpec(mode="skip", reason="needs root")
    static = validate_command(with_verify(mode="static", reason="r"), FILE)
    assert static.examples[0].verify.reason == "r"


def test_static_example_with_denylisted_command_passes() -> None:
    doc = valid_doc(examples=[example(cmd="brew list", verify={"mode": "static"})])
    assert validate_command(doc, FILE).examples[0].verify.mode == "static"


def test_danger_on_a_harmless_command_passes() -> None:
    doc = with_example(danger="be careful", cmd="tar -tf a", verify={"mode": "static"})
    assert validate_command(doc, FILE).examples[0].danger == "be careful"


def test_escaped_placeholder_is_a_literal() -> None:
    doc = with_example(cmd="echo \\{{x}}", verify={"mode": "exec"})
    assert validate_command(doc, FILE).examples[0].cmd == "echo \\{{x}}"


def test_names_with_regex_specials_work() -> None:
    doc = valid_doc(
        name="[",
        examples=[example(id="[-x", cmd="[ -f a ]", verify={"mode": "exec"})],
    )
    assert validate_command(doc, "commands/[.yaml").examples[0].id == "[-x"


def test_name_with_plus_signs_works() -> None:
    doc = valid_doc(
        name="c++", examples=[example(id="c++-x", cmd="c++ a", verify={"mode": "exec"})]
    )
    assert validate_command(doc, "commands/c++.yaml").name == "c++"


@pytest.mark.parametrize(
    ("subcommands", "message"),
    [
        ("s", "commands/tar.yaml:subcommands: must be a list"),
        (["s"], "commands/tar.yaml:subcommands[0]: must be a mapping"),
        ([{"summary": "s"}], "commands/tar.yaml:subcommands[0].name: required"),
        (
            [{"name": "a b", "summary": "s"}],
            "commands/tar.yaml:subcommands[0].name: must not contain whitespace",
        ),
        ([{"name": "a"}], "commands/tar.yaml:subcommands[0].summary: required"),
        (
            [{"name": "a", "summary": "x\ny"}],
            "commands/tar.yaml:subcommands[0].summary: must be a single line",
        ),
        (
            [{"name": "a", "summary": 1}],
            "commands/tar.yaml:subcommands[0].summary: must be a string",
        ),
        (
            [{"name": "a", "summary": "s", "body": " "}],
            "commands/tar.yaml:subcommands[0].body: must not be blank",
        ),
        (
            [{"name": "a", "summary": "s", "entry_name": "x y"}],
            "commands/tar.yaml:subcommands[0].entry_name: must not contain whitespace",
        ),
        (
            [{"name": "a", "summary": "s", "extra": 1}],
            "commands/tar.yaml:subcommands[0]: unknown key 'extra'",
        ),
        (
            [
                {"name": "a", "summary": "s"},
                {"name": "b", "summary": "s"},
                {"name": "a", "summary": "t"},
            ],
            "commands/tar.yaml:subcommands[2].name: duplicate subcommand 'a'",
        ),
    ],
)
def test_subcommand_errors(subcommands: object, message: str) -> None:
    assert error_of(valid_doc(subcommands=subcommands)).message == message


@pytest.mark.parametrize(
    ("related", "message"),
    [
        ("gzip", "commands/tar.yaml:related: must be a list"),
        ([1], "commands/tar.yaml:related[0]: must be a string"),
        (["a b"], "commands/tar.yaml:related[0]: must not contain whitespace"),
        (["tar"], "commands/tar.yaml:related[0]: must not be the command itself"),
        (["gzip", "zip", "gzip"], "commands/tar.yaml:related[2]: duplicate name 'gzip'"),
    ],
)
def test_related_errors(related: object, message: str) -> None:
    assert error_of(valid_doc(related=related)).message == message


@pytest.mark.parametrize(
    ("probe", "message"),
    [
        ("x", "commands/tar.yaml:help_probe: must be a mapping"),
        ({"profile": "two-col"}, "commands/tar.yaml:help_probe.args: required"),
        ({"args": ["a"]}, "commands/tar.yaml:help_probe.profile: required"),
        (
            {"args": ["a"], "profile": "two-col", "x": 1},
            "commands/tar.yaml:help_probe: unknown key 'x'",
        ),
        ({"args": "a", "profile": "two-col"}, "commands/tar.yaml:help_probe.args: must be a list"),
        (
            {"args": [], "profile": "two-col"},
            "commands/tar.yaml:help_probe.args: must not be empty",
        ),
        (
            {"args": [" "], "profile": "two-col"},
            "commands/tar.yaml:help_probe.args[0]: must not be blank",
        ),
        (
            {"args": ["a", "a b"], "profile": "two-col"},
            "commands/tar.yaml:help_probe.args[1]: must not contain whitespace",
        ),
        (
            {"args": [1], "profile": "two-col"},
            "commands/tar.yaml:help_probe.args[0]: must be a string",
        ),
        (
            {"args": ["a"], "profile": "table"},
            "commands/tar.yaml:help_probe.profile: must be one of two-col, git-list, brew-commands",
        ),
    ],
)
def test_help_probe_errors(probe: object, message: str) -> None:
    assert error_of(valid_doc(help_probe=probe)).message == message


def test_first_error_wins_in_documented_order() -> None:
    doc = valid_doc(summary="", intents=[], explain="")
    assert error_of(doc).message == f"{FILE}:summary: must not be blank"


def test_nested_mapping_unknown_key_beats_field_errors() -> None:
    doc = valid_doc(examples=[example(id="bad", extra=1)])
    assert error_of(doc).message == f"{FILE}:examples[0]: unknown key 'extra'"


def test_file_label_is_used_in_messages() -> None:
    assert error_of(valid_doc(summary=""), "commands/tar.yaml").message.startswith(
        "commands/tar.yaml:summary"
    )
    assert error_of(None, "x/tar.yaml").message == "x/tar.yaml: expected a mapping"


HUGE = 10**5000  # `repr` and `str` of an int this long raise ValueError
HIDDEN = "<integer too large to show>"


def test_over_long_integers_are_reported_not_raised() -> None:
    assert error_of(valid_doc(schema=HUGE)).message == (
        f"{FILE}:schema: unsupported schema {HIDDEN} (expected 1)"
    )
    assert error_of({**valid_doc(), HUGE: 1}).message == f"{FILE}: unknown key {HIDDEN}"
    assert error_of({**valid_doc(), (1, HUGE): 1}).message == f"{FILE}: unknown key {HIDDEN}"
    verify = {"mode": "exec", "bind": {"archive": "a", HUGE: "b"}}
    message = error_of(valid_doc(examples=[example(verify=verify)])).message
    assert message == f"{FILE}:examples[0].verify.bind: unknown placeholder {HIDDEN}"
    verify = {"mode": "exec", "bind": {"archive": "a", HUGE: 1}}
    message = error_of(valid_doc(examples=[example(verify=verify)])).message
    assert message == f"{FILE}:examples[0].verify.bind.{HIDDEN}: must be a string"


def test_non_string_bind_keys_are_reported_not_raised() -> None:
    verify = {"mode": "exec", "bind": {"archive": "a", 7: 1}}
    message = error_of(valid_doc(examples=[example(verify=verify)])).message
    assert message == f"{FILE}:examples[0].verify.bind.7: must be a string"


def test_validation_does_not_mutate_the_input() -> None:
    data = full_doc()
    snapshot = copy.deepcopy(data)
    validate_command(data, FILE)
    assert data == snapshot


def _too_long(number: int) -> int:
    return number << 20_000


JSON_LIKE = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.integers().map(_too_long)
    | st.floats()
    | st.text(max_size=12),
    lambda inner: (
        st.lists(inner, max_size=4)
        | st.dictionaries(
            st.text(max_size=8) | st.integers() | st.integers().map(_too_long), inner, max_size=4
        )
    ),
    max_leaves=12,
)


def _outcome(data: object) -> None:
    with contextlib.suppress(ContentError):
        validate_command(data, FILE)


@given(JSON_LIKE)
def test_arbitrary_data_never_leaks_other_exceptions(data: object) -> None:
    _outcome(data)


@given(
    st.sampled_from(
        [
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
        ]
    ),
    JSON_LIKE,
)
def test_replacing_a_top_level_field_never_leaks(key: str, value: object) -> None:
    _outcome(valid_doc(**{key: value}))


@given(st.sampled_from(["id", "desc", "cmd", "danger", "verify"]), JSON_LIKE)
def test_replacing_an_example_field_never_leaks(key: str, value: object) -> None:
    _outcome(valid_doc(examples=[example(**{key: value})]))


@given(
    st.sampled_from(
        ["mode", "setup", "bind", "expect_exit", "stdout_contains", "stdout_regex", "files_exist"]
    ),
    JSON_LIKE,
)
def test_replacing_a_verify_field_never_leaks(key: str, value: object) -> None:
    verify = {"mode": "exec", "bind": {"archive": "a"}}
    verify[key] = value  # type: ignore[assignment] # arbitrary JSON-like value on purpose
    _outcome(valid_doc(examples=[example(verify=verify)]))


@given(st.text(max_size=40), st.text(max_size=40))
def test_arbitrary_cmd_and_setup_text_never_leak(cmd: str, setup: str) -> None:
    verify = {"mode": "exec", "setup": setup}
    _outcome(valid_doc(examples=[example(cmd=cmd, verify=verify)]))
