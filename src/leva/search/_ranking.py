"""Pure ranking helpers: weights, tokenisation, intent strength and sub-score formulas."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final, Literal

from rapidfuzz import fuzz, process
from rapidfuzz.distance import OSA

STOPWORDS: Final = frozenset(
    {
        "a",
        "an",
        "the",
        "in",
        "on",
        "of",
        "to",
        "for",
        "and",
        "or",
        "with",
        "by",
        "from",
        "into",
        "my",
        "me",
        "i",
        "is",
        "it",
        "this",
        "that",
        "how",
        "do",
        "what",
    }
)

NAME_SUB: Final = 800.0  # best sub-score of any tier; a name match uses it as its factor
ALIAS_SUB: Final = 700.0  # factor of an alias match
FUZZY_NAME_FACTOR: Final = 8.0  # fuzzy sub-score = factor * similarity (<= 100)
FUZZY_ALIAS_FACTOR: Final = 7.0
FUZZY_MIN: Final = 80.0  # minimum similarity of a fuzzy match
FUZZY_MIN_LENGTH: Final = 3
FUZZY_MAX_LENGTH: Final = 64
PHRASE_SUB: Final = 800.0
ALL_WORDS_SUB: Final = 400.0
ORD_STEP: Final = 10.0  # sub-score lost per position of an intent (phrase and all-words)
PARTIAL_ORD_STEP: Final = 5.0
MAX_ORD: Final = 30
FTS_SCALE: Final = 10.0  # bm25 value at which the FTS sub-score reaches half of its maximum

_MIN_TIER_GAP: Final = 1000.0
_MAX_BONUS_SUM: Final = 50.0
_WORD: Final = re.compile(r"\w+")

IntentTier = Literal["intent", "partial"]


@dataclass(frozen=True, slots=True)
class Weights:
    """Tier bases and bonuses of the ranking.

    A result's score is its tier base plus a sub-score below 900 plus a bonus of at most 50, so a
    tier never crosses into the next one.

    Attributes:
        exact: Name or alias equals the query.
        prefix: Name or alias starts with the query.
        fuzzy: Similar name or alias (single-token queries only).
        intent: Exact intent phrase or all query words in an intent.
        summary: Full-text hit with a query word in the summary.
        partial: Some, not all, query words in an intent.
        body: Any other full-text hit.
        curated_bonus: Added to entries with curated content.
        builtin_bonus: Added to shell builtins.

    Raises:
        ValueError: If the tiers are not strictly decreasing by at least 1000 each, or a bonus is
            negative, or the bonuses sum to more than 50.
    """

    exact: float = 7000.0
    prefix: float = 6000.0
    fuzzy: float = 5000.0
    intent: float = 4000.0
    summary: float = 3000.0
    partial: float = 2000.0
    body: float = 1000.0
    curated_bonus: float = 20.0
    builtin_bonus: float = 10.0

    def __post_init__(self) -> None:
        tiers = (
            self.exact,
            self.prefix,
            self.fuzzy,
            self.intent,
            self.summary,
            self.partial,
            self.body,
        )
        if not all(upper - lower >= _MIN_TIER_GAP for upper, lower in pairwise(tiers)):
            raise ValueError(f"tiers must decrease by at least {_MIN_TIER_GAP:g}: {tiers!r}")
        if not self.body >= _MIN_TIER_GAP:
            raise ValueError(f"body must be at least {_MIN_TIER_GAP:g}: {self.body!r}")
        bonuses = (self.curated_bonus, self.builtin_bonus)
        if not (min(bonuses) >= 0 and sum(bonuses) <= _MAX_BONUS_SUM):
            raise ValueError(f"bonuses must be >= 0 and sum to <= {_MAX_BONUS_SUM:g}: {bonuses!r}")


DEFAULT_WEIGHTS: Final = Weights()


@dataclass(frozen=True, slots=True)
class IntentMatch:
    """How strongly a query matches one intent.

    Attributes:
        tier: ``"intent"`` for a phrase or all-words match, ``"partial"`` for some words.
        sub: Sub-score in ``[0, 900)``.
    """

    tier: IntentTier
    sub: float


def normalise(query: str) -> str:
    """Collapse runs of whitespace and strip the query."""
    return " ".join(query.split())


def name_key(text: str) -> str:
    """Return the casefolded name a normalised query stands for (``git co`` is ``git-co``)."""
    return text.replace(" ", "-").casefold()


def words(text: str) -> tuple[str, ...]:
    """Return the casefolded alphanumeric words of ``text`` (punctuation is dropped)."""
    return tuple(_WORD.findall(text.casefold()))


def content_words(query_words: Sequence[str]) -> tuple[str, ...]:
    """Return the query words without stopwords, deduplicated, in order."""
    return tuple(dict.fromkeys(word for word in query_words if word not in STOPWORDS))


def intent_match(
    query_words: tuple[str, ...],
    query_content: tuple[str, ...],
    intent_words: tuple[str, ...],
    position: int,
) -> IntentMatch | None:
    """Rate one intent against the query: exact phrase > all words > some words.

    Args:
        query_words: Words of the query, stopwords included.
        query_content: Words of the query without stopwords.
        intent_words: Words of the intent.
        position: ``ord`` of the intent in its entry; an earlier intent scores higher.

    Returns:
        The match, or ``None`` when no content word occurs in the intent.
    """
    if not query_words:
        return None
    rank = min(position, MAX_ORD)
    if query_words == intent_words:
        return IntentMatch("intent", PHRASE_SUB - ORD_STEP * rank)
    known = set(intent_words)
    matched = sum(1 for word in query_content if word in known)
    if matched == 0:
        return None
    if matched == len(query_content):
        return IntentMatch("intent", ALL_WORDS_SUB - ORD_STEP * rank)
    fraction = matched / len(query_content)
    return IntentMatch("partial", max(0.0, NAME_SUB * fraction - PARTIAL_ORD_STEP * rank))


def fuzzy_applies(text: str) -> bool:
    """Whether fuzzy name matching runs: one token of 3 to 64 characters."""
    return " " not in text and FUZZY_MIN_LENGTH <= len(text) <= FUZZY_MAX_LENGTH


def fuzzy_hits(key: str, choices: list[str]) -> dict[int, float]:
    """Return similarity by index for every choice similar to ``key``.

    A choice matches with ``rapidfuzz.fuzz.WRatio >= 80`` or an optimal-string-alignment distance
    of 1 (a one-letter typo or swap), which counts as similarity 80.

    Args:
        key: Casefolded query.
        choices: Casefolded names or aliases.
    """
    hits = {
        index: score
        for _, score, index in process.extract(
            key,
            choices,
            scorer=fuzz.WRatio,
            processor=None,
            score_cutoff=FUZZY_MIN,
            limit=None,
        )
    }
    for _, _, index in process.extract(
        key, choices, scorer=OSA.distance, processor=None, score_cutoff=1, limit=None
    ):
        hits[index] = max(hits.get(index, 0.0), FUZZY_MIN)
    return hits


def nearest(text: str, choices: list[str]) -> list[float]:
    """Return the WRatio similarity of ``text`` to every choice, in choice order."""
    scores = [0.0] * len(choices)
    for _, score, index in process.extract(
        text, choices, scorer=fuzz.WRatio, processor=None, limit=None
    ):
        scores[index] = score
    return scores


def fts_sub(score: float) -> float:
    """Map a full-text score (``-bm25``, may be negative) to a sub-score in ``[0, 800)``."""
    clamped = max(score, 0.0)
    return NAME_SUB * clamped / (clamped + FTS_SCALE)
