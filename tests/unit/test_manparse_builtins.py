"""Tests for `leva.manparse.extract_builtins` over synthetic zsh-like and bash-like pages."""

from __future__ import annotations

from pathlib import Path

import pytest

from leva.manparse import BuiltinDoc, ParsedMan, extract_builtins, first_sentence, parse_man

FIXTURES = Path(__file__).parent.parent / "fixtures" / "man"
HEADER = "LEVA-T(1)        General Commands Manual        LEVA-T(1)"
FOOTER = "macOS 27.0           November 1, 2026           macOS 27.0"


def _load(name: str, hint: str) -> ParsedMan:
    return parse_man((FIXTURES / name).read_text(encoding="utf-8"), name_hint=hint)


def _page(*sections: tuple[str, tuple[str, ...]]) -> ParsedMan:
    """Build a parsed page; each section's body lines are indented by five spaces."""
    inner: list[str] = []
    for heading, lines in sections:
        inner += [heading, *(f"     {line}" if line else "" for line in lines), ""]
    return parse_man("\n".join([HEADER, "", *inner, FOOTER, ""]), name_hint="leva-t")


def _by_name(docs: list[BuiltinDoc]) -> dict[str, BuiltinDoc]:
    return {doc.name: doc for doc in docs}


def _single(description: str) -> list[BuiltinDoc]:
    page = _page(("SHELL BUILTIN COMMANDS", ("cmd", f"        {description}")))
    return extract_builtins(page)


def test_zsh_layout_yields_sorted_unique_names() -> None:
    docs = extract_builtins(_load("builtins_zsh.txt", "leva-zshb"))

    assert [doc.name for doc in docs] == [
        "-",
        ".",
        "alias",
        "echo",
        "print",
        "source",
        "true",
        "unalias",
    ]


def test_zsh_grouped_terms_share_body_and_summary() -> None:
    docs = _by_name(extract_builtins(_load("builtins_zsh.txt", "leva-zshb")))

    assert docs["."].body == docs["source"].body
    assert docs["."].summary == docs["source"].summary
    assert docs["."].summary == "Reads commands from file and runs them in the current shell."
    assert docs["."].synopsis == ". file [ arg ... ]"
    assert docs["source"].synopsis == "source file [ arg ... ]"


def test_zsh_precommand_modifier_item() -> None:
    docs = _by_name(extract_builtins(_load("builtins_zsh.txt", "leva-zshb")))

    assert docs["-"].synopsis == "- simple command"
    assert docs["-"].summary.startswith("Marks the next word")


def test_zsh_same_name_variants_join_the_synopsis() -> None:
    docs = _by_name(extract_builtins(_load("builtins_zsh.txt", "leva-zshb")))

    assert docs["print"].synopsis == "print [ -nr ] [ arg ... ]\nprint -f format [ arg ... ]"


def test_zsh_nested_options_stay_in_the_body() -> None:
    docs = _by_name(extract_builtins(_load("builtins_zsh.txt", "leva-zshb")))

    body = docs["alias"].body
    assert "\n-g      Make the alias global." in body
    assert "\n        It is replaced anywhere in a command line." in body
    assert docs["alias"].summary == "Defines or lists aliases."


def test_zsh_inline_term_item() -> None:
    docs = _by_name(extract_builtins(_load("builtins_zsh.txt", "leva-zshb")))

    assert docs["true"].synopsis == "true"
    assert docs["true"].body == "Does nothing and succeeds.\nIt always exits with status zero."
    assert docs["true"].summary == "Does nothing and succeeds."


def test_bash_layout_skips_the_intro_paragraph() -> None:
    docs = extract_builtins(_load("builtins_bash.txt", "leva-bashb"))

    assert [doc.name for doc in docs] == [":", "[", "cd", "read", "test"]
    assert all("Unless stated" not in doc.body for doc in docs)


def test_bash_duplicate_name_keeps_the_first_item() -> None:
    docs = _by_name(extract_builtins(_load("builtins_bash.txt", "leva-bashb")))

    assert docs["read"].synopsis == "read [-r] [name ...]"
    assert (
        docs["read"].summary == "Reads one line from standard input and splits it into the names."
    )


def test_bash_test_and_bracket_share_the_description() -> None:
    docs = _by_name(extract_builtins(_load("builtins_bash.txt", "leva-bashb")))

    assert docs["test"].synopsis == "test expr"
    assert docs["["].synopsis == "[ expr ]"
    assert docs["test"].body == docs["["].body


def test_bash_nested_list_is_kept_in_the_body() -> None:
    docs = _by_name(extract_builtins(_load("builtins_bash.txt", "leva-bashb")))

    assert "\n-L      Follow symbolic links.\n        This is the default." in docs["cd"].body
    assert docs["cd"].summary == "Changes the current directory to dir."


def test_summary_is_the_first_sentence_only() -> None:
    assert _single("Change the directory. Then more.")[0].summary == "Change the directory."


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Is it ready? Yes.", "Is it ready?"),
        ("Stop now! Really.", "Stop now!"),
        ("no sentence end here", "no sentence end here"),
        ("see e.g. foo for more", "see e.g."),
    ],
)
def test_summary_heuristic(description: str, expected: str) -> None:
    assert _single(description)[0].summary == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Lists things. More text.", "Lists things."),
        ("no end here\n  wrapped", "no end here wrapped"),
        ("a" * 250, "a" * 200),
        ("", ""),
    ],
)
def test_first_sentence(text: str, expected: str) -> None:
    assert first_sentence(text) == expected


def test_summary_spans_wrapped_lines() -> None:
    page = _page(
        ("SHELL BUILTIN COMMANDS", ("cmd", "        Runs a thing that", "        wraps. Next."))
    )

    assert extract_builtins(page)[0].summary == "Runs a thing that wraps."


def test_summary_is_cut_at_200_chars_and_right_stripped() -> None:
    summary = _single(("word " * 60).strip())[0].summary

    assert len(summary) <= 200
    assert summary == summary.rstrip()
    assert summary.startswith("word word")


def test_custom_heading_selects_that_section() -> None:
    page = _page(
        ("SHELL BUILTIN COMMANDS", ("one", "        First.")),
        ("RESERVED WORDS", ("while", "        Loops.")),
    )

    assert [doc.name for doc in extract_builtins(page, "RESERVED WORDS")] == ["while"]
    assert [doc.name for doc in extract_builtins(page)] == ["one"]


def test_missing_heading_gives_no_builtins() -> None:
    assert extract_builtins(_load("builtins_zsh.txt", "leva-zshb"), "NO SUCH SECTION") == []


def test_repeated_matching_sections_are_all_scanned() -> None:
    page = _page(
        ("SHELL BUILTIN COMMANDS", ("zeta", "        Last.")),
        ("OTHER", ("x", "        Y.")),
        ("SHELL BUILTIN COMMANDS", ("alpha", "        First.", "", "beta", "        Second.")),
    )

    assert [doc.name for doc in extract_builtins(page)] == ["alpha", "beta", "zeta"]


def test_heading_match_is_exact() -> None:
    page = _page(("shell builtin commands", ("one", "        First.")))

    assert extract_builtins(page) == []


def test_extraction_is_deterministic_and_sorted() -> None:
    parsed = _load("builtins_zsh.txt", "leva-zshb")

    first = extract_builtins(parsed)
    assert first == extract_builtins(parsed)
    assert [doc.name for doc in first] == sorted(doc.name for doc in first)


def test_empty_section_gives_no_builtins() -> None:
    page = _page(("SHELL BUILTIN COMMANDS", ()))

    assert extract_builtins(page) == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"name": "a b"},
        {"summary": "x" * 201},
        {"summary": "two\nlines"},
        {"summary": "carriage\rreturn"},
        {"summary": "trailing newline\n"},
        {"summary": "next line\x85"},
    ],
)
def test_builtin_doc_invariants(kwargs: dict[str, str]) -> None:
    fields = {"name": "cd", "synopsis": "cd", "summary": "Changes.", "body": "Changes."}
    fields.update(kwargs)

    with pytest.raises(ValueError, match="BuiltinDoc"):
        BuiltinDoc(**fields)


def test_builtin_doc_accepts_a_200_char_summary() -> None:
    assert len(BuiltinDoc("cd", "cd", "x" * 200, "x" * 200).summary) == 200
