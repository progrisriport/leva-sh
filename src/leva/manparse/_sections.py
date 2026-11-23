"""Split rendered man text into sections and extract the NAME data."""

from __future__ import annotations

from dataclasses import dataclass

from leva.manparse._name import MAX_SUMMARY, is_name, parse_name
from leva.model import Section

_DEFAULT_HEADING = "DESCRIPTION"


@dataclass(frozen=True, slots=True)
class ParsedMan:
    """The structured content of one rendered man page.

    Attributes:
        names: Names from NAME, in order of appearance; never empty, each a valid name.
        summary: One-line summary from NAME, at most 200 characters; may be empty.
        sections: Sections in order of appearance, with `ord` equal to the position.
        redirect_to: Target of a ``.so`` stub page; `parse_man` never sets it, ingest does.

    Raises:
        ValueError: If `names` is empty or holds an invalid name, `summary` is too long or
            spans lines, or the section `ord`s are not ``0..n-1`` in order.
    """

    names: tuple[str, ...]
    summary: str
    sections: tuple[Section, ...]
    redirect_to: str | None = None

    def __post_init__(self) -> None:
        if not self.names or not all(is_name(name) for name in self.names):
            raise ValueError(f"ParsedMan.names must be non-empty valid names: {self.names!r}")
        if len(self.summary) > MAX_SUMMARY or len(self.summary.splitlines()) > 1:
            raise ValueError(f"ParsedMan.summary must be one line of <= {MAX_SUMMARY} chars")
        if "\n" in self.summary or "\r" in self.summary:
            raise ValueError("ParsedMan.summary must not contain a line break")
        if [section.ord for section in self.sections] != list(range(len(self.sections))):
            raise ValueError("ParsedMan.sections ord must run 0..n-1 in order")


def parse_man(text: str, *, name_hint: str) -> ParsedMan:
    """Parse rendered, overstrike-free man text (D-027).

    The first and last non-blank lines (header and footer) are dropped. Every other column-0
    line with a letter opens a section; all other lines belong to the open section's body,
    which keeps its rendered indentation. Never raises for any `text`.

    Pre: `name_hint` is a valid name (non-empty, no whitespace); `text` has no overstrike.
    Post: sections in order of appearance (at least one); `names` never empty; `summary` one
    line of at most 200 characters; `redirect_to` is None.

    Args:
        text: Output of `ManRenderer.render`.
        name_hint: Command name used when NAME yields no valid name.

    Returns:
        The parsed page.

    Raises:
        ValueError: `name_hint` is not a valid name (programmer error).
    """
    if not is_name(name_hint):
        raise ValueError(f"name_hint must be non-empty without whitespace: {name_hint!r}")
    groups = _split(_inner_lines(text)) or [(_DEFAULT_HEADING, [])]
    sections = tuple(
        Section(heading, _body(lines), position) for position, (heading, lines) in enumerate(groups)
    )
    names, summary = parse_name(_name_body(sections), name_hint)
    return ParsedMan(names=names, summary=summary, sections=sections)


def _inner_lines(text: str) -> list[str]:
    """Return the right-stripped lines strictly between the first and last non-blank line."""
    lines = [line.rstrip() for line in text.splitlines()]
    filled = [index for index, line in enumerate(lines) if line]
    if len(filled) < 2:
        return []
    return lines[filled[0] + 1 : filled[-1]]


def _is_heading(line: str) -> bool:
    """Tell whether a right-stripped line opens a section: column 0 with at least one letter."""
    return line != "" and not line[0].isspace() and any(char.isalpha() for char in line)


def _split(inner: list[str]) -> list[tuple[str, list[str]]]:
    """Group `inner` lines under their headings; a non-blank preamble becomes DESCRIPTION."""
    groups: list[tuple[str, list[str]]] = [("", [])]
    for line in inner:
        if _is_heading(line):
            groups.append((line.strip(), []))
        else:
            groups[-1][1].append(line)
    preamble = groups[0]
    if any(preamble[1]):
        groups[0] = (_DEFAULT_HEADING, preamble[1])
        return groups
    return groups[1:]


def _body(lines: list[str]) -> str:
    """Join `lines` without leading and trailing blank lines, keeping indentation."""
    start = 0
    end = len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return "\n".join(lines[start:end])


def _name_body(sections: tuple[Section, ...]) -> str:
    """Return the body of the first NAME section, or an empty string."""
    return next((section.body for section in sections if section.heading.casefold() == "name"), "")
