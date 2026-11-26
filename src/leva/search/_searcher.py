"""Turn a user query into ranked, deduplicated results from the name list and the FTS index."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from leva.model import Kind, Origin
from leva.repo import NameRow, Repository
from leva.search._ranking import (
    ALIAS_SUB,
    DEFAULT_WEIGHTS,
    FUZZY_ALIAS_FACTOR,
    FUZZY_NAME_FACTOR,
    NAME_SUB,
    Weights,
    content_words,
    fts_sub,
    fuzzy_applies,
    fuzzy_hits,
    intent_match,
    name_key,
    nearest,
    normalise,
    words,
)

MatchReason = Literal["name", "alias", "intent", "summary", "body"]

_MIN_FTS_LIMIT = 100
_FTS_OVERSAMPLING = 4


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One ranked search result.

    Attributes:
        entry_id: Index row id; several results can share a name (``echo``), so open by id.
        name: Command name.
        section: Man section, or ``None``.
        kind: What the entry is.
        origin: Where it comes from.
        summary: One-line description, ``""`` when absent.
        score: Ranking score, higher is better.
        why: What matched: name, alias, intent, summary or body.
        via: The matched intent text, set exactly when ``why`` is ``"intent"`` (D-029).

    Raises:
        ValueError: If ``via`` is set while ``why`` is not ``"intent"``, or missing while it is.
    """

    entry_id: int
    name: str
    section: str | None
    kind: Kind
    origin: Origin
    summary: str
    score: float
    why: MatchReason
    via: str | None = None

    def __post_init__(self) -> None:
        if (self.why == "intent") != (self.via is not None):
            raise ValueError(
                f"via must be set exactly when why is 'intent': {self.why!r}, {self.via!r}"
            )


@dataclass(frozen=True, slots=True)
class _Match:
    base: float
    sub: float
    why: MatchReason
    via: str | None = None

    @property
    def total(self) -> float:
        return self.base + self.sub


@dataclass(frozen=True, slots=True)
class _Entry:
    row: NameRow
    position: int
    name_key: str
    alias_keys: tuple[str, ...]
    intent_words: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class _Names:
    entries: tuple[_Entry, ...]
    by_id: dict[int, _Entry]
    with_intents: tuple[_Entry, ...]
    name_keys: list[str]
    alias_keys: list[str]
    alias_owners: list[int]  # position of the entry owning each item of alias_keys


def _build_names(rows: list[NameRow]) -> _Names:
    entries = tuple(
        _Entry(
            row=row,
            position=position,
            name_key=row.name.casefold(),
            alias_keys=tuple(alias.casefold() for alias in row.aliases),
            intent_words=tuple(words(intent) for intent in row.intents),
        )
        for position, row in enumerate(rows)
    )
    return _Names(
        entries=entries,
        by_id={entry.row.entry_id: entry for entry in entries},
        with_intents=tuple(entry for entry in entries if entry.intent_words),
        name_keys=[entry.name_key for entry in entries],
        alias_keys=[alias for entry in entries for alias in entry.alias_keys],
        alias_owners=[entry.position for entry in entries for _ in entry.alias_keys],
    )


def _check_limit(limit: int) -> None:
    if limit < 1:
        raise ValueError(f"limit must be >= 1: {limit!r}")


def _offer(found: dict[int, _Match], entry_id: int, match: _Match) -> None:
    """Keep the best-scoring match per entry; the first one wins a tie."""
    current = found.get(entry_id)
    if current is None or match.total > current.total:
        found[entry_id] = match


def _merge(found: dict[int, _Match], other: dict[int, _Match]) -> None:
    for entry_id, match in other.items():
        _offer(found, entry_id, match)


class Searcher:
    """Rank entries for a query: exact > prefix > fuzzy > intent > summary > partial > body.

    The name list is loaded lazily on the first call and cached, because the index is read-only.

    Args:
        repo: Open repository over the index.
        weights: Tier bases and bonuses.
    """

    def __init__(self, repo: Repository, *, weights: Weights = DEFAULT_WEIGHTS) -> None:
        self._repo = repo
        self._weights = weights
        self._names: _Names | None = None

    def search(self, query: str, limit: int = 50) -> list[SearchResult]:
        """Return the best results for ``query``, best first.

        Case and runs of whitespace do not matter. Ties are broken by name, then by the position
        in the repository's name list (which encodes the D-005 rank).

        Args:
            query: Raw user input.
            limit: Maximum number of results, at least 1.

        Returns:
            At most ``limit`` results without repeated ``entry_id``; ``[]`` for a blank query.

        Raises:
            ValueError: If ``limit`` is below 1.
            IndexUnavailableError: If the index cannot be read.
        """
        _check_limit(limit)
        text = normalise(query)
        if not text:
            return []
        index = self._index()
        query_words = words(text)
        query_content = content_words(query_words)
        found: dict[int, _Match] = {}
        _merge(found, self._by_name(index, name_key(text)))
        _merge(found, self._by_fuzzy(index, text))
        _merge(found, self._by_intent(index, query_words, query_content))
        _merge(found, self._by_fts(index, text, query_content, limit))
        return self._rank(index, found, limit)

    def nearest_names(self, query: str, limit: int = 3) -> list[str]:
        """Return the names and aliases most similar to ``query``, with no similarity threshold.

        Args:
            query: Raw user input.
            limit: Maximum number of strings, at least 1.

        Returns:
            Distinct names or aliases as stored, best ``WRatio`` first, ties by string; ``[]``
            for a blank query.

        Raises:
            ValueError: If ``limit`` is below 1.
            IndexUnavailableError: If the index cannot be read.
        """
        _check_limit(limit)
        text = normalise(query)
        if not text:
            return []
        index = self._index()
        shown = [entry.row.name for entry in index.entries]
        shown += [alias for entry in index.entries for alias in entry.row.aliases]
        scores = nearest(text.casefold(), index.name_keys + index.alias_keys)
        best: dict[str, float] = {}
        for string, score in zip(shown, scores, strict=True):
            best[string] = max(best.get(string, 0.0), score)
        ordered = sorted(best.items(), key=lambda item: (-item[1], item[0]))
        return [string for string, _ in ordered[:limit]]

    def _index(self) -> _Names:
        if self._names is None:
            self._names = _build_names(self._repo.names())
        return self._names

    def _by_name(self, index: _Names, key: str) -> dict[int, _Match]:
        found: dict[int, _Match] = {}
        for entry in index.entries:
            candidates = [self._text_match(key, entry.name_key, NAME_SUB, "name")]
            candidates += [
                self._text_match(key, alias, ALIAS_SUB, "alias") for alias in entry.alias_keys
            ]
            for match in candidates:
                if match is not None:
                    _offer(found, entry.row.entry_id, match)
        return found

    def _text_match(
        self, key: str, candidate: str, factor: float, why: MatchReason
    ) -> _Match | None:
        if key == candidate:
            return _Match(self._weights.exact, factor, why)
        if candidate.startswith(key):
            return _Match(self._weights.prefix, factor * len(key) / len(candidate), why)
        return None

    def _by_fuzzy(self, index: _Names, text: str) -> dict[int, _Match]:
        if not fuzzy_applies(text):
            return {}
        key = text.casefold()
        found: dict[int, _Match] = {}
        for position, similarity in fuzzy_hits(key, index.name_keys).items():
            match = _Match(self._weights.fuzzy, FUZZY_NAME_FACTOR * similarity, "name")
            _offer(found, index.entries[position].row.entry_id, match)
        for item, similarity in fuzzy_hits(key, index.alias_keys).items():
            match = _Match(self._weights.fuzzy, FUZZY_ALIAS_FACTOR * similarity, "alias")
            _offer(found, index.entries[index.alias_owners[item]].row.entry_id, match)
        return found

    def _by_intent(
        self, index: _Names, query_words: tuple[str, ...], query_content: tuple[str, ...]
    ) -> dict[int, _Match]:
        found: dict[int, _Match] = {}
        for entry in index.with_intents:
            for position, intent_words in enumerate(entry.intent_words):
                rated = intent_match(query_words, query_content, intent_words, position)
                if rated is None:
                    continue
                base = self._weights.intent if rated.tier == "intent" else self._weights.partial
                via = entry.row.intents[position]
                _offer(found, entry.row.entry_id, _Match(base, rated.sub, "intent", via))
        return found

    def _by_fts(
        self, index: _Names, text: str, query_content: tuple[str, ...], limit: int
    ) -> dict[int, _Match]:
        """Full-text hits; stopwords neither restrict the AND query nor make a summary match.

        A query made only of stopwords and punctuation is passed through unchanged.
        """
        fts_text = " ".join(query_content) or text
        summary_words = set(query_content) or set(words(text))
        found: dict[int, _Match] = {}
        for hit in self._repo.fts(fts_text, limit=max(_FTS_OVERSAMPLING * limit, _MIN_FTS_LIMIT)):
            entry = index.by_id.get(hit.entry_id)
            if entry is None:
                continue
            in_summary = not summary_words.isdisjoint(words(entry.row.summary))
            if in_summary:
                match = _Match(self._weights.summary, fts_sub(hit.score), "summary")
            else:
                match = _Match(self._weights.body, fts_sub(hit.score), "body")
            found[hit.entry_id] = match
        return found

    def _bonus(self, row: NameRow) -> float:
        curated = self._weights.curated_bonus if row.curated else 0.0
        builtin = self._weights.builtin_bonus if row.kind is Kind.BUILTIN else 0.0
        return curated + builtin

    def _rank(self, index: _Names, found: dict[int, _Match], limit: int) -> list[SearchResult]:
        scored = [
            (match.total + self._bonus(index.by_id[entry_id].row), index.by_id[entry_id], match)
            for entry_id, match in found.items()
        ]
        scored.sort(key=lambda item: (-item[0], item[1].row.name, item[1].position))
        return [
            SearchResult(
                entry_id=entry.row.entry_id,
                name=entry.row.name,
                section=entry.row.section,
                kind=entry.row.kind,
                origin=entry.row.origin,
                summary=entry.row.summary,
                score=score,
                why=match.why,
                via=match.via,
            )
            for score, entry, match in scored[:limit]
        ]
