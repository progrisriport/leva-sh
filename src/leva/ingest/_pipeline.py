"""Turn located man files into rendered and parsed pages, in parallel and deterministically."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from leva.ingest._progress import CANCELLED, CancelToken, ProgressSink
from leva.manparse import ManRenderer, ParsedMan, parse_man, read_man_source, stub_target
from leva.model import IngestError, ManRenderError
from leva.sources import ManFile

DEFAULT_WORKERS: Final = 8
MAX_FAILURE_RATIO: Final = 0.2
UNREADABLE: Final = "man pages unreadable; run leva doctor"

_Key = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Page:
    """A rendered page: becomes the entry (man.name, man.section, man.origin).

    Attributes:
        man: The winning man file.
        parsed: Its parsed content; `redirect_to` is the raw ``.so`` argument for a stub
            rendered as itself, else None.
    """

    man: ManFile
    parsed: ParsedMan


@dataclass(frozen=True, slots=True)
class StubAlias:
    """A winning stub whose target is another winning page: `man.name` becomes its alias."""

    man: ManFile
    target_name: str
    target_section: str


@dataclass(frozen=True, slots=True)
class PageSet:
    """The result of `render_pages`, every tuple in input (winner) order.

    Attributes:
        pages: Rendered pages.
        aliases: Stubs that point to another winning page.
        skipped: ``(label, reason)`` of every page that was read or rendered with an error,
            plus the stubs without a usable target.
    """

    pages: tuple[Page, ...]
    aliases: tuple[StubAlias, ...]
    skipped: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _Skip:
    """A page left out without counting as a failure."""

    reason: str


@dataclass(frozen=True, slots=True)
class _Failure:
    """A page that could not be read or rendered."""

    reason: str


@dataclass(frozen=True, slots=True)
class _Cancelled:
    """A page not processed because the build was cancelled."""


_Outcome = Page | StubAlias | _Skip | _Failure | _Cancelled


def page_label(man: ManFile) -> str:
    """Return the label of a page in messages, such as ``ls(1)``."""
    return f"{man.name}({man.section})"


def select_winners(files: Iterable[ManFile]) -> list[ManFile]:
    """Keep the first `ManFile` of each (name, section) in the given order (D-005).

    Args:
        files: Man files sorted as `ManPageLocator.locate` yields them.

    Returns:
        The winners, in the input order.
    """
    seen: set[_Key] = set()
    winners: list[ManFile] = []
    for man in files:
        key = (man.name, man.section)
        if key not in seen:
            seen.add(key)
            winners.append(man)
    return winners


def resolve_stub(man: ManFile, raw: str) -> Path | None:
    """Resolve the raw ``.so`` argument `raw` of the stub `man` to an existing regular file.

    Candidates in order: the man root (``man.path.parent.parent``), then the page directory
    (``man.path.parent``), each as written and with ``.gz`` appended (not when `raw` already
    ends in ``.gz``). Never raises: an `OSError` while checking counts as missing.

    Returns:
        The first candidate that is a regular file, or None.
    """
    suffixes = ("",) if raw.endswith(".gz") else ("", ".gz")
    for base in (man.path.parent.parent, man.path.parent):
        for suffix in suffixes:
            candidate = base / f"{raw}{suffix}"
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
    return None


def _owners(files: Iterable[ManFile]) -> dict[str, _Key]:
    """Map the real path of every man file to its (name, section); the first file wins."""
    owners: dict[str, _Key] = {}
    for man in files:
        owners.setdefault(os.path.realpath(str(man.path)), (man.name, man.section))
    return owners


def _stub_outcome(
    man: ManFile, raw: str, renderer: ManRenderer, owners: Mapping[str, _Key]
) -> _Outcome:
    """Decide what the stub `man` with argument `raw` becomes (D-005)."""
    target = resolve_stub(man, raw)
    if target is None:
        return _Skip(f"stub target missing: {raw}")
    key = owners.get(os.path.realpath(str(target)))
    if key == (man.name, man.section):
        return _Skip(f"stub points to itself: {raw}")
    if key is not None:
        return StubAlias(man, *key)
    parsed = parse_man(renderer.render(man.path), name_hint=man.name)
    return Page(man, replace(parsed, redirect_to=raw))


def _build(man: ManFile, renderer: ManRenderer, owners: Mapping[str, _Key]) -> _Outcome:
    """Read, classify and render `man`; may raise `ManRenderError`."""
    raw = stub_target(read_man_source(man.path))
    if raw is not None:
        return _stub_outcome(man, raw, renderer, owners)
    return Page(man, parse_man(renderer.render(man.path), name_hint=man.name))


def _process(
    man: ManFile,
    renderer: ManRenderer,
    owners: Mapping[str, _Key],
    cancel: CancelToken | None,
) -> _Outcome:
    """Worker body: one page into exactly one outcome, never raising `ManRenderError`."""
    if cancel is not None and cancel.is_set():
        return _Cancelled()
    try:
        return _build(man, renderer, owners)
    except ManRenderError as exc:
        return _Failure(exc.message)


def _collect(
    winners: Sequence[ManFile],
    futures: Sequence[Future[_Outcome]],
    progress: ProgressSink,
    cancel: CancelToken | None,
) -> list[_Outcome]:
    """Consume the futures in input order, reporting progress; raise when cancelled."""
    outcomes: list[_Outcome] = []
    for man, future in zip(winners, futures, strict=True):
        if cancel is not None and cancel.is_set():
            raise IngestError(CANCELLED)
        outcome = future.result()
        if isinstance(outcome, _Cancelled):
            raise IngestError(CANCELLED)
        progress.advance()
        if isinstance(outcome, _Skip | _Failure):
            progress.warn(f"{page_label(man)}: {outcome.reason}")
        outcomes.append(outcome)
    return outcomes


def _assemble(winners: Sequence[ManFile], outcomes: Sequence[_Outcome]) -> PageSet:
    """Split the outcomes into pages, aliases and skipped, raising above the failure limit."""
    pages = tuple(outcome for outcome in outcomes if isinstance(outcome, Page))
    aliases = tuple(outcome for outcome in outcomes if isinstance(outcome, StubAlias))
    skipped = tuple(
        (page_label(man), outcome.reason)
        for man, outcome in zip(winners, outcomes, strict=True)
        if isinstance(outcome, _Skip | _Failure)
    )
    failures = sum(1 for outcome in outcomes if isinstance(outcome, _Failure))
    if failures > MAX_FAILURE_RATIO * len(winners):
        raise IngestError(UNREADABLE)
    return PageSet(pages, aliases, skipped)


def render_pages(
    files: Sequence[ManFile],
    renderer: ManRenderer,
    progress: ProgressSink,
    *,
    workers: int = DEFAULT_WORKERS,
    cancel: CancelToken | None = None,
) -> PageSet:
    """Render and parse the winning man pages of `files` on `workers` threads.

    Pages are picked per D-005 (`select_winners`), stubs are classified before rendering
    (`.so` to another page gives a `StubAlias`, to a file outside every man dir renders the
    stub itself with `redirect_to` set, a missing target or a self-reference is skipped).
    Results keep the input order whatever the thread timing. The pipeline reports
    ``progress.phase("render", n)``, one ``advance`` per page and one ``warn`` per skip or
    failure.

    Args:
        files: Man files sorted as `ManPageLocator.locate` yields them.
        renderer: Port that renders a page file to text.
        progress: Receives phase, advance and warn events.
        workers: Number of threads, at least 1.
        cancel: Checked before every page; once set, pending pages are not processed.

    Returns:
        The pages, stub aliases and skipped pages.

    Raises:
        ValueError: `workers` is below 1.
        IngestError: The build was cancelled (``build cancelled``), or more than 20% of the
            winning pages could not be read or rendered (``man pages unreadable; ...``).
    """
    if workers < 1:
        raise ValueError(f"workers must be >= 1: {workers}")
    winners = select_winners(files)
    progress.phase("render", len(winners))
    owners = _owners(files)
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [pool.submit(_process, man, renderer, owners, cancel) for man in winners]
        outcomes = _collect(winners, futures, progress, cancel)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return _assemble(winners, outcomes)
