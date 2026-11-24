"""Tests for the content providers, `content_version`, `default_root` and `attribution_text`."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import pytest

from leva.content import (
    ContentProvider,
    CuratedCommand,
    CuratedYamlProvider,
    TldrPage,
    TldrSnapshotProvider,
    attribution_text,
    content_version,
    default_root,
)
from leva.model import ContentError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
VALID_ROOT = FIXTURES / "content" / "valid"
SHA256_EMPTY = hashlib.sha256(b"").hexdigest()


def doc_text(name: str = "x", example_id: str | None = None) -> str:
    """Return the text of a minimal valid curated document."""
    return (
        "schema: 1\n"
        "kind: command\n"
        f"name: {name}\n"
        "summary: A synthetic command.\n"
        "explain: Used by the provider tests.\n"
        "intents:\n"
        "  - do something\n"
        "examples:\n"
        f"  - id: {example_id or f'{name}-run'}\n"
        "    desc: Run it\n"
        f"    cmd: {name}\n"
        "    verify:\n"
        "      mode: static\n"
    )


def write_command(root: Path, filename: str, text: str | bytes) -> Path:
    """Write `commands/<filename>` under `root` and return its path."""
    path = root / "commands" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def load_error(root: Path) -> str:
    """Return the message of the `ContentError` raised by loading `root`."""
    with pytest.raises(ContentError) as caught:
        list(CuratedYamlProvider(root).load())
    return caught.value.message


# --- CuratedYamlProvider -------------------------------------------------------------------


def test_curated_loads_fixture_files_in_name_order() -> None:
    commands = list(CuratedYamlProvider(VALID_ROOT).load())

    assert [command.name for command in commands] == ["alpha", "beta"]
    assert all(isinstance(command, CuratedCommand) for command in commands)
    assert commands[0].examples[0].id == "alpha-hello"


def test_curated_provider_satisfies_the_port() -> None:
    provider: ContentProvider = CuratedYamlProvider(VALID_ROOT)

    assert [record.name for record in provider.load()] == ["alpha", "beta"]


def test_curated_load_rereads_the_disk(tmp_path: Path) -> None:
    write_command(tmp_path, "a.yaml", doc_text("a"))
    provider = CuratedYamlProvider(tmp_path)
    first = list(provider.load())

    assert list(provider.load()) == first
    write_command(tmp_path, "b.yaml", doc_text("b"))

    assert [command.name for command in provider.load()] == ["a", "b"]


def test_curated_sorts_by_plain_file_name(tmp_path: Path) -> None:
    write_command(tmp_path, "ls.yaml", doc_text("ls"))
    write_command(tmp_path, "ls-a.yaml", doc_text("ls-a"))
    write_command(tmp_path, "B.yaml", doc_text("B"))

    assert [command.name for command in CuratedYamlProvider(tmp_path).load()] == [
        "B",
        "ls-a",
        "ls",
    ]


def test_curated_missing_commands_directory_yields_nothing(tmp_path: Path) -> None:
    assert list(CuratedYamlProvider(tmp_path).load()) == []


def test_curated_ignores_other_files_and_directories(tmp_path: Path) -> None:
    write_command(tmp_path, "a.yaml", doc_text("a"))
    write_command(tmp_path, "README.md", "# notes\n")
    write_command(tmp_path, "notes.txt", "not yaml: [\n")
    (tmp_path / "commands" / "sub.yaml").mkdir()
    (tmp_path / "commands" / "nested").mkdir()
    write_command(tmp_path / "commands" / "nested", "z.yaml", "broken: [\n")

    assert [command.name for command in CuratedYamlProvider(tmp_path).load()] == ["a"]


def test_curated_rejects_the_yml_extension(tmp_path: Path) -> None:
    write_command(tmp_path, "x.yml", doc_text("x"))

    assert load_error(tmp_path) == "commands/x.yml: use the .yaml extension"


def test_curated_rejects_invalid_utf8(tmp_path: Path) -> None:
    write_command(tmp_path, "x.yaml", b"schema: 1\nname: \xff\xfe\n")

    assert load_error(tmp_path) == "commands/x.yaml: not valid UTF-8"


def test_curated_reports_an_unreadable_file(tmp_path: Path) -> None:
    path = write_command(tmp_path, "x.yaml", doc_text("x"))
    path.chmod(0o000)
    try:
        message = load_error(tmp_path)
    finally:
        path.chmod(0o600)

    assert message == "commands/x.yaml: cannot read file"


def test_curated_reports_an_unreadable_directory(tmp_path: Path) -> None:
    write_command(tmp_path, "x.yaml", doc_text("x"))
    directory = tmp_path / "commands"
    directory.chmod(0o000)
    try:
        message = load_error(tmp_path)
    finally:
        directory.chmod(0o700)

    assert message == "commands: cannot read directory"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("schema: 1\nkind: command\nname: a: b\n", "commands/x.yaml: invalid YAML at line 3"),
        ("schema: 1\nkind: command\nname: [\n", "commands/x.yaml: invalid YAML at line 4"),
        ("a: 1\n---\nb: 2\n", "commands/x.yaml: invalid YAML at line 2"),
        ("a: !!python/object:os.system x\n", "commands/x.yaml: invalid YAML at line 1"),
        ("? [a, b]\n: 1\n", "commands/x.yaml: invalid YAML at line 1"),
        ("a: 1\x00\n", "commands/x.yaml: invalid YAML"),
        ("", "commands/x.yaml: expected a mapping"),
        ("- a\n- b\n", "commands/x.yaml: expected a mapping"),
    ],
    ids=[
        "mapping-value",
        "unclosed-flow",
        "two-documents",
        "unsafe-tag",
        "unhashable-key",
        "control-character",
        "empty-file",
        "sequence",
    ],
)
def test_curated_reports_yaml_problems(tmp_path: Path, text: str, message: str) -> None:
    write_command(tmp_path, "x.yaml", text)

    assert load_error(tmp_path) == message


def test_curated_rejects_a_duplicate_top_level_key(tmp_path: Path) -> None:
    write_command(tmp_path, "x.yaml", "schema: 1\nkind: command\nname: x\nname: y\n")

    assert load_error(tmp_path) == "commands/x.yaml: duplicate key 'name' at line 4"


def test_curated_rejects_a_duplicate_nested_key(tmp_path: Path) -> None:
    lines = doc_text("x").splitlines()
    lines.append("      mode: skip")
    write_command(tmp_path, "x.yaml", "\n".join(lines) + "\n")

    assert load_error(tmp_path) == "commands/x.yaml: duplicate key 'mode' at line 14"


def test_curated_rejects_a_duplicate_key_after_a_merge(tmp_path: Path) -> None:
    text = "base: &b {k: 1}\nthing:\n  <<: *b\n  other: 2\n  other: 3\n"
    write_command(tmp_path, "x.yaml", text)

    assert load_error(tmp_path) == "commands/x.yaml: duplicate key 'other' at line 5"


def test_curated_surfaces_validation_errors_with_the_label(tmp_path: Path) -> None:
    write_command(tmp_path, "x.yaml", doc_text("x").replace("summary: A synthetic command.\n", ""))

    assert load_error(tmp_path) == "commands/x.yaml:summary: required"


def test_curated_requires_the_stem_to_equal_the_name(tmp_path: Path) -> None:
    write_command(tmp_path, "y.yaml", doc_text("x"))

    assert load_error(tmp_path).startswith("commands/y.yaml:name: ")


def test_curated_rejects_an_example_id_used_in_two_files(tmp_path: Path) -> None:
    write_command(tmp_path, "ls-a.yaml", doc_text("ls-a", "ls-a-x"))
    write_command(tmp_path, "ls.yaml", doc_text("ls", "ls-a-x"))

    assert load_error(tmp_path) == (
        "commands/ls.yaml:examples[0].id: duplicate example id 'ls-a-x'"
        " (also in commands/ls-a.yaml)"
    )


def test_curated_yields_nothing_when_a_later_file_is_invalid(tmp_path: Path) -> None:
    write_command(tmp_path, "a.yaml", doc_text("a"))
    write_command(tmp_path, "b.yaml", "broken: [\n")
    seen: list[CuratedCommand] = []

    with pytest.raises(ContentError):
        seen.extend(CuratedYamlProvider(tmp_path).load())

    assert seen == []


# --- TldrSnapshotProvider ------------------------------------------------------------------


def page_line(**overrides: Any) -> str:
    """Return one JSONL line for a valid common page named `tar`."""
    data: dict[str, Any] = {
        "name": "tar",
        "platform": "common",
        "description": "Archive files.",
        "examples": [{"desc": "List", "cmd": "tar -tf {{archive}}"}],
    }
    data.update(overrides)
    return json.dumps(data)


def write_tldr(root: Path, stem: str, text: str | bytes) -> Path:
    """Write `tldr/<stem>.jsonl` under `root` and return its path."""
    path = root / "tldr" / f"{stem}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def tldr_error(root: Path) -> str:
    """Return the message of the `ContentError` raised by loading the snapshot in `root`."""
    with pytest.raises(ContentError) as caught:
        list(TldrSnapshotProvider(root).load())
    return caught.value.message


def test_tldr_merges_the_fixture_snapshot() -> None:
    pages = list(TldrSnapshotProvider(FIXTURES).load())

    assert [(page.name, page.platform) for page in pages] == [("alpha", "common"), ("beta", "osx")]
    alpha = pages[0]
    assert alpha.description == "Common alpha."
    assert [(item.desc, item.cmd) for item in alpha.examples] == [
        ("Say hi", "alpha --hi"),
        ("Say bye", "alpha --bye {{name}}"),
    ]
    assert pages[1].examples[0].cmd == "beta --mac"


def test_tldr_provider_satisfies_the_port() -> None:
    provider: ContentProvider = TldrSnapshotProvider(FIXTURES)

    assert [record.name for record in provider.load()] == ["alpha", "beta"]


def test_tldr_without_snapshot_files_yields_nothing(tmp_path: Path) -> None:
    assert list(TldrSnapshotProvider(tmp_path).load()) == []


def test_tldr_reads_a_lone_common_file(tmp_path: Path) -> None:
    write_tldr(tmp_path, "common", page_line() + "\n")

    pages = list(TldrSnapshotProvider(tmp_path).load())

    assert [(page.name, page.platform) for page in pages] == [("tar", "common")]


def test_tldr_osx_replaces_common_and_pages_are_sorted(tmp_path: Path) -> None:
    write_tldr(tmp_path, "common", page_line(name="zip") + "\n" + page_line() + "\n")
    write_tldr(tmp_path, "osx", page_line(name="tar", platform="osx", description="Mac.") + "\n")

    pages = list(TldrSnapshotProvider(tmp_path).load())

    assert [(page.name, page.platform, page.description) for page in pages] == [
        ("tar", "osx", "Mac."),
        ("zip", "common", "Archive files."),
    ]


def test_tldr_skips_blank_lines_but_counts_them(tmp_path: Path) -> None:
    write_tldr(tmp_path, "common", f"\n{page_line()}\n   \n{{not json\n")

    assert tldr_error(tmp_path) == "tldr/common.jsonl:4: invalid JSON"


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("{not json", "tldr/common.jsonl:1: invalid JSON"),
        ('{"a": NaN}', "tldr/common.jsonl:1: invalid JSON"),
        ("[" * 100_000, "tldr/common.jsonl:1: invalid JSON"),
        ("[1, 2]", "tldr/common.jsonl:1: expected an object"),
        ('{"name": "a", "name": "b"}', "tldr/common.jsonl:1: duplicate key 'name'"),
        (page_line(extra=1), "tldr/common.jsonl:1: unknown key 'extra'"),
        (
            json.dumps({"name": "tar", "platform": "common", "description": ""}),
            "tldr/common.jsonl:1: missing key 'examples'",
        ),
        (page_line(name="two words"), "tldr/common.jsonl:1:name: must be a command name"),
        (page_line(name=7), "tldr/common.jsonl:1:name: must be a command name"),
        (page_line(platform="osx"), "tldr/common.jsonl:1:platform: must be 'common'"),
        (page_line(description=None), "tldr/common.jsonl:1:description: must be a string"),
        (page_line(examples={}), "tldr/common.jsonl:1:examples: must be a list"),
        (
            page_line(examples=["x"]),
            "tldr/common.jsonl:1:examples[0]: expected an object with keys desc, cmd",
        ),
        (
            page_line(examples=[{"desc": "d", "cmd": "c", "extra": "e"}]),
            "tldr/common.jsonl:1:examples[0]: expected an object with keys desc, cmd",
        ),
        (
            page_line(examples=[{"desc": "d", "cmd": "c"}, {"desc": "d"}]),
            "tldr/common.jsonl:1:examples[1]: expected an object with keys desc, cmd",
        ),
        (
            page_line(examples=[{"desc": "d", "cmd": 3}]),
            "tldr/common.jsonl:1:examples[0]: expected an object with keys desc, cmd",
        ),
    ],
    ids=[
        "invalid-json",
        "nan",
        "too-deep",
        "not-an-object",
        "duplicate-key",
        "unknown-key",
        "missing-key",
        "bad-name",
        "name-not-a-string",
        "platform-not-the-stem",
        "description-not-a-string",
        "examples-not-a-list",
        "example-not-an-object",
        "example-extra-key",
        "example-missing-key",
        "example-non-string",
    ],
)
def test_tldr_reports_line_problems(tmp_path: Path, line: str, message: str) -> None:
    write_tldr(tmp_path, "common", line + "\n")

    assert tldr_error(tmp_path) == message


def test_tldr_rejects_a_duplicate_page_in_one_file(tmp_path: Path) -> None:
    write_tldr(tmp_path, "common", page_line(name="zip") + "\n" + page_line() + "\n" + page_line())

    assert tldr_error(tmp_path) == "tldr/common.jsonl:3:name: duplicate page 'tar'"


def test_tldr_reports_osx_errors_with_the_osx_label(tmp_path: Path) -> None:
    write_tldr(tmp_path, "common", page_line() + "\n")
    write_tldr(tmp_path, "osx", page_line() + "\n")

    assert tldr_error(tmp_path) == "tldr/osx.jsonl:1:platform: must be 'osx'"


def test_tldr_rejects_invalid_utf8(tmp_path: Path) -> None:
    write_tldr(tmp_path, "osx", b'{"name": "\xff"}\n')

    assert tldr_error(tmp_path) == "tldr/osx.jsonl: not valid UTF-8"


def test_tldr_reports_an_unreadable_file(tmp_path: Path) -> None:
    path = write_tldr(tmp_path, "common", page_line() + "\n")
    path.chmod(0o000)
    try:
        message = tldr_error(tmp_path)
    finally:
        path.chmod(0o600)

    assert message == "tldr/common.jsonl: cannot read file"


def test_tldr_yields_nothing_when_a_later_file_is_invalid(tmp_path: Path) -> None:
    write_tldr(tmp_path, "common", page_line() + "\n")
    write_tldr(tmp_path, "osx", "{not json\n")
    seen: list[TldrPage] = []

    with pytest.raises(ContentError):
        seen.extend(TldrSnapshotProvider(tmp_path).load())

    assert seen == []


def test_tldr_drops_examples_that_break_the_command_rules(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    examples = [
        {"desc": "bare newline", "cmd": "echo a\necho b"},
        {"desc": "kept", "cmd": "echo kept"},
        {"desc": "blank", "cmd": "  \n"},
        {"desc": "carriage return", "cmd": "echo a\rb"},
        {"desc": "continued", "cmd": "echo a \\\n  b"},
    ]
    write_tldr(tmp_path, "osx", page_line(platform="osx", examples=examples) + "\n")

    with caplog.at_level(logging.WARNING, logger="leva.content"):
        pages = list(TldrSnapshotProvider(tmp_path).load())

    assert [item.desc for item in pages[0].examples] == ["kept", "continued"]
    assert len(pages[0].to_examples()) == 2
    dropped = [r for r in caplog.records if r.getMessage().startswith("tldr example dropped:")]
    assert len(dropped) == 3
    assert {r.levelno for r in dropped} == {logging.WARNING}
    assert all(r.name == "leva.content" for r in dropped)
    assert dropped[0].getMessage().startswith("tldr example dropped: tldr/osx.jsonl:1: ")


def test_tldr_keeps_malformed_placeholders(tmp_path: Path) -> None:
    write_tldr(tmp_path, "common", page_line(examples=[{"desc": "d", "cmd": "a {{b"}]) + "\n")

    pages = list(TldrSnapshotProvider(tmp_path).load())

    assert pages[0].examples[0].cmd == "a {{b"


def test_every_fixture_tldr_page_converts_to_examples() -> None:
    for page in TldrSnapshotProvider(FIXTURES).load():
        assert len(page.to_examples()) == len(page.examples)


# --- content_version -----------------------------------------------------------------------


def build_tree(root: Path) -> None:
    """Write a small content tree under `root`."""
    write_command(root, "a.yaml", doc_text("a"))
    write_command(root, "b.yaml", doc_text("b"))
    write_tldr(root, "common", page_line() + "\n")


def test_version_is_64_lowercase_hex() -> None:
    version = content_version(VALID_ROOT)

    assert len(version) == 64
    assert version == version.lower()
    assert int(version, 16) >= 0


def test_version_of_an_empty_root_is_the_hash_of_nothing(tmp_path: Path) -> None:
    assert content_version(tmp_path) == SHA256_EMPTY


def test_version_follows_the_documented_recipe(tmp_path: Path) -> None:
    data = doc_text("a").encode()
    write_command(tmp_path, "a.yaml", data)
    (tmp_path / "tldr").mkdir()
    (tmp_path / "tldr" / "SOURCE.json").write_bytes(b"{}")
    digest = hashlib.sha256()
    digest.update(b"commands/a.yaml\0" + hashlib.sha256(data).digest())
    digest.update(b"tldr/SOURCE.json\0" + hashlib.sha256(b"{}").digest())

    assert content_version(tmp_path) == digest.hexdigest()


def test_version_equals_for_copies_of_the_same_tree(tmp_path: Path) -> None:
    build_tree(tmp_path / "one")
    shutil.copytree(tmp_path / "one", tmp_path / "two")

    assert content_version(tmp_path / "one") == content_version(tmp_path / "two")


def test_version_changes_with_one_byte_of_a_curated_file(tmp_path: Path) -> None:
    build_tree(tmp_path)
    before = content_version(tmp_path)

    write_command(tmp_path, "a.yaml", doc_text("a") + "#")

    assert content_version(tmp_path) != before


def test_version_changes_when_a_curated_file_is_added_or_renamed(tmp_path: Path) -> None:
    build_tree(tmp_path)
    before = content_version(tmp_path)

    write_command(tmp_path, "c.yaml", doc_text("c"))
    added = content_version(tmp_path)
    (tmp_path / "commands" / "c.yaml").rename(tmp_path / "commands" / "d.yaml")

    assert added != before
    assert content_version(tmp_path) not in {before, added}


def test_version_changes_when_source_json_appears_or_changes(tmp_path: Path) -> None:
    build_tree(tmp_path)
    before = content_version(tmp_path)
    source = tmp_path / "tldr" / "SOURCE.json"

    source.write_text("{}", encoding="utf-8")
    appeared = content_version(tmp_path)
    source.write_text('{"commit": "abc"}', encoding="utf-8")

    assert appeared != before
    assert content_version(tmp_path) not in {before, appeared}


def test_version_ignores_files_that_are_not_curated_content(tmp_path: Path) -> None:
    build_tree(tmp_path)
    before = content_version(tmp_path)

    write_tldr(tmp_path, "common", page_line(description="changed") + "\n")
    write_tldr(tmp_path, "osx", page_line(platform="osx") + "\n")
    (tmp_path / "README.md").write_text("readme", encoding="utf-8")
    (tmp_path / "ATTRIBUTION.md").write_text("credit", encoding="utf-8")
    write_command(tmp_path, "notes.txt", "notes")
    write_command(tmp_path, "x.yml", "ignored")
    (tmp_path / "commands" / "dir.yaml").mkdir()

    assert content_version(tmp_path) == before


def test_version_reports_an_unreadable_file(tmp_path: Path) -> None:
    path = write_command(tmp_path, "a.yaml", doc_text("a"))
    path.chmod(0o000)
    try:
        with pytest.raises(ContentError) as caught:
            content_version(tmp_path)
    finally:
        path.chmod(0o600)

    assert caught.value.message == "commands/a.yaml: cannot read file"


def test_version_reports_an_unreadable_directory(tmp_path: Path) -> None:
    write_command(tmp_path, "a.yaml", doc_text("a"))
    directory = tmp_path / "commands"
    directory.chmod(0o000)
    try:
        with pytest.raises(ContentError) as caught:
            content_version(tmp_path)
    finally:
        directory.chmod(0o700)

    assert caught.value.message == "commands: cannot read directory"


# --- bundled content -----------------------------------------------------------------------


def test_attribution_text_names_the_licence_and_the_project() -> None:
    text = attribution_text()

    assert "CC BY 4.0" in text
    assert "Leva" in text


def test_attribution_text_reports_an_unreadable_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Broken:
        def joinpath(self, name: str) -> _Broken:
            return self

        def read_text(self, encoding: str) -> str:
            raise OSError("boom")

    def broken_files(package: str) -> _Broken:
        return _Broken()

    monkeypatch.setattr("leva.content._version.resources.files", broken_files)

    with pytest.raises(ContentError) as caught:
        attribution_text()

    assert caught.value.message == "ATTRIBUTION.md: cannot read file"


def test_attribution_text_reports_undecodable_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Binary:
        def joinpath(self, name: str) -> _Binary:
            return self

        def read_text(self, encoding: str) -> str:
            return b"\xff".decode(encoding)

    def binary_files(package: str) -> _Binary:
        return _Binary()

    monkeypatch.setattr("leva.content._version.resources.files", binary_files)

    with pytest.raises(ContentError) as caught:
        attribution_text()

    assert caught.value.message == "ATTRIBUTION.md: cannot read file"


def test_default_root_holds_the_bundled_content() -> None:
    root = default_root()

    assert root.is_absolute()
    assert (root / "commands" / "ls.yaml").is_file()
    assert (root / "ATTRIBUTION.md").is_file()
