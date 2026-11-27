"""Assemble the index entries from pages, stub aliases, executables and builtins (D-005)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final

from leva.ingest._pipeline import Page, StubAlias, page_label
from leva.manparse import BuiltinDoc, ParsedMan, extract_builtins
from leva.model import (
    Example,
    Kind,
    Note,
    Origin,
    Section,
    Subcommand,
    is_name,
)
from leva.sources import Executable

_log = logging.getLogger("leva.ingest")

ZSH_PAGE: Final = ("zshbuiltins", "1")
BASH_PAGE: Final = ("bash", "1")

_SECTION_ORDER: Final = {"1": 0, "8": 1}
_OTHER_SECTION: Final = 2
_NO_SECTION: Final = 3


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One entry to write, with everything the writer needs.

    Attributes:
        name: Entry name.
        section: Man section, or None for builtins and executables without a page.
        kind: What the entry is.
        origin: Where it comes from.
        summary: One-line summary, ``""`` when absent.
        path: Path of the first executable of that name, or None.
        has_man: Whether the entry has man page content.
        aliases: Other names, sorted in plain ``str`` order, unique, never `name`.
        sections: Man sections in order.
        parsed: The page; None for builtins and executables without a page.
        curated: Whether curated content exists (T-6.4).
        rank: Position among the entries of the same name; 0 is the primary one.
        explain: Curated explanation (T-6.4).
        intents: Curated intents (T-6.4).
        notes: Curated notes (T-6.4).
        examples: Curated and tldr examples (T-6.4).
        subcommands: Subcommands (T-6.4).
        related: Related command names (T-6.4).

    Raises:
        ValueError: If `name` or a set `section` is not a valid name, `kind` or `origin` is not
            an enum member, an alias is invalid, equals `name`, or the aliases are not sorted
            and unique, or `rank` is negative.
    """

    name: str
    section: str | None
    kind: Kind
    origin: Origin
    summary: str
    path: str | None
    has_man: bool
    aliases: tuple[str, ...] = ()
    sections: tuple[Section, ...] = ()
    parsed: ParsedMan | None = None
    curated: bool = False
    rank: int = 0
    explain: str = ""
    intents: tuple[str, ...] = ()
    notes: tuple[Note, ...] = ()
    examples: tuple[Example, ...] = ()
    subcommands: tuple[Subcommand, ...] = ()
    related: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not is_name(self.name):
            raise ValueError(f"CatalogEntry.name must be a valid name: {self.name!r}")
        if self.section is not None and not is_name(self.section):
            raise ValueError(f"CatalogEntry.section must be a valid name: {self.section!r}")
        if not isinstance(self.kind, Kind):
            raise ValueError(f"CatalogEntry.kind must be a Kind member: {self.kind!r}")
        if not isinstance(self.origin, Origin):
            raise ValueError(f"CatalogEntry.origin must be an Origin member: {self.origin!r}")
        _check_aliases(self.name, self.aliases)
        if self.rank < 0:
            raise ValueError(f"CatalogEntry.rank must be >= 0: {self.rank!r}")

    @property
    def key(self) -> tuple[str, str, str]:
        """Return ``(name, section or "", origin.value)``: the write order and unique key."""
        return (self.name, self.section or "", self.origin.value)


@dataclass(frozen=True, slots=True)
class Catalog:
    """The entries to write and the stubs that could not be attached.

    Attributes:
        entries: Entries sorted by `CatalogEntry.key`, ranks assigned.
        skipped: ``(label, reason)`` of every stub whose target has no entry, in input order.
    """

    entries: tuple[CatalogEntry, ...]
    skipped: tuple[tuple[str, str], ...]


def _check_aliases(name: str, aliases: Sequence[str]) -> None:
    if not all(is_name(alias) and alias != name for alias in aliases):
        raise ValueError(f"CatalogEntry.aliases must be valid names other than {name!r}")
    if list(aliases) != sorted(set(aliases)):
        raise ValueError(f"CatalogEntry.aliases must be sorted and unique: {tuple(aliases)!r}")


def rank_key(entry: CatalogEntry, position: int, *, use_curated: bool = True) -> tuple[int, ...]:
    """Return the D-005 sort key of `entry`; the smallest key of a name is its primary entry.

    The key is ``(not curated, not has_man, section order, kind order, origin order,
    position)``; the first part is left out unless `use_curated`. Section order: ``"1"`` 0,
    ``"8"`` 1, any other section 2, none 3. Kind order: builtin 1, else 0. Origin order:
    bash 1, else 0.

    Args:
        entry: The entry to rank.
        position: Its position in the key-sorted entry list (the future id order).
        use_curated: Whether curated entries come first.

    Returns:
        The key to sort by.
    """
    if entry.section is None:
        section = _NO_SECTION
    else:
        section = _SECTION_ORDER.get(entry.section, _OTHER_SECTION)
    parts = (
        int(not entry.has_man),
        section,
        int(entry.kind is Kind.BUILTIN),
        int(entry.origin is Origin.BASH),
        position,
    )
    return (int(not entry.curated), *parts) if use_curated else parts


def assign_ranks(entries: Sequence[CatalogEntry]) -> tuple[CatalogEntry, ...]:
    """Set the rank of every entry among the entries of its name (D-005).

    Pre: `entries` are sorted by key, so a position is the future id order.
    Post: same order; per name the rank is the position of the entry when the group is
    sorted by `rank_key`.

    Args:
        entries: Entries sorted by key.

    Returns:
        The entries with their ranks.
    """
    groups: defaultdict[str, list[int]] = defaultdict(list)
    for position, entry in enumerate(entries):
        groups[entry.name].append(position)
    ranked = list(entries)
    for positions in groups.values():
        ordered = sorted(positions, key=lambda pos: rank_key(entries[pos], pos))
        for rank, position in enumerate(ordered):
            ranked[position] = replace(entries[position], rank=rank)
    return tuple(ranked)


def build_catalog(
    pages: Sequence[Page],
    aliases: Sequence[StubAlias],
    executables: Sequence[Executable],
) -> Catalog:
    """Turn pages, stub aliases and executables into the entries to write (D-005, D-054).

    Pure: no I/O. The order of `pages` and `aliases` does not change the entries (they are
    sorted); `skipped` follows the order of `aliases`. The first executable of a name in
    `executables` wins.

    Args:
        pages: The winning pages of the pipeline.
        aliases: The stubs that point to another winning page.
        executables: The scanned executables, in bin-dir order.

    Returns:
        The catalog: entries sorted by key with ranks, and the stubs left out.
    """
    first = _first_executables(executables)
    extra, skipped = _stub_names(pages, aliases)
    entries = [_man_entry(item, first, extra) for item in pages]
    entries += _builtin_entries(pages)
    entries.sort(key=lambda entry: entry.key)
    entries += _executable_entries(entries, first)
    entries.sort(key=lambda entry: entry.key)
    return Catalog(assign_ranks(entries), skipped)


def _first_executables(executables: Iterable[Executable]) -> dict[str, Executable]:
    """Return the first executable of every name: the scanner order is bin-dir order."""
    first: dict[str, Executable] = {}
    for exe in executables:
        first.setdefault(exe.name, exe)
    return first


def _stub_names(
    pages: Sequence[Page], aliases: Sequence[StubAlias]
) -> tuple[dict[tuple[str, str], set[str]], tuple[tuple[str, str], ...]]:
    """Group the stub names by the (name, section) of their target page; list the orphans.

    A target that is itself a stub is followed to its own target (``a -> b -> c`` makes both
    ``a`` and ``b`` aliases of ``c``, as mandoc follows nested ``.so``); a cycle is an orphan.
    """
    targets = {(item.man.name, item.man.section) for item in pages}
    links = {(a.man.name, a.man.section): (a.target_name, a.target_section) for a in aliases}
    names: dict[tuple[str, str], set[str]] = defaultdict(set)
    skipped: list[tuple[str, str]] = []
    for alias in aliases:
        target = _follow(links, targets, (alias.target_name, alias.target_section))
        if target in targets:
            names[target].add(alias.man.name)
        else:
            reason = f"stub target not indexed: {alias.target_name}({alias.target_section})"
            _log.debug("%s: %s", page_label(alias.man), reason)
            skipped.append((page_label(alias.man), reason))
    return names, tuple(skipped)


def _follow(
    links: Mapping[tuple[str, str], tuple[str, str]],
    targets: set[tuple[str, str]],
    target: tuple[str, str],
) -> tuple[str, str]:
    """Follow stub links from `target` until a page, a non-stub or a repeated key."""
    seen: set[tuple[str, str]] = set()
    while target not in targets and target in links and target not in seen:
        seen.add(target)
        target = links[target]
    return target


def _man_entry(
    item: Page, first: dict[str, Executable], extra: dict[tuple[str, str], set[str]]
) -> CatalogEntry:
    """Build the entry of one page; its path is the first executable of its name."""
    man = item.man
    names = set(item.parsed.names) | extra.get((man.name, man.section), set())
    exe = first.get(man.name)
    return CatalogEntry(
        name=man.name,
        section=man.section,
        kind=Kind.MANPAGE_ONLY if exe is None else Kind.EXECUTABLE,
        origin=man.origin,
        summary=item.parsed.summary,
        path=None if exe is None else str(exe.path),
        has_man=True,
        aliases=tuple(sorted(names - {man.name})),
        sections=item.parsed.sections,
        parsed=item.parsed,
    )


def _builtin_entries(pages: Sequence[Page]) -> list[CatalogEntry]:
    """Build the builtin entries from the zsh and bash pages; a missing page gives none."""
    entries: list[CatalogEntry] = []
    for (name, section), origin in ((ZSH_PAGE, Origin.ZSH), (BASH_PAGE, Origin.BASH)):
        for item in pages:
            if (item.man.name, item.man.section) == (name, section):
                entries += [_builtin_entry(doc, origin) for doc in extract_builtins(item.parsed)]
    return entries


def _builtin_entry(doc: BuiltinDoc, origin: Origin) -> CatalogEntry:
    return CatalogEntry(
        name=doc.name,
        section=None,
        kind=Kind.BUILTIN,
        origin=origin,
        summary=doc.summary,
        path=None,
        has_man=True,
        sections=(Section("SYNOPSIS", doc.synopsis, 0), Section("DESCRIPTION", doc.body, 1)),
    )


def _executable_entries(
    entries: list[CatalogEntry], first: dict[str, Executable]
) -> list[CatalogEntry]:
    """Place the executables whose name is no entry name; attach them or add exe-only entries.

    An executable that is an alias of man entries goes to the best of them (`rank_key` without
    curated): the owner gets its path when it has none, else the executable is absorbed.
    Mutates `entries` in place for the owners and returns the exe-only entries to add.

    Pre: `entries` are sorted by key.
    """
    taken = {entry.name for entry in entries}
    owners: defaultdict[str, list[int]] = defaultdict(list)
    for position, entry in enumerate(entries):
        for alias in entry.aliases:
            owners[alias].append(position)
    added: list[CatalogEntry] = []
    for name in sorted(first.keys() - taken):
        exe = first[name]
        if name not in owners:
            added.append(_exe_only_entry(exe))
            continue
        best = min(owners[name], key=lambda pos: rank_key(entries[pos], pos, use_curated=False))
        if entries[best].path is None:
            entries[best] = replace(entries[best], path=str(exe.path), kind=Kind.EXECUTABLE)
    return added


def _exe_only_entry(exe: Executable) -> CatalogEntry:
    return CatalogEntry(
        name=exe.name,
        section=None,
        kind=Kind.EXECUTABLE,
        origin=exe.origin,
        summary="",
        path=str(exe.path),
        has_man=False,
    )
