# Phase 4 review

- Date: 2026-11-25 · Scope: T-4.1, T-4.2, T-4.3, T-4.4 · Reviewer: ralph loop (executor)

## Scope

`leva.store` (`_schema`, `_writer`, `_finalize`, `_open`, `migrations/0001_init.sql`), `leva.repo` (`_rows`, `_fts`,
`_repository`), the fixture index factory (`tests/support/index_factory.py`, `tests/fixtures/index/entries.json`),
`tests/unit/test_{store_writer,index_factory,repo,repo_fts}.py`, `tests/integration/test_store_finalize.py`, DECISIONS
D-047..D-049, PLAN T-4.1..T-4.4. Checked against PLAN §4 RC, DITS §9 and §10, ADR-0003, the S-3 findings, D-005, D-006,
D-029, D-030, D-032, D-033, TEST-STRATEGY (`store` and `repo` rows, §3, §4, §5).

## Checked items

Baseline before changes: `make check` green, 1468 passed, store 99.3% and repo 100.0% branch coverage, overall 99.9%,
3 contracts kept.

1. Public API matches DITS + DECISIONS: ok. Deviations from DITS §9/§10 are recorded in D-047..D-049 (`NewEntry`,
   `add_intents`, `finalize(*, built_at) -> str`, `entry.rank`, `example.danger`, `description` column, `close`,
   `get_entry_by_id`, `explain`, row types). The DITS schema sketch (`UNIQUE(name, section, origin)`) became the unique
   index `entry_key` on `IFNULL(section, '')` (D-047), because SQL `UNIQUE` ignores NULL sections.
2. Docstrings: ok. Every module states one responsibility; public items carry Args/Returns/Raises. `IndexWriter` states
   the "each list method once per entry" precondition.
3. Only `LevaError` crosses the boundary: finding F-1 and F-2 (fixed). Wrapped with `from exc`: every `sqlite3.Error`
   in the writer (`IngestError`), in `open_readonly` and in `Repository` (`IndexUnavailableError`), `UnicodeEncodeError`
   in writes, `ValueError` of the model in the row converters (`index corrupt: ...`). `ValueError` remains for
   programmer errors only (`NewEntry`, state errors, `limit < 1`, naive `built_at`).
4. No global mutable state; env, clock and paths are injected (`finalize(built_at=...)`, `IndexWriter(path)`); no
   `os`, `environ` or `datetime.now` in either package: ok.
5. Small functions, naming: ok (C901 passes). SQL strings are module constants;
   the digest query list and the writer's insert statements are not duplicated. The `rank`/`explain` extras of
   `NewEntry` are the only fields with defaults.
6. Tests: meaningful and deterministic. Store: rollback on exception (also after finalize), failed commit, failed DDL,
   unique constraints (NULL section included), foreign keys per child method, finalize meta, FTS per column, bm25 order,
   integrity check, finalize state errors, `open_readonly` for missing/directory/garbage/unreadable/other version/special
   characters/relative path/read-only connection. Repo: queries over the fixture, D-005 order of `get_entry`, FTS
   sanitisation with 30 hostile strings and a Hypothesis property, corrupt-row conversion errors, closed connection.
   No sleeps, `chmod` restored in `finally`, every connection closed. TEST-STRATEGY §4 lists `test_store_repo_roundtrip.py`:
   it did not exist; added (F-5).
7. Coverage: ok. store 99.4% (only the defensive `lastrowid is None` branch), repo 100.0%, overall 99.9% (gates 90%/85%).
8. No `Any` in public APIs. `cast` appears three times in `repo/_rows.py` for the `Literal` columns of `Example` and
   `Note`; each is justified (the model validates in `__post_init__`, so a bad stored value is `index corrupt`). No
   TODO/FIXME.
9. Layers and arch: ok. `repo` (layer 5) does not import `leva.store` (layer 4; only a docstring mentions it); both
   import only `model` and stdlib; 3 contracts kept.
10. Docs consistent: ok after the D-047/D-049 amendments and the R10 edits below.

Risk spots of the brief:

- **Transaction**: `__enter__` connects with `isolation_level=None`, so no implicit transaction exists when
  `executescript("BEGIN;...")` runs; Python 3.11's "executescript commits a pending transaction first" cannot apply
  (no pending one). DDL, `PRAGMA user_version` and every write share that transaction; a rollback undoes the DDL, so
  `user_version` stays 0 (`test_open_readonly_rejects_other_schema_version[0]`, `test_a_rolled_back_build_is_not_readable`).
  A failing commit and a failing DDL close the connection (`finally` / `except` branch). Leak in `__enter__` when the
  migration files cannot be read: F-3.
- **`open_readonly`**: `Path.as_uri()` on `absolute()` is correct for `#`, `%` and spaces (test), `PRAGMA user_version`
  runs before returning, the connection is closed on every failure path. `Path.is_file()` raised `PermissionError`
  for an unsearchable parent directory: F-2.
- **Digest**: canonical (explicit columns, primary-key order, `json.dumps(..., ensure_ascii=False)`), independent of
  `built_at`, covers every content table and the meta keys except `built_at`/`index_digest`; D-048 matches the code. The
  recipe-pin test covered only `meta` and `entry`: F-4.
- **FTS**: rows are inserted with `rowid = entry.id` in id order (`ORDER BY id`), `'optimize'` follows the fill, no
  `'rebuild'`, no `VACUUM`; columns are exactly as D-048 states (name + sorted aliases, intents, summary, bodies
  without headings).
- **Repository**: `get_entry` follows D-005 (name by `(rank, id)`, then alias by `(rank, name, id)`, section filter on
  both). `fts` hostile inputs tried: `NEAR/3`, `{name}: x`, `x OR`, `“x”`, `ls\`, `-`, `*`, `^ls`, `name:ls`, SQL
  injection, NUL, 10 000-character token, 500 parentheses, and the lone surrogate `"\ud800"`: the surrogate raised a raw
  `UnicodeEncodeError` (F-1, decision below). All other inputs were already total. Corrupt rows give
  `index corrupt: <table> row <id>`; every row converter returns model types with enum members.
- **Fixture**: original text only. Spot check of 9 entries against
  `mandoc -T ascii /usr/share/man/man1/<name>.1 | col -bx`: `ls`, `tar` and `grep` (NAME, SYNOPSIS, start of
  DESCRIPTION) and the NAME line of `cat`, `du`, `sort`, `head`, `kill`, `date`. Wording and structure differ; `head`
  ("print the first lines of a file" vs "display first lines of a file") and `date` ("show or set the system date and
  time" vs "display or set date and time") are near paraphrases of a one-line NAME text, too short and plain to be
  copyable prose, so they stay. Required shapes present (echo x3, `[` alias of `test`, exe-only
  `bat`, `sync` 1/8, tar curated vs tldr pair, danger examples, intents order, `find` long section). D-005 ranks right;
  build is deterministic (the digest test). One factual slip in a note: F-6.

## Findings

- **F-1** (medium) `repo`: `Repository.fts` and `get_entry` raised a raw `UnicodeEncodeError` for text with a lone
  surrogate (`"\ud800"`), because `sqlite3` cannot bind it. The test strategies of the Phase 4 tests never produced one
  (`st.text()` excludes surrogates). D-046 recorded the limitation for content, but user text reaches the repository.
- **F-2** (medium) `store/_open.py`: `open_readonly` called `path.is_file()` unguarded; it raises `PermissionError`
  when a parent directory cannot be searched, so a raw `OSError` escaped instead of `IndexUnavailableError`.
- **F-3** (low) `store/_writer.py`: `IndexWriter.__enter__` read the migration files after `sqlite3.connect`; a
  `ValueError` from `load_migrations` (bad bundled series) left the created file and an open connection behind (only
  `sqlite3.Error` was handled).
- **F-4** (low, test gap) `test_store_finalize.py`: the recipe-pin test covered `meta` and `entry` only, so a changed
  column list or order of a child table in the digest would not have failed it by name.
- **F-5** (low, test gap) TEST-STRATEGY §4 `test_store_repo_roundtrip.py` was missing: round trips existed only against
  the shared fixture or raw SQL, never `IndexWriter` + `open_readonly` + `Repository` on independent data.
- **F-6** (low, fixture) `entries.json` `ls` note claimed the macOS `ls` has no long option names; the macOS man page
  lists `--color=when`.

Kept on purpose:

- Integer arguments (`limit`, ids) above 64 bits raise `OverflowError` (checked: `sqlite3` behaviour); they come from the
  index or the caller, not from user text. Recorded in D-049.
- `sqlite3.connect` is not given a timeout: the index is written once into a new file and read-only afterwards.
- `content_item` has no writer or reader (reserved by DITS §9); it is part of the digest and stays empty.

## Fixes

- **F-1** New private `repo/_text.py` (`is_encodable`). `fts_query` returns `None` for text that does not encode, so
  `fts` returns `[]`; `get_entry` returns `None` when the name or the section does not encode. Decision: make both total
  (nothing stored can equal such text), not a documented limitation. Tests: `fts_query` cases, the parametrized
  hostile list gained 6 inputs (incl. surrogates, `NEAR/3`, `ls OR`, curly quotes, a trailing backslash), a Hypothesis
  property over a hostile alphabet that includes surrogates and NUL (`test_fts_property_hostile_alphabet_is_total`),
  `test_fts_and_get_entry_with_an_unencodable_name_match_nothing`, `test_get_entry_with_a_nul_in_the_name_is_none`.
  D-049 amendment.
- **F-2** `open_readonly` maps an `OSError` of `is_file()` to `IndexUnavailableError("index unreadable: <path>")`.
  Test `test_open_readonly_rejects_file_in_unsearchable_directory`. D-047 amendment.
- **F-3** `__enter__` builds the script before connecting. Test `test_unreadable_migrations_create_no_file`. D-047
  amendment.
- **F-4** `test_digest_recipe_covers_every_child_table` computes the digest by hand for an entry with every child
  table (two aliases written out of order, two sections, two examples with and without `danger`, two subcommands with and
  without `entry_name`, a note, two related names, two intents, an extra meta key, `explain`, `rank`, non-ASCII text).
  It passed on the first run, so the recipe in D-048 and the code agree; the earlier test is kept. D-048 note.
- **F-5** `tests/integration/test_store_repo_roundtrip.py`: writes three entries (two share a name with ranks 0 and 1)
  with every child table, then reads each back through `Repository` and compares with the written values (entry, explain,
  sections, examples, subcommands, notes, related, aliases, intents, meta, stats, FTS hit per written text); a rolled-back
  build is rejected by `open_readonly`.
- **F-6** The note now reads "Here -G turns on color; GNU ls reads -G as --no-group and colors only with --color."
  (reviewer: the executor's first rewording still implied `--color` is GNU-only, but macOS `ls` accepts
  `--color=when` too). No test depends on it.

R10 edits to later PLAN tasks (facts verified against the merged code and the tests above):

- T-5.1: `NameRow` fields and order, `FtsHit.score` is `-bm25` (higher is better), `FTS_WEIGHTS`, no prefix search in FTS
  (prefix and fuzzy tiers come from `names()`), a lone-surrogate query gives `[]`.
- T-5.2: the benchmark index is written with `with IndexWriter(path) as w: ...; w.finalize(built_at=...)` and read through
  `Repository(open_readonly(path))` (an unfinalized index has an empty `search_fts`).
- T-5.3: `get_entry_by_id`, `explain`, idempotent `close`, `meta()["attribution"]`, `get_entry` does not strip the name,
  error type.
- T-6.1: fingerprint parts go into meta through `set_meta` before `finalize`, so they are part of the digest; read back
  with `Repository.meta()`.
- T-6.5: `NewEntry(..., rank, explain)`, ids follow write order, child lists once per entry, the `with ...; digest =
  w.finalize(built_at=clock())` shape, a stale `.new` must be removed first, and a rolled-back file must be removed by
  the builder.
- T-7.3 / T-9.3: `Repository.stats()` fields (`IndexStats(entries, man_pages, builtins, curated, examples, subcommands)`);
  no per-verify-mode counts; `open_readonly` errors for doctor.

## Commands run

- `make check` (baseline) → green, 1468 passed, store 99.3%, repo 100.0%, overall 99.9%, 3 contracts kept.
- `uv run pytest` on the five Phase 4 test files after adding the tests → 11 failed (F-1 x9, F-2, F-3), 266 passed;
  after the fixes → all passed (the F-4 and F-5 tests passed immediately: they pin existing behaviour).
- Adversarial inputs were exercised through the committed parametrized and Hypothesis tests (no scratch script: the
  loop's permissions do not allow running ad-hoc Python).
- `mandoc -T ascii /usr/share/man/man1/<name>.1 | col -bx` for the fixture spot check (`ls`, `tar`, `grep` first lines;
  `cat`, `du`, `sort`, `head`, `kill`, `date` NAME line).
- `uv run ruff format .`; `make check` → green, 1499 passed, store 99.4%, repo 100.0%, overall 99.9%, gate passed, 3
  contracts kept.
- `make py311` → 1499 passed on Python 3.11.

## Open items

None.
