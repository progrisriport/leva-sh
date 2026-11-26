"""Search latency on a synthetic 3000-entry index (NFR-2: p95 < 50 ms; CI bound 100 ms)."""

from __future__ import annotations

import itertools
import math
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

from leva.model import Kind, Origin, Section
from leva.repo import Repository
from leva.search import Searcher
from leva.store import IndexWriter, NewEntry, open_readonly

pytestmark = pytest.mark.perf

ENTRY_COUNT: Final = 3000
QUERY_COUNT: Final = 200
P95_BUDGET_SECONDS: Final = 0.100
RESULT_LIMIT: Final = 50
BUILT_AT: Final = datetime(2026, 1, 1, tzinfo=UTC)

SYLLABLES: Final = (
    "ba", "ch", "de", "gr", "ka", "lo", "mi", "nu",
    "pe", "ri", "so", "st", "tu", "va", "xe", "zo",
)  # fmt: skip
VERBS: Final = (
    "compress", "extract", "list", "rename", "search", "merge", "split", "sort",
    "count", "copy", "inspect", "monitor", "convert", "encrypt", "resize", "archive",
)  # fmt: skip
NOUNS: Final = (
    "folder", "archive", "process", "image", "stream", "table", "socket", "volume",
    "record", "pattern", "schedule", "package", "session", "bundle", "journal", "ticket",
)  # fmt: skip
WORDS: Final = (
    "reads", "writes", "prints", "filters", "walks", "reports", "joins", "trims",
    "tracks", "swaps", "mounts", "probes", "wraps", "formats", "queues", "signs",
    "values", "lines", "fields", "blocks", "tokens", "labels", "hashes", "ranges",
)  # fmt: skip

BUILTIN_EVERY: Final = 50
SECTION_8_EVERY: Final = 10
CURATED_EVERY: Final = 20
ALIAS_EVERY: Final = 7
EXE_ONLY_EVERY: Final = 25
INTENTS_PER_ENTRY: Final = 4
INTENT_STRIDE: Final = 37  # odd, so it permutes the 256 verb/noun pairs


def make_names() -> list[str]:
    """Return the first `ENTRY_COUNT` sorted names built from three syllables."""
    names = sorted("".join(parts) for parts in itertools.product(SYLLABLES, repeat=3))[:ENTRY_COUNT]
    assert len(set(names)) == ENTRY_COUNT
    return names


NAMES: Final = make_names()


def intent_phrase(index: int, slot: int) -> str:
    """Return the `slot`-th curated intent of entry `index`, e.g. ``compress a folder``.

    Consecutive (curated entry, slot) pairs walk all verb/noun pairs before any repeats.
    """
    pair = ((index // CURATED_EVERY) * INTENTS_PER_ENTRY + slot) * INTENT_STRIDE
    pair %= len(VERBS) * len(NOUNS)
    return f"{VERBS[pair % len(VERBS)]} a {NOUNS[pair // len(VERBS)]}"


def summary_text(index: int) -> str:
    """Return a 5-9 word summary for entry `index`."""
    count = 5 + index % 5
    return " ".join(WORDS[(index * 3 + k * 5) % len(WORDS)] for k in range(count))


def description_text(index: int) -> str:
    """Return a 150-300 word description for entry `index`."""
    count = 150 + (index * 7) % 151
    return " ".join(WORDS[(index * 11 + k * 13 + k // 7) % len(WORDS)] for k in range(count))


def is_builtin(index: int) -> bool:
    """Tell whether entry `index` is a shell builtin."""
    return index % BUILTIN_EVERY == 0


def is_exe_only(index: int) -> bool:
    """Tell whether entry `index` has no man page (never a builtin or curated entry)."""
    return index % EXE_ONLY_EVERY == EXE_ONLY_EVERY - 1


def is_curated(index: int) -> bool:
    """Tell whether entry `index` carries curated content."""
    return index % CURATED_EVERY == 0


def build_entry(index: int) -> NewEntry:
    """Return the `NewEntry` for position `index` in `NAMES`."""
    name = NAMES[index]
    has_man = not is_exe_only(index)
    builtin = is_builtin(index)
    section = None if builtin else ("8" if index % SECTION_8_EVERY == 0 else "1")
    return NewEntry(
        name=name,
        section=section,
        kind=Kind.BUILTIN if builtin else Kind.EXECUTABLE,
        origin=Origin.ZSH if builtin else Origin.MACOS,
        summary=summary_text(index) if has_man else "",
        path=None if builtin else f"/usr/bin/{name}",
        has_man=has_man,
        curated=is_curated(index),
    )


def write_index(path: Path) -> None:
    """Write the finalized synthetic index to `path`."""
    with IndexWriter(path) as writer:
        for index, name in enumerate(NAMES):
            entry_id = writer.add_entry(build_entry(index))
            if index % ALIAS_EVERY == 0:
                writer.add_alias(entry_id, f"{name}x")
            if not is_exe_only(index):
                writer.add_sections(
                    entry_id,
                    [
                        Section("NAME", f"{name} - {summary_text(index)}", 0),
                        Section("SYNOPSIS", f"{name} [options] file", 1),
                        Section("DESCRIPTION", description_text(index), 2),
                    ],
                )
            if is_curated(index):
                writer.add_intents(
                    entry_id, [intent_phrase(index, slot) for slot in range(INTENTS_PER_ENTRY)]
                )
        writer.finalize(built_at=BUILT_AT)


def swap_adjacent(name: str, position: int) -> str:
    """Return `name` with the characters at `position` and `position + 1` swapped."""
    chars = list(name)
    chars[position], chars[position + 1] = chars[position + 1], chars[position]
    return "".join(chars)


def exact_name_queries() -> list[str]:
    """Return 40 existing names spread over the whole index."""
    return [NAMES[(i * 75 + 3) % ENTRY_COUNT] for i in range(40)]


def prefix_queries() -> list[str]:
    """Return 40 prefixes of 1-4 characters (the per-keystroke case)."""
    return [NAMES[(i * 73 + 5) % ENTRY_COUNT][: 1 + i % 4] for i in range(40)]


def typo_queries() -> list[str]:
    """Return 30 names with two adjacent letters swapped."""
    return [swap_adjacent(NAMES[(i * 97 + 11) % ENTRY_COUNT], i % 5) for i in range(30)]


def intent_queries() -> list[str]:
    """Return 30 intent phrases: 15 exact and 15 partial ones without the article."""
    curated = [i for i in range(ENTRY_COUNT) if is_curated(i)]
    phrases = [
        intent_phrase(curated[(i * 9) % len(curated)], i % INTENTS_PER_ENTRY) for i in range(30)
    ]
    return [p if i % 2 == 0 else p.replace(" a ", " ") for i, p in enumerate(phrases)]


def word_queries() -> list[str]:
    """Return 40 queries of 1-3 summary or body words."""
    return [
        " ".join(WORDS[(i * 5 + k * 3 + i // len(WORDS)) % len(WORDS)] for k in range(1 + i % 3))
        for i in range(40)
    ]


def multi_word_name_queries() -> list[str]:
    """Return 10 names written with a space or a hyphen inside."""
    picked = [NAMES[(i * 211 + 17) % ENTRY_COUNT] for i in range(10)]
    return [name[:3] + (" " if i % 2 == 0 else "-") + name[3:] for i, name in enumerate(picked)]


def odd_queries() -> list[str]:
    """Return 10 hostile or degenerate inputs."""
    return [
        "",
        "   ",
        "\U0001f642\U0001f642",
        "!!!???",
        "a" * 200,
        "LS",
        "KALOMI",
        "';--",
        "\x00",
        "ZO ZO ZO",
    ]


def build_queries() -> list[str]:
    """Return the 200 benchmark queries, in a fixed order."""
    queries = [
        *exact_name_queries(),
        *prefix_queries(),
        *typo_queries(),
        *intent_queries(),
        *word_queries(),
        *multi_word_name_queries(),
        *odd_queries(),
    ]
    assert len(queries) == len(set(queries)) == QUERY_COUNT
    return queries


def percentile(sorted_values: list[float], fraction: float) -> float:
    """Return the nearest-rank percentile: the value at index ``ceil(fraction * n) - 1``."""
    return sorted_values[math.ceil(fraction * len(sorted_values)) - 1]


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Repository]:
    """A read-only repository over the module's synthetic index."""
    path = tmp_path_factory.mktemp("latency") / "index.db"
    write_index(path)
    repository = Repository(open_readonly(path))
    try:
        yield repository
    finally:
        repository.close()


def test_search_p95_under_budget(repo: Repository, request: pytest.FixtureRequest) -> None:
    searcher = Searcher(repo)
    started = time.perf_counter()
    searcher.search("warm")  # reads and caches names(), kept out of the sample
    warmup = time.perf_counter() - started
    durations: list[float] = []
    for query in build_queries():
        started = time.perf_counter()
        searcher.search(query, RESULT_LIMIT)
        durations.append(time.perf_counter() - started)
    durations.sort()
    p50, p95, worst = percentile(durations, 0.50), percentile(durations, 0.95), durations[-1]
    # What `record_property` does, minus its warning (an error here) under junit_family xunit2.
    request.node.user_properties += [
        ("entries", ENTRY_COUNT),
        ("warmup_ms", round(warmup * 1000, 2)),
        ("p50_ms", round(p50 * 1000, 2)),
        ("p95_ms", round(p95 * 1000, 2)),
        ("max_ms", round(worst * 1000, 2)),
    ]
    assert p95 < P95_BUDGET_SECONDS, (
        f"p50={p50 * 1000:.2f} ms p95={p95 * 1000:.2f} ms max={worst * 1000:.2f} ms "
        f"warm-up={warmup * 1000:.2f} ms over {len(durations)} queries"
    )


def test_synthetic_index_shape(repo: Repository) -> None:
    stats = repo.stats()
    indexes = range(ENTRY_COUNT)
    assert stats.entries == ENTRY_COUNT
    assert len(repo.names()) == ENTRY_COUNT
    assert stats.curated == sum(is_curated(i) for i in indexes) == 150
    assert stats.builtins == sum(is_builtin(i) for i in indexes) == 60
    assert stats.man_pages == sum(not is_exe_only(i) and not is_builtin(i) for i in indexes) == 2820
    assert repo.fts(WORDS[0], 10)
    assert repo.fts(intent_phrase(0, 0).split()[0], 10)


def test_queries_return_results_within_limit(repo: Repository) -> None:
    searcher = Searcher(repo)
    for query in build_queries():
        assert len(searcher.search(query, RESULT_LIMIT)) <= RESULT_LIMIT, repr(query)
    for name in exact_name_queries():
        results = searcher.search(name, RESULT_LIMIT)
        assert results, name
        assert results[0].name == name
    intents = {row.entry_id: row.intents for row in repo.names()}
    for phrase in intent_queries()[::2]:
        top = searcher.search(phrase, RESULT_LIMIT)[0]
        assert phrase in intents[top.entry_id], phrase
