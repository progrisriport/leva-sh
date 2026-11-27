"""Build the index: scan, render, enrich, write and atomically swap it in (D-056)."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from leva.content import (
    ContentProvider,
    CuratedCommand,
    TldrPage,
    attribution_text,
    content_version,
)
from leva.ingest._catalog import CatalogEntry, build_catalog
from leva.ingest._enrich import DEFAULT_EXTRACTORS, ProbeFactory, enrich
from leva.ingest._fingerprint import Fingerprint, Staleness, compute_fingerprint, staleness
from leva.ingest._lock import LOCK_NAME, index_lock
from leva.ingest._pipeline import DEFAULT_WORKERS, render_pages
from leva.ingest._progress import CANCELLED, CancelToken, ProgressSink
from leva.manparse import ManRenderer
from leva.model import IngestError, Kind
from leva.sources import ExecutableScanner, ManPageLocator, ProbeRunner, SystemInfo
from leva.store import IndexWriter, NewEntry
from leva.subcmd import SubcommandExtractor

_NEW_SUFFIX = ".new"


@dataclass(frozen=True, slots=True)
class BuildReport:
    """What a finished build produced.

    Attributes:
        entries: Number of entries written.
        man_pages: Entries with man page content that are not builtins.
        skipped: ``(label, reason)`` of everything left out: the pipeline's, then the
            catalog's, then the enrichment's.
        curated: Number of entries with curated content.
        seconds: Wall time of the build.
        digest: The ``index_digest`` of the new index.
    """

    entries: int
    man_pages: int
    skipped: tuple[tuple[str, str], ...]
    curated: int
    seconds: float
    digest: str


@dataclass(frozen=True, slots=True)
class _Built:
    """The outcome of producing a new index file, before the swap."""

    entries: tuple[CatalogEntry, ...]
    skipped: tuple[tuple[str, str], ...]
    curated: int
    digest: str


class IndexBuilder:
    """Build the index from the installed man pages, executables and bundled content."""

    def __init__(
        self,
        *,
        executables: ExecutableScanner,
        man: ManPageLocator,
        renderer: ManRenderer,
        providers: Sequence[ContentProvider],
        system: SystemInfo,
        config_digest: str,
        clock: Callable[[], datetime],
        leva_version: str,
        content_root: Path,
        extractors: Sequence[SubcommandExtractor] = DEFAULT_EXTRACTORS,
        probe_factory: ProbeFactory = ProbeRunner,
        workers: int = DEFAULT_WORKERS,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        """Remember the collaborators; does no I/O.

        Args:
            executables: Scanner of the bin directories.
            man: Locator of the man page files.
            renderer: Renders man pages to text.
            providers: Content providers, drained in order.
            system: macOS version and build.
            config_digest: ``LevaConfig.digest()``.
            clock: Returns the timezone-aware build time.
            leva_version: Leva's own version.
            content_root: Content root hashed by `content_version`.
            extractors: Subcommand extractors run on every entry.
            probe_factory: Builds the help prober from the probe allowlist.
            workers: Threads used to render man pages.
            timer: Monotonic seconds, for `BuildReport.seconds`.

        Raises:
            ValueError: If `workers` is below 1.
        """
        if workers < 1:
            raise ValueError(f"workers must be >= 1: {workers!r}")
        self._executables = executables
        self._man = man
        self._renderer = renderer
        self._providers = tuple(providers)
        self._system = system
        self._config_digest = config_digest
        self._clock = clock
        self._leva_version = leva_version
        self._content_root = content_root
        self._extractors = tuple(extractors)
        self._probe_factory = probe_factory
        self._workers = workers
        self._timer = timer

    def fingerprint(self) -> Fingerprint:
        """Return the fingerprint of the current state, as a build would store it.

        Raises:
            ContentError: If the content files cannot be read.
        """
        return self._fingerprint(content_version(self._content_root))

    def staleness(self, index_db: Path) -> Staleness:
        """Compare the index at `index_db` with the current state."""
        return staleness(index_db, self.fingerprint())

    def build(
        self, target: Path, progress: ProgressSink, *, cancel: CancelToken | None = None
    ) -> BuildReport:
        """Build the index into ``<target>.new`` and swap it over `target`.

        Post: `target` is a valid index; on any failure the previous `target` is untouched and
        the ``.new`` file is removed. The phases are ``scan``, ``render``, ``enrich``,
        ``write`` and ``finalize``. An exclusive lock on ``index.lock`` next to `target`
        keeps two builds apart.

        Args:
            target: Path of the index file; its directory is created when missing.
            progress: Receives the phases, advances and warnings.
            cancel: Checked between phases and entries; once set the build stops.

        Returns:
            The report of the build.

        Raises:
            IngestError: The lock is busy, the index cannot be written, too many man pages are
                unreadable or the build was cancelled.
            ContentError: The curated or tldr content is invalid.
        """
        start = self._timer()
        new = target.with_name(target.name + _NEW_SUFFIX)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with index_lock(target.parent / LOCK_NAME):
                built = self._build_locked(target, new, progress, cancel)
        except OSError as exc:
            raise IngestError(f"cannot write index: {target}") from exc
        return BuildReport(
            entries=len(built.entries),
            man_pages=sum(1 for e in built.entries if e.has_man and e.kind is not Kind.BUILTIN),
            skipped=built.skipped,
            curated=built.curated,
            seconds=self._timer() - start,
            digest=built.digest,
        )

    def _fingerprint(self, version: str) -> Fingerprint:
        return compute_fingerprint(
            leva_version=self._leva_version,
            content_version=version,
            system=self._system,
            man_dirs=self._man.dirs,
            sections=self._man.sections,
            bin_dirs=self._executables.dirs,
            config_digest=self._config_digest,
        )

    def _build_locked(
        self, target: Path, new: Path, progress: ProgressSink, cancel: CancelToken | None
    ) -> _Built:
        new.unlink(missing_ok=True)
        try:
            built = self._produce(new, progress, cancel)
            new.replace(target)
        except BaseException:
            with contextlib.suppress(OSError):
                new.unlink(missing_ok=True)
            raise
        return built

    def _produce(self, new: Path, progress: ProgressSink, cancel: CancelToken | None) -> _Built:
        version = content_version(self._content_root)
        meta = self._meta(version)
        progress.phase("scan", None)
        executables = list(self._executables.scan())
        man_files = list(self._man.locate())
        _check_cancel(cancel)
        page_set = render_pages(
            man_files, self._renderer, progress, workers=self._workers, cancel=cancel
        )
        catalog = build_catalog(page_set.pages, page_set.aliases, executables)
        curated, tldr = self._load_content()
        _check_cancel(cancel)
        enrichment = enrich(
            catalog.entries,
            curated=curated,
            tldr=tldr,
            executables=executables,
            probe_factory=self._probe_factory,
            progress=progress,
            extractors=self._extractors,
        )
        _check_cancel(cancel)
        digest = self._write(new, enrichment.entries, meta, progress, cancel)
        skipped = page_set.skipped + catalog.skipped + enrichment.skipped
        return _Built(enrichment.entries, skipped, enrichment.curated, digest)

    def _meta(self, version: str) -> dict[str, str]:
        return {
            **self._fingerprint(version).meta(),
            "leva_version": self._leva_version,
            "content_version": version,
            "macos_version": self._system.macos_version,
            "macos_build": self._system.macos_build,
            "attribution": attribution_text(),
        }

    def _load_content(self) -> tuple[list[CuratedCommand], list[TldrPage]]:
        curated: list[CuratedCommand] = []
        tldr: list[TldrPage] = []
        for provider in self._providers:
            for record in provider.load():
                if isinstance(record, CuratedCommand):
                    curated.append(record)
                else:
                    tldr.append(record)
        return curated, tldr

    def _write(
        self,
        new: Path,
        entries: Sequence[CatalogEntry],
        meta: Mapping[str, str],
        progress: ProgressSink,
        cancel: CancelToken | None,
    ) -> str:
        progress.phase("write", len(entries))
        with IndexWriter(new) as writer:
            for entry in entries:
                _write_entry(writer, entry)
                progress.advance()
                _check_cancel(cancel)
            for key, value in meta.items():
                writer.set_meta(key, value)
            progress.phase("finalize", None)
            return writer.finalize(built_at=self._clock())


def _write_entry(writer: IndexWriter, entry: CatalogEntry) -> None:
    entry_id = writer.add_entry(
        NewEntry(
            entry.name,
            entry.section,
            entry.kind,
            entry.origin,
            entry.summary,
            entry.path,
            entry.has_man,
            entry.curated,
            entry.rank,
            entry.explain,
        )
    )
    for alias in entry.aliases:
        writer.add_alias(entry_id, alias)
    writer.add_sections(entry_id, entry.sections)
    writer.add_examples(entry_id, entry.examples)
    writer.add_subcommands(entry_id, entry.subcommands)
    writer.add_notes(entry_id, entry.notes)
    writer.add_related(entry_id, entry.related)
    writer.add_intents(entry_id, entry.intents)


def _check_cancel(cancel: CancelToken | None) -> None:
    if cancel is not None and cancel.is_set():
        raise IngestError(CANCELLED)
