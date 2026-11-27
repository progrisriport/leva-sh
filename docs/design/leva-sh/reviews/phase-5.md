# Phase 5 review

- Date: 2026-11-27 · Scope: T-5.1, T-5.2, T-5.3 · Reviewer: ralph loop (executor)

## Scope

`leva.search` (`_ranking`, `_searcher`), `leva.library` (`_card`, `_history`, `_library`), the latency benchmark
(`tests/integration/test_search_latency.py`), `tests/unit/test_{search,library}.py`, `tests/fixtures/index/gold_mini.json`,
DECISIONS D-050 and D-051, PLAN T-5.1..T-5.3 and the R10 lines in T-8.4, T-8.5, T-8.7. Checked against PLAN §4 RC, DITS §11
and §12, D-010, D-011, D-028 (UX.md §3.1–3.2), D-029, D-031, D-049, TEST-STRATEGY (`search` and `library` rows, §3, §5).

## Checked items

Result after the changes: 1687 passed (non-live), search 100.0%, library 100.0%, overall 99.9% branch coverage, 3
contracts kept. Baseline before changes (HEAD `f720a7d`, as recorded by the T-5.3 commit): `make check` green, 1646
passed, search 100.0% and library 100.0% branch coverage; the executor did not re-run it before the F-1 change.

1. Public API matches DITS + DECISIONS: ok. `SearchResult` (adds `section`, `kind`, `origin`, `via`), `nearest_names`, the
   `partial` tier, `Card.summary`, `card`, `open_result`, `trail`, `nearest_names`, `close` and `HISTORY_LIMIT` are all
   recorded in D-050/D-051. The PLAN T-5.1 lines that D-050 refines were not stated in D-050: F-4.
2. Docstrings: ok. Every module states one responsibility; public items carry Args/Returns/Raises. The `Library` class
   docstring said only `IndexUnavailableError` is raised, but `search` and `nearest_names` also raise `ValueError` for
   `limit < 1`: F-2.
3. Only `LevaError` crosses the boundary: ok. Neither package catches anything: `IndexUnavailableError` comes from the
   repository, `ValueError` is a programmer error (`limit < 1`, `Weights`, `Card`, `SearchResult`). Kept on purpose: an
   integer argument above 64 bits (`limit`, `entry_id`) makes `sqlite3` raise `OverflowError` (D-049); both come from
   code, not user text.
4. No global mutable state; env, clock and paths injected: ok. `STOPWORDS` is a frozenset, `DEFAULT_WEIGHTS` a frozen
   dataclass, the name cache lives in the `Searcher` instance, the history in the `Library` instance. No `os`, `environ`,
   clock, `print`, `sqlite3` or `subprocess` in either package.
5. Small functions, no duplication, naming: ok (C901 passes). The `Searcher` candidate steps are one method each
   (`_by_name`, `_by_fuzzy`, `_by_intent`, `_by_fts`) merged by `_offer`.
6. Tests: meaningful and deterministic. Search: gold mini, typos (`gerp` → `grep`), blank query, case and spaces, stable
   order, no duplicate ids, limit, every tier and `why`, fuzzy rules, stopwords, `nearest_names`, stub repositories for the
   FTS paths, Hypothesis invariants. Library: open by name/alias/`git commit`, curated → tldr order, merge, history,
   synthesized card, closed repository. No sleeps. Gaps: F-3.
7. Coverage: ok. search 100.0%, library 100.0%, overall 99.9% (gates 90% / 85% / 85%).
8. No `Any` in public APIs, no `cast`, no `type: ignore`: ok.
9. Layers and arch: ok. `search` imports `model`, `repo` and `rapidfuzz`; `library` imports `model`, `placeholders`, `repo`,
   `search`, only from package roots; `lint-imports`: 3 kept, 0 broken. 3.11 compatibility read: no `type` statement, no
   PEP 695, no `itertools.batched`; `itertools.pairwise` exists since 3.10.
10. Docs consistent: ok after F-2 and F-4. PLAN Files lines list the files that exist (`_ranking.py`, `_searcher.py`,
    `_card.py`, `_history.py`, `_library.py`); the R10 lines of T-8.4, T-8.5 and T-8.7 match the code (`SearchResult` fields
    and `via`, `card`/`open_result`/`trail`/`back`/`forward`, breadcrumb and `Card.summary`, `open_subcommand` and the
    synthesized card). `CLAUDE.md` is untouched.

Risk spots of the brief:

- **Ranking vs D-029**: the sub-scores are `< 900` (name/alias 800/700, prefix below that, fuzzy at most `8 * 100`, intent
  phrase `800 - 10 * min(ord, 30)` ≥ 500, all words `400 - 10 * min(ord, 30)` ≤ 400, partial `< 800`, FTS `< 800`) and the
  bonuses sum to at most 50, so a tier never crosses into the next one, and phrase (≥ 500) stays above all words (≤ 400)
  with a gap larger than the largest bonus. Both facts are now pinned by tests (F-3). Adversarial `Weights`: `exact=inf`
  and `exact=1e18` were accepted: F-1. The partial tier below `summary` is recorded in D-050 as a refinement of the PLAN
  and DITS tier list (also noted in the amendment, F-4).
- **Fuzzy rules**: only one token of 3 to 64 characters; 1 and 2 characters (`l`, `ls`, `g`, `gi`) get exact and prefix
  only; the OSA distance-1 rule counts as similarity 80; `nearest_names` has no threshold and is not limited by length
  (a 10 000-character query is in the odd-input test).
- **Totality** of `Searcher.search`, `nearest_names` and `Library.open` over NUL, lone surrogates, emoji, 10 000
  characters, only punctuation, only stopwords: the search side was tested by parametrized cases; Hypothesis properties
  over a hostile alphabet and explicit hostile inputs were missing for `Library.open` and for the search/`nearest_names`
  pair: F-3. All pass without a code change.
- **Determinism**: ties are broken by `(name, names() position)`, a total order. The only `set` objects (`known`,
  `summary_words`) are used for membership, never iterated into the output; `dict` insertion order is deterministic;
  `nearest_names` sorts by `(-score, string)`. Two Searchers agree (test).
- **Lazy loading**: `Searcher.__init__` does no I/O (`test_constructing_a_searcher_does_no_io`). The cache cannot go stale in one
  `Library`: the index is read-only and a rebuild opens a new Library (T-8.9/T-9.2, R10 line in PROGRESS).
- **Library history**: `push` truncates the forward part, then applies the limit of 50; `back`/`forward` return `None` and
  do not move at the ends; `open_result` clears only for a known id; `card` never records; `open` pushes once on the
  subcommand path (the helper `_resolve_subcommand` does not record); the synthesized card has the parent `entry`,
  `explain ""`, one DESCRIPTION section or none, examples filtered on a word boundary (`git statusx` excluded);
  `example_key` collapses placeholders to `{}`; curated wins over tldr. All pinned by existing tests.
- **Benchmark**: finalized index (`finalize` fills FTS), the warm-up call is outside the sample, p95 is nearest-rank
  (`ceil(0.95 * 200) - 1`), the budget is 100 ms (NFR-2 target 50 ms), data is deterministic (no RNG, no clock), the
  repository is closed by the module fixture, the file takes about 1 s. Numbers are in PROGRESS (T-5.2): p95 2.8–3.1 ms.
- **Gold mini**: 30/30 with the expect in the top three, measured on the fixture index in this review; no query was
  swapped (the test asserts ≥ 27, the spec).

## Findings

- **F-1** (medium) `search/_ranking.py`: `Weights(exact=inf)` passed validation (`inf - 6000 >= 1000`), and
  `Weights(exact=1e18, prefix=1e18 - 1e4)` too: above about 1e15 the float spacing exceeds the 1-point resolution of the
  sub-scores, so the tiers collapse into ties and the "tier never crossed" guarantee of D-029 no longer holds for the
  values the validation allowed.
- **F-2** (low, docs) `library/_library.py`: the class docstring said every method raises only `IndexUnavailableError`,
  contradicting `search`/`nearest_names` (`ValueError` for `limit < 1`) and D-051.
- **F-3** (low, test gap) Missing: the largest allowed bonuses never lift a result into a better tier (end to end over
  six queries and four bonus splits); phrase > all words > partial over every `ord` incl. past `MAX_ORD`; Hypothesis
  totality of `Library.open`; Hypothesis totality of `search`/`nearest_names` over a hostile alphabet incl. surrogates
  and NUL; explicit hostile names (10 000 characters, 2 500 repeated words, NUL, lone surrogate, punctuation) for
  `Library.open`; `Weights` with `inf`, a near-1e18 spread and a `nan` bonus.
- **F-4** (low, docs) D-050 said it refined DITS §11 but not the PLAN T-5.1 lines "Strict tiers: exact > prefix > fuzzy >
  intent > summary > body" and "ties broken by (name, section, origin)".

Kept on purpose:

- `search(limit=10**30)` raises `OverflowError` from `sqlite3` (the FTS limit is `4 * limit`); the UI passes constants
  (D-049: integer arguments are not guarded beyond `limit >= 1`).
- Fuzzy matching also finds distance-1 neighbours of 3-letter queries (`cat` finds `cut`, `car`): they rank in the fuzzy
  tier, below an exact name or prefix, as D-050 states.
- `Library.open` is exact and case-sensitive and does not strip flags (`ls -la`): D-012 resolution belongs to the
  TUI/search side (PROGRESS warnings of T-5.1 and T-5.3).

## Fixes

- **F-1** `_MAX_TIER = 1e9` and `Weights.__post_init__` raises `ValueError` unless `exact <= 1e9` (rejects `inf`; `nan`
  already fails the gap test). Tests: `test_invalid_weights_are_rejected` gained `exact=inf`, `exact=1e18` with a 1e4
  gap, and a `nan` bonus. D-050 amendment. The defaults are unchanged.
- **F-2** Docstring now says `IndexUnavailableError` for a database problem and `ValueError` for `limit < 1` on `search`
  and `nearest_names`.
- **F-3** `test_the_largest_bonuses_never_lift_a_result_into_a_better_tier`,
  `test_intent_sub_scores_keep_phrase_above_all_words_above_partial`,
  `test_search_and_nearest_names_are_total_over_hostile_text` (Hypothesis, module-scoped searcher),
  `test_open_is_total_over_hostile_text` (Hypothesis, module-scoped library; no function-scoped fixture inside `@given`),
  `test_open_returns_none_for_hostile_text_without_touching_history`. They pass on the existing ranking and library code:
  they pin behaviour that was only implied.
- **F-4** D-050 amendment names both PLAN T-5.1 lines it refines.

Amendments: D-050 (F-1, F-4).

R10 edits: none. The facts that Phase 6 ingest and Phase 8/9 rely on were already recorded in the T-5.x PROGRESS entries
and in the R10 lines of T-8.4, T-8.5 and T-8.7, and each matches the code; no decision of this review changes them.

## Commands run

- `uv run pytest tests/unit/test_search.py tests/unit/test_library.py -q` → 177 passed (partial work of this review in
  place), then 65 passed in `test_library.py` after the explicit hostile test.
- `uv run ruff check .` flagged one E501 in the new Hypothesis alphabet; `uv run ruff format .` fixed it; ruff check, ruff
  format, `uv run mypy` (58 source files), `uv run lint-imports` (3 kept) → green.
- `uv run pytest --cov --cov-report=json -q` + `uv run python tools/coverage_gate.py coverage.json` → 1687 passed,
  search 100.0%, library 100.0%, overall 99.9%, gate passed. One run showed a failure of
  `tests/unit/test_sources_probe.py::test_timeout_kills_process_group_and_removes_temp_dir` under load; the file passed
  alone (31 passed) and in the first full run. It is a timing test of Phase 2, outside this scope: left for the loop
  reviewer to watch (candidate for `quarantine` if it repeats).
- Gold mini measured through the fixture index: 30 queries, 0 misses in the top three.
- `make check` itself could not be run by the executor (the permission mode denied it); its steps were run one by one as
  listed above. The loop reviewer ran `make check`: green, 1687 passed, 11 deselected, coverage gate passed
  (`test_sources_probe.py` passed in that run).

## Not run

- `make py311` (not allowed in the loop): 3.11 compatibility checked by reading the code (see item 9).
- `make live`, the real-index gold set (T-10.18) and a re-measurement of the benchmark (numbers in PROGRESS T-5.2).

## Open items

None.
