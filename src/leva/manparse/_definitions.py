"""Parse man-page definition lists from their rendered layout (D-027)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_INLINE = re.compile(r"^(\S.*?) {2,}(\S.*)$")


@dataclass(frozen=True, slots=True)
class DefinitionItem:
    """One entry of a definition list.

    Attributes:
        terms: Stripped term texts in document order; never empty, none blank.
        description: Dedented description, nested lists keeping their relative indent; may be
            empty.

    Raises:
        ValueError: If `terms` is empty or a term is blank.
    """

    terms: tuple[str, ...]
    description: str

    def __post_init__(self) -> None:
        if not self.terms or not all(term.strip() for term in self.terms):
            raise ValueError(
                f"DefinitionItem.terms must be non-empty and not blank: {self.terms!r}"
            )


@dataclass(slots=True)
class _Pending:
    """An item being built: its terms and the raw lines of its description."""

    terms: list[str]
    first: str | None = None
    lines: list[str] = field(default_factory=list)
    collecting: bool = True

    def has_description(self) -> bool:
        return self.first is not None or bool(self.lines)

    def build(self) -> DefinitionItem:
        deeper = _dedent(self.lines)
        raw = [] if self.first is None else [self.first]
        return DefinitionItem(tuple(self.terms), _trim(raw + deeper))


def definition_items(body: str) -> list[DefinitionItem]:
    """Parse a section body into definition items by indentation (D-027, D-043).

    A term line sits at the body's minimal indent and its description deeper. Consecutive term
    lines form one item; an inline term (two or more spaces, then text) starts its description
    on its own line and closes the group. Never raises.

    Pre: `body` is the rendered text of a section; indents are relative to the body.
    Post: items in document order, terms stripped and non-blank, descriptions dedented with
    leading and trailing blank lines removed; deeper lines before the first term are ignored.

    Args:
        body: Section body with its rendered indentation.

    Returns:
        The items; empty when `body` has no non-blank line.
    """
    lines = body.splitlines()
    indents = [_indent(line) for line in lines if line.strip()]
    if not indents:
        return []
    base = min(indents)
    items: list[_Pending] = []
    for line in lines:
        _feed(items, line, base)
    return [item.build() for item in items]


def _feed(items: list[_Pending], line: str, base: int) -> None:
    """Fold one body line into the item list."""
    current = items[-1] if items else None
    if not line.strip():
        if current is not None:
            current.collecting = False
            if current.has_description():
                current.lines.append("")
    elif _indent(line) == base:
        _feed_term(items, line.strip())
    elif current is not None:
        current.collecting = False
        current.lines.append(line.rstrip())


def _feed_term(items: list[_Pending], text: str) -> None:
    """Add a base-indent line as a term, grouping it with the previous term line if open."""
    inline = _INLINE.match(text)
    term, first = (inline.group(1).rstrip(), inline.group(2)) if inline else (text, None)
    if items and items[-1].collecting:
        items[-1].terms.append(term)
    else:
        items.append(_Pending([term]))
    if first is not None:
        items[-1].first = first
        items[-1].collecting = False


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _dedent(lines: list[str]) -> list[str]:
    """Remove the minimal indent of the non-blank `lines`; blank lines become empty."""
    filled = [_indent(line) for line in lines if line.strip()]
    cut = min(filled, default=0)
    return [line[cut:] if line.strip() else "" for line in lines]


def _trim(lines: list[str]) -> str:
    """Join `lines` without trailing blank lines (a description never starts blank)."""
    end = len(lines)
    while end > 0 and not lines[end - 1]:
        end -= 1
    return "\n".join(lines[:end])
