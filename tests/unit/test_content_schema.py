"""Tests for the `leva.content` schema types: invariants and conversions."""

from __future__ import annotations

import pytest

from leva import subcmd
from leva.content import (
    HELP_PROFILES,
    TLDR_PLATFORMS,
    VERIFY_MODES,
    CuratedCommand,
    ExampleSpec,
    HelpProbe,
    TldrExample,
    TldrPage,
    VerifySpec,
)


def _command(**overrides: object) -> CuratedCommand:
    fields: dict[str, object] = {
        "name": "tar",
        "section": None,
        "summary": "s",
        "explain": "e",
        "intents": ("i",),
        "tags": (),
        "notes": (),
        "examples": (),
        "subcommands": (),
        "related": (),
        "help_probe": None,
    }
    fields.update(overrides)
    return CuratedCommand(**fields)  # type: ignore[arg-type] # test helper passes a field dict


def test_help_profiles_equal_subcmd_profiles() -> None:
    assert HELP_PROFILES == subcmd.HELP_PROFILES


def test_constants_hold_the_documented_values() -> None:
    assert VERIFY_MODES == ("exec", "static", "skip")
    assert TLDR_PLATFORMS == ("common", "osx")


def test_verify_spec_defaults() -> None:
    spec = VerifySpec(mode="static")
    assert spec.setup == ""
    assert dict(spec.bind) == {}
    assert spec.expect_exit == 0
    assert spec.stdout_contains == ()
    assert spec.stdout_regex is None
    assert spec.files_exist == ()
    assert spec.reason is None
    assert spec.min_macos is None


def test_verify_spec_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="mode"):
        VerifySpec(mode="run")  # type: ignore[arg-type] # deliberately invalid


def test_verify_spec_bind_is_a_read_only_copy() -> None:
    source = {"a": "1"}
    spec = VerifySpec(mode="exec", bind=source)
    source["b"] = "2"
    assert dict(spec.bind) == {"a": "1"}
    assert spec.bind == {"a": "1"}
    with pytest.raises(TypeError):
        spec.bind["c"] = "3"  # type: ignore[index] # read-only mapping on purpose


def test_verify_spec_equality_and_no_hash() -> None:
    assert VerifySpec(mode="exec", bind={"a": "1"}) == VerifySpec(mode="exec", bind={"a": "1"})
    assert VerifySpec(mode="exec", bind={"a": "1"}) != VerifySpec(mode="exec")
    with pytest.raises(TypeError):
        hash(VerifySpec(mode="exec"))


def test_example_spec_maps_to_example() -> None:
    spec = ExampleSpec("tar-x", "extract", "tar -x", VerifySpec(mode="skip", reason="r"), "careful")
    example = spec.to_example()
    assert (example.id, example.desc, example.cmd) == ("tar-x", "extract", "tar -x")
    assert (example.source, example.verified, example.danger) == ("curated", "skip", "careful")


def test_example_spec_rejects_id_with_whitespace() -> None:
    with pytest.raises(ValueError, match="id"):
        ExampleSpec("a b", "d", "c", VerifySpec(mode="static"))


def test_help_probe_accepts_valid_values() -> None:
    probe = HelpProbe(("help",), "two-col")
    assert (probe.args, probe.profile) == (("help",), "two-col")


@pytest.mark.parametrize(
    ("args", "profile"),
    [((), "two-col"), (("",), "two-col"), (("x",), "table")],
)
def test_help_probe_rejects_invalid_values(args: tuple[str, ...], profile: str) -> None:
    with pytest.raises(ValueError, match="HelpProbe"):
        HelpProbe(args, profile)


def test_curated_command_rejects_bad_name() -> None:
    with pytest.raises(ValueError, match="name"):
        _command(name="")
    with pytest.raises(ValueError, match="name"):
        _command(name="a b")


def test_tldr_page_rejects_bad_name_and_platform() -> None:
    with pytest.raises(ValueError, match="name"):
        TldrPage("a b", "common", "d", ())
    with pytest.raises(ValueError, match="platform"):
        TldrPage("tar", "linux", "d", ())


def test_tldr_page_to_examples_numbers_from_one() -> None:
    page = TldrPage(
        "tar",
        "osx",
        "archiver",
        (TldrExample("list", "tar -tf {{file}}"), TldrExample("extract", "tar -xf {{file}}")),
    )
    examples = page.to_examples()
    assert [e.id for e in examples] == ["tar-tldr-1", "tar-tldr-2"]
    assert [e.desc for e in examples] == ["list", "extract"]
    assert [e.cmd for e in examples] == ["tar -tf {{file}}", "tar -xf {{file}}"]
    assert {(e.source, e.verified, e.danger) for e in examples} == {("tldr", "none", None)}


def test_tldr_page_to_examples_empty() -> None:
    assert TldrPage("tar", "common", "d", ()).to_examples() == ()
