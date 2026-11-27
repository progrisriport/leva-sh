"""Attach curated content, tldr examples and subcommands to the catalog entries (D-055)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final, Protocol, TypeAlias

from leva.content import CuratedCommand, TldrPage
from leva.ingest._catalog import CatalogEntry, assign_ranks, rank_key
from leva.ingest._progress import ProgressSink
from leva.model import IngestError, Kind, Subcommand
from leva.sources import Executable
from leva.subcmd import (
    HelpTextExtractor,
    HyphenPageExtractor,
    KnownPage,
    SectionListExtractor,
    SubcommandExtractor,
    merge_subcommands,
)

_log = logging.getLogger("leva.ingest")

NOT_INSTALLED: Final = "curated command not installed"
DEFAULT_EXTRACTORS: Final[tuple[SubcommandExtractor, ...]] = (
    SectionListExtractor(),
    HyphenPageExtractor(),
)

_SYNOPSIS: Final = "synopsis"


class Prober(Protocol):
    """Port: run the allowlisted help probe of a command; `ProbeRunner` satisfies it."""

    def run(self, command: str) -> str:
        """Return the probe output of `command`.

        Raises:
            IngestError: If the probe is not allowed, fails, times out or prints nothing.
        """
        ...


ProbeFactory: TypeAlias = Callable[[Mapping[str, tuple[str, ...]]], Prober]


@dataclass(frozen=True, slots=True)
class Enrichment:
    """The enriched entries and what could not be attached.

    Attributes:
        entries: The input entries in the same (key) order, ranks recomputed.
        skipped: ``(curated name, NOT_INSTALLED)`` for every curated command without an entry,
            in curated order.
        curated: Number of entries with `curated` set.
    """

    entries: tuple[CatalogEntry, ...]
    skipped: tuple[tuple[str, str], ...]
    curated: int


def probe_allowlist(
    curated: Sequence[CuratedCommand], executables: Sequence[Executable]
) -> dict[str, tuple[str, ...]]:
    """Build the help-probe allowlist: command name to the full argv (D-009).

    Post: one item per curated command that has a `help_probe` and an executable of that name;
    the binary is the first executable of that name in `executables` (scan order).

    Args:
        curated: Curated commands.
        executables: Scanned executables in bin-dir order.

    Returns:
        ``{name: (str(path), *help_probe.args)}`` in curated order.
    """
    first: dict[str, Executable] = {}
    for exe in executables:
        first.setdefault(exe.name, exe)
    return {
        cmd.name: (str(first[cmd.name].path), *cmd.help_probe.args)
        for cmd in curated
        if cmd.help_probe is not None and cmd.name in first
    }


def known_pages(entries: Sequence[CatalogEntry]) -> dict[str, KnownPage]:
    """Describe the man pages the subcommand extractors may match (D-008).

    Pre: `entries` carry their ranks.
    Post: one item per name of a man-backed entry (`has_man`, not a builtin), taken from the
    entry with the lowest rank; `synopsis` is the body of the first section whose heading
    casefolds to ``synopsis``, ``""`` when there is none.

    Args:
        entries: The catalog entries.

    Returns:
        The known pages by entry name.
    """
    best: dict[str, CatalogEntry] = {}
    for entry in entries:
        if not entry.has_man or entry.kind is Kind.BUILTIN:
            continue
        current = best.get(entry.name)
        if current is None or entry.rank < current.rank:
            best[entry.name] = entry
    return {name: KnownPage(name, entry.summary, _synopsis(entry)) for name, entry in best.items()}


def enrich(
    entries: Sequence[CatalogEntry],
    *,
    curated: Sequence[CuratedCommand],
    tldr: Sequence[TldrPage],
    executables: Sequence[Executable],
    probe_factory: ProbeFactory,
    progress: ProgressSink,
    extractors: Sequence[SubcommandExtractor] = DEFAULT_EXTRACTORS,
) -> Enrichment:
    """Attach curated content, tldr examples and subcommands to `entries` (D-055).

    Pre: `entries` are the key-sorted entries of `build_catalog`, ranks assigned.
    Post: same order; curated entries (those a curated command found) are re-ranked first
    within their name; tldr examples follow the curated ones on the rank-0 entry of a name;
    probe failures only warn.

    Args:
        entries: The catalog entries.
        curated: Curated commands.
        tldr: tldr pages, one per name.
        executables: Scanned executables in bin-dir order (for the probe allowlist).
        probe_factory: Builds the prober from the allowlist; called exactly once.
        progress: Receives the ``enrich`` phase, one advance per entry and probe warnings.
        extractors: Subcommand extractors run on every entry.

    Returns:
        The enriched entries, the curated commands without an entry and the curated count.
    """
    progress.phase("enrich", len(entries))
    attached, skipped, targets = _attach_curated(entries, curated)
    ranked = _attach_tldr(assign_ranks(attached), tldr)
    known = known_pages(ranked)
    commands = {cmd.name: cmd for cmd in targets.values()}
    allowlist = probe_allowlist(list(commands.values()), executables)
    profiles = {
        cmd.name: cmd.help_probe.profile
        for cmd in commands.values()
        if cmd.help_probe is not None and cmd.name in allowlist
    }
    probes = _probe_subcommands(allowlist, profiles, probe_factory, progress, known)
    result: list[CatalogEntry] = []
    for position, entry in enumerate(ranked):
        cmd = targets.get(position)
        own = () if cmd is None else cmd.subcommands
        probed = () if cmd is None else probes.get(cmd.name, ())
        subs = _subcommands(entry, known, extractors, own, probed)
        result.append(replace(entry, subcommands=subs) if subs else entry)
        progress.advance()
    return Enrichment(tuple(result), skipped, len(targets))


def _synopsis(entry: CatalogEntry) -> str:
    """Return the body of the first SYNOPSIS section of `entry`, or the empty string."""
    return next((item.body for item in entry.sections if item.heading.casefold() == _SYNOPSIS), "")


def _find_target(
    by_name: Mapping[str, Sequence[int]], entries: Sequence[CatalogEntry], cmd: CuratedCommand
) -> int | None:
    """Return the position of the best entry for `cmd`, or None (D-005, D-055).

    Exact name, and the section when `cmd` sets one; best by `rank_key` without curated.
    """
    candidates = [
        pos
        for pos in by_name.get(cmd.name, ())
        if cmd.section is None or entries[pos].section == cmd.section
    ]
    return min(
        candidates, key=lambda pos: rank_key(entries[pos], pos, use_curated=False), default=None
    )


def _attach_curated(
    entries: Sequence[CatalogEntry], curated: Sequence[CuratedCommand]
) -> tuple[list[CatalogEntry], tuple[tuple[str, str], ...], dict[int, CuratedCommand]]:
    """Set the curated fields on the target entry of every curated command.

    Returns:
        The entries (same order), the commands without a target as ``(name, NOT_INSTALLED)``,
        and the command attached at each position.
    """
    by_name: defaultdict[str, list[int]] = defaultdict(list)
    for pos, entry in enumerate(entries):
        by_name[entry.name].append(pos)
    names = {entry.name for entry in entries} | {a for entry in entries for a in entry.aliases}
    result = list(entries)
    skipped: list[tuple[str, str]] = []
    targets: dict[int, CuratedCommand] = {}
    for cmd in curated:
        position = _find_target(by_name, entries, cmd)
        if position is None:
            skipped.append((cmd.name, NOT_INSTALLED))
            continue
        result[position] = _with_curated(result[position], cmd, names)
        targets[position] = cmd
    return result, tuple(skipped), targets


def _with_curated(entry: CatalogEntry, cmd: CuratedCommand, names: set[str]) -> CatalogEntry:
    """Return `entry` with the content of `cmd`; related names that resolve are kept."""
    related = tuple(name for name in cmd.related if name in names)
    if len(related) != len(cmd.related):
        _log.debug("%s: related names without an entry dropped: %s", cmd.name, cmd.related)
    return replace(
        entry,
        curated=True,
        summary=cmd.summary,
        explain=cmd.explain,
        intents=cmd.intents,
        notes=cmd.notes,
        examples=tuple(spec.to_example() for spec in cmd.examples),
        related=related,
    )


def _attach_tldr(
    entries: Sequence[CatalogEntry], pages: Sequence[TldrPage]
) -> tuple[CatalogEntry, ...]:
    """Append the tldr examples of each page to the rank-0 entry of its name."""
    primary = {entry.name: position for position, entry in enumerate(entries) if entry.rank == 0}
    result = list(entries)
    for page in pages:
        position = primary.get(page.name)
        if position is None:
            _log.debug("tldr page without an entry: %s", page.name)
            continue
        entry = result[position]
        result[position] = replace(entry, examples=entry.examples + page.to_examples())
    return tuple(result)


def _probe_subcommands(
    allowlist: Mapping[str, tuple[str, ...]],
    profiles: Mapping[str, str],
    probe_factory: ProbeFactory,
    progress: ProgressSink,
    known: Mapping[str, KnownPage],
) -> dict[str, list[Subcommand]]:
    """Run the allowed probes in name order; a failed probe warns and gives nothing (D-009)."""
    prober = probe_factory(allowlist)
    found: dict[str, list[Subcommand]] = {}
    for name in sorted(allowlist):
        try:
            text = prober.run(name)
        except IngestError as exc:
            _log.warning("help probe failed: %s", exc.message)
            progress.warn(exc.message)
            continue
        found[name] = HelpTextExtractor(profiles[name], text).extract(name, None, known)
    return found


def _subcommands(
    entry: CatalogEntry,
    known: Mapping[str, KnownPage],
    extractors: Sequence[SubcommandExtractor],
    curated: Sequence[Subcommand],
    probed: Sequence[Subcommand],
) -> tuple[Subcommand, ...]:
    """Merge curated, probe and extractor subcommands of `entry` by priority (D-044)."""
    extracted = [ex.extract(entry.name, entry.parsed, known) for ex in extractors]
    return tuple(merge_subcommands([curated, probed, *extracted]))
