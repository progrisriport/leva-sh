# S-3 — FTS5 availability and index size

- Project: Leva (`leva-sh`) · Date: 2026-11-22 · Task: T-0.5 · Status: done
- Related: [ADR-0003](../ADR/ADR-0003-storage-sqlite-fts5.md) · [ANALYSIS R-11](../ANALYSIS.md) · [DECISIONS](../DECISIONS.md) (D-006, D-024, D-027) · [S-2](S-2-mandoc.md)
- Code: [`spikes/s3_probe.py`](../../../../spikes/s3_probe.py) · [`spikes/s3_fts5.py`](../../../../spikes/s3_fts5.py)

Verdict: every interpreter found on this Mac (3.13 project, 3.12 at `/usr/local/bin`, 3.9
system) has SQLite with everything the index design needs: FTS5 with
`unicode61 remove_diacritics 2`, a contentless table with `bm25` column weights, the `IFNULL`
unique index and `mode=ro` URI opens. The prototype index of all 2598 rendered section 1/8 pages
is 41.05 MB (45.51 MB before `VACUUM`), well under the 100 MB of NFR-15. FTS queries take
0.09 ms p50 and 0.23 ms p95, so FTS is not a budget risk for NFR-2. D-006 is confirmed, with
four additions: `'rebuild'` does not exist on a contentless table (finalize inserts the rows
itself), `'optimize'` runs after the fill, the read-only open uses `Path.as_uri()`, and a
corrupt index only shows up at the first query.

## Method

`spikes/s3_fts5.py` (run with `uv run python spikes/s3_fts5.py`; `--quick` uses a 200-page
stride subset, `--json PATH` dumps the raw report into gitignored `spikes/out/`):

1. **Probe per interpreter.** It looks for the project interpreter (`sys.executable`),
   `/usr/local/bin/python3*`, `/opt/homebrew/bin/python3*` and `/usr/bin/python3`, dedupes by
   resolved path and runs `spikes/s3_probe.py` under each with `-I`, a minimal environment, a
   60 s timeout and a fresh scratch dir. The probe is stdlib-only and Python 3.9 compatible.
   It runs nine required checks and seven informational ones (tables below) on in-memory
   databases, except the read-only checks, which use a scratch path with a space, `#` and `%`
   in it.
2. **Pages.** It discovers and renders pages exactly as S-2 does (D-004, D-005, D-007: first copy
   per `(name, section)`, stubs excluded, `mandoc -T ascii -O width=80`, 8 workers) and drops
   failed renders.
3. **Rows.** Per page: name, section, origin (`homebrew` under `/opt/homebrew` or
   `/usr/local`, else `macos`), summary (text after the first NAME separator, D-027) and the
   ordered sections as rendered (D-012 keeps the 80-column layout).
4. **Prototype index.** DITS §9 schema with the D-006 changes (`entry.rank`, the `IFNULL`
   unique index, no plain `UNIQUE`). One transaction fills `entry` and `doc_section` in sorted
   key order, then fills the contentless `search_fts` from Python in id order. After the commit:
   `'optimize'`, `ANALYZE`, `PRAGMA integrity_check`, `VACUUM`. Sizes use 1 MB = 1,000,000
   bytes. `dbstat` gives the size per table.
5. **Latency.** The index is opened with `Path.as_uri() + "?mode=ro"`. 20 fixed queries run
   through a T-4.4-style sanitiser (every token double-quoted, `compr*` as `"compr"*`) with
   `SELECT rowid, bm25(search_fts, 10.0, 5.0, 2.0, 1.0) ... ORDER BY score LIMIT 50`: one
   warm-up pass, then 10 timed passes (200 executions). Entry names are joined outside the
   timed part.

The report holds counts, sizes, timings, error messages and command names only. No man page
prose is committed here or in the code.

## Environment

| Item | Value |
|---|---|
| macOS | 27.2.1, arm64, 10 CPUs |
| Project Python | 3.13.12 (uv env), SQLite 3.50.4 |
| mandoc | `/usr/bin/mandoc` (system), same corpus as S-2 |
| Page cache | warm |

## Interpreters

| Label / path | Python | SQLite | Machine | fts5 | contentless | bm25_weights | optimize | quoting | ifnull_unique | ro_uri | ro_missing | ro_garbage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| project: `.venv/bin/python3` | 3.13.12 | 3.50.4 | arm64 | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| `/usr/local/bin/python3` | 3.12.2 | 3.45.1 | arm64 | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| `/opt/homebrew/bin/python3*` | not present | | | | | | | | | | | |
| `/usr/bin/python3` | 3.9.6 | 3.54.0 | arm64 | ok | ok | ok | ok | ok | ok | ok | ok | ok |

`/usr/bin/python3` is a real 3.9.6 result: the probe ran there without a syntax error. Leva
targets Python 3.11 or later, so this row only shows that the features do not depend on a
recent interpreter. (`sqlite3.threadsafety` reads 3 on the two newer builds and 1 on the
system build; the spike is single-threaded and does not test what that means for Leva.)

Informational checks (same three interpreters, same result unless noted):

- `plain_unique_nulls`: a plain `UNIQUE(name, section, origin)` accepts two
  `('ls', NULL, 'macos')` rows. This is why D-006 uses the `IFNULL` index.
- `rebuild_contentless`: `INSERT INTO t(t) VALUES('rebuild')` is rejected with
  `'rebuild' may not be used with a contentless fts5 table`.
- `naive_uri`: `f"file:{path}?mode=ro"` on a path containing `#` and `%` fails with
  `no such table: t`. The URI is truncated at the `#`, so SQLite opens a different, empty
  database. This justifies `Path.as_uri()`.
- `trigram`, `contentless_delete`, `json1`: available everywhere (SQLite 3.45.1 is the
  oldest, and `contentless_delete=1` needs 3.43).
- `dbstat`: available on the project and the system interpreter, missing on 3.12.2 (SQLite
  built without `ENABLE_DBSTAT_VTAB`). Only the spike uses it, to break down the size.
- `ENABLE_FTS5` appears in `PRAGMA compile_options` on all three.

Observed messages (identical on all three unless noted):

| Check | Observation |
|---|---|
| `contentless` | `MATCH` returns the explicit rowid; `SELECT name` returns NULL |
| `bm25_weights` | order is name row, summary row, body row (weights 10, 5, 2, 1; three filler rows keep IDF positive) |
| `quoting` | unquoted `git-commit` raises `no such column: commit`; unquoted `NEAR(x` raises `fts5: syntax error near ""`; a bare `AND` raises `fts5: syntax error near "AND"`; a bare `NEAR` raises nothing (an ordinary term) and `name:x` raises nothing (a valid column filter, so it silently changes the query); `"git-commit"`, `"near(x"`, `"near"`, `"and"`, `"name:x"`, `"x*"` and `"a ""b"""` raise nothing |
| `ifnull_unique` | second `('ls', NULL, 'macos')` raises `IntegrityError: UNIQUE constraint failed: index 'k'`; `('ls', '1', 'macos')` is accepted |
| `ro_uri` | read works; write raises `OperationalError: attempt to write a readonly database` |
| `ro_missing` | `connect` itself raises `OperationalError: unable to open database file` |
| `ro_garbage` | `connect` succeeds; the first query (`PRAGMA user_version`) raises `DatabaseError: file is not a database` |

## Prototype index

2598 pages rendered, 0 failed, 2552 with a summary, 627 with origin `homebrew`.

| Table | Rows |
|---|---|
| `entry` | 2598 |
| `doc_section` | 17865 |
| `alias` | 0 (the spike does not extract aliases) |
| `search_fts` (rows in `search_fts_docsize`) | 2598 |

| Stage | Bytes | MB |
|---|---|---|
| After commit | 42,504,192 | 42.50 |
| After `optimize` + `ANALYZE` | 45,510,656 | 45.51 |
| After `VACUUM` | 41,054,208 | 41.05 |

`integrity_check` returns `ok`. Size per object after `optimize` + `ANALYZE` (`dbstat`, bytes):

| Object | Bytes |
|---|---|
| `doc_section` | 31,240,192 |
| `search_fts*` (all FTS5 shadow tables) | 9,400,320 |
| `entry` | 315,392 |
| `entry_key` | 81,920 |
| `alias`, `alias_alias`, `meta`, `sqlite_autoindex_meta_1`, `sqlite_schema`, `sqlite_stat1` | 4,096 each |

These add up to 41.06 MB. The other 4.45 MB of the 45.51 MB file are free pages that
`optimize` leaves behind when it merges the FTS segments; `VACUUM` returns them.

Build timings (seconds, full run):

| Step | Time |
|---|---|
| Render (8 workers) | 3.06 |
| Parse into rows | 0.31 |
| Insert entries and sections | 0.04 |
| Fill `search_fts` | 0.20 |
| `optimize` | 0.05 |
| `ANALYZE` | 0.003 |
| `VACUUM` | 0.16 |
| Total | 3.8 |

## Latency

Read-only open plus the first query: 0.28 ms. Over 200 timed executions (20 queries, 10
passes): p50 0.093 ms, p95 0.232 ms, max 0.286 ms. Each execution scores all matches and
returns the best 50.

| Query | Median ms | Hits | Top 3 |
|---|---|---|---|
| `ls` | 0.068 | 50 | git-ls-tree(1), git-ls-remote(1), which(1) |
| `tar` | 0.053 | 50 | git-get-tar-commit-id(1), tar(1), git-archive(1) |
| `copy file` | 0.275 | 50 | ssh-copy-id(1), cp(1), uucp(1) |
| `compress folder` | 0.017 | 3 | perl5120delta(1), perlos2(1), hdiutil(1) |
| `extract archive` | 0.058 | 50 | bsdtar(1), tar(1), git-get-tar-commit-id(1) |
| `disk usage` | 0.092 | 50 | fs_usage(1), snmpdf(1), quota(1) |
| `list processes` | 0.147 | 50 | pgrep(1), pkill(1), killall(1) |
| `kill process` | 0.080 | 50 | kill.d(1), kill(1), fixproc(1) |
| `file permissions` | 0.177 | 50 | mount_smbfs(8), git-init(1), cp(1) |
| `symbolic link` | 0.081 | 50 | ln(1), chgrp(1), chown(8) |
| `search text` | 0.137 | 50 | dseditgroup(8), zshzle(1), bzegrep(1) |
| `regular expression` | 0.138 | 50 | perl5303delta(1), awk(1), perl5283delta(1) |
| `environment variable` | 0.223 | 50 | gh-variable-set(1), xcrun(1), gh-variable-delete(1) |
| `ssh key` | 0.075 | 50 | gh-ssh-key(1), gh-ssh-key-add(1), gh-ssh-key-delete(1) |
| `git commit` | 0.167 | 50 | git-get-tar-commit-id(1), git-commit(1), git-commit-graph(1) |
| `checksum` | 0.043 | 50 | md5(1), md5sum(1), sha1(1) |
| `network interface` | 0.078 | 50 | ifconfig(8), snmpnetstat(1), netstat(1) |
| `compr*` | 0.216 | 50 | compression_tool(1), compress(1), lz4(1) |
| `perm*` | 0.189 | 50 | chmod(1), mount_smbfs(8), git-init(1) |
| `netw*` | 0.151 | 50 | networksetup(8), networkserviceproxy(8), perlnetware(1) |

Hits are capped by `LIMIT 50`. The entry called `ls` is 4th in the hit list for `ls`, and the
entry called `tar` is 2nd for `tar`.

## Findings

1. **FTS5 is not a constraint.** All three interpreters compile FTS5 and pass every required
   check. The oldest SQLite seen is 3.45.1, which is the floor to document. There is no
   Homebrew Python on this Mac, so that row is empty.
2. **Contentless tables read back NULL.** Column values, `snippet()` and `highlight()` are
   unavailable. D-010 computes `why` in memory instead, and the whole index is rebuilt each
   time, so nothing the design needs is lost.
3. **`'rebuild'` is rejected on a contentless table.** DITS §9 says finalize does an "FTS
   rebuild"; that is impossible here. T-4.2 already fills the table from Python with explicit
   rowids, which is the only way.
4. **`'optimize'` works and shrinks the FTS segments, but leaves free pages.** The file grows
   from 42.50 to 45.51 MB after `optimize` + `ANALYZE`, and `VACUUM` brings it to 41.05 MB for
   0.16 s. NFR-15 does not need `VACUUM`; finalize may run it after the commit (it cannot run
   inside the writer's transaction) to save 4.45 MB.
5. **The `IFNULL` unique index does what D-006 wants.** A second NULL-section row raises
   `IntegrityError`; the plain `UNIQUE` accepts it.
6. **The read-only open must use `Path.as_uri()`.** The naive `file:{path}?mode=ro` form
   fails on a path with `#` and `%` in it (the probe path also has a space; `#` starts a URI
   fragment, so SQLite looks for a different file). The real data dir,
   `~/Library/Application Support/leva`, has a space. `Path.as_uri()` percent-encodes these
   characters and needs an absolute path.
7. **Errors surface late.** A missing file fails at `connect`. A file with garbage bytes
   connects fine and fails at the first query with `file is not a database`.
   `open_readonly` must therefore run `PRAGMA user_version` before returning, and map every
   `sqlite3.Error` to `IndexUnavailableError`.
8. **FTS quoting.** Unquoted `git-commit` raises (`-` reads as a column filter), unquoted
   `NEAR(` and a bare `AND` raise a syntax error, and unquoted `name:x` silently becomes a
   column filter. A bare `NEAR` is only an ordinary term. Double-quoting every token, with an
   embedded `"` doubled, neutralises all of them: the quoted forms of `-`, `NEAR(`, `AND`, `:`,
   `*` and `""` all run without error. So T-4.4's list of operators is covered by quoting plus
   `"` doubling; a prefix query is the only place where a `*` goes outside the quotes.
9. **Size.** 41.05 MB for all man pages (45.51 MB without `VACUUM`) is inside the 30–60 MB
   that ADR-0003 expects. Of the 41.06 MB that `dbstat` accounts for, 76% is `doc_section`
   (the rendered text), 23% is the FTS index and the rest is under 1%. Curated content and
   tldr are not in the prototype and were not measured.
10. **Build time.** The whole prototype build is about 3.8 s, dominated by rendering (3.06 s).
    Index writing, FTS fill, `optimize` and `ANALYZE` together take 0.3 s, so NFR-3 (30 s) has
    a wide margin.
11. **Latency.** p95 is 0.23 ms and the maximum 0.29 ms, with a warm page cache. That is
    about 85 times under the 20 ms aim for the FTS stage.
12. **bm25 alone does not rank exact names first.** `ls` is 4th (`git-ls-tree`,
    `git-ls-remote` and `which` come first) and `tar` is 2nd (`git-get-tar-commit-id` comes
    first). A likely cause is that `unicode61` splits hyphenated names into tokens, so
    `git-ls-tree` also has `ls` in its name column; the spike did not isolate this. T-5.1's
    fuzzy name stage and ranking are meant to fix this, and nothing was tuned here.
13. **Aliases are not in the spike.** The prototype has an empty `alias` table, and the NAME
    line is not split into extra names. Each alias adds a few bytes to the FTS name column and
    one row to `alias`, which is negligible next to 41 MB.

## Conclusion

**NFR-15 (index ≤ 100 MB).** Met with a large margin: 41.05 MB after `VACUUM`, 45.51 MB
without. The wheel limit is unaffected, since the index is built on the user's Mac and not
shipped.

**R-11 (FTS5 absent).** The risk is very low: FTS5 is compiled into every SQLite seen
here, from 3.45.1 to 3.54.0. The doctor check stays as planned (create a small
`unicode61 remove_diacritics 2` FTS5 table in memory and report the SQLite version). No PLAN
task builds the LIKE fallback that ANALYSIS lists for R-11, and this spike gives no reason to
add one: D-032 records that v1 has no LIKE fallback.

**D-006 (schema refinements).** Confirmed: the `IFNULL` unique index, `entry.rank`, and a
contentless FTS5 table filled at finalize all work as specified. Additions: the FTS rows are
inserted by finalize itself, because `'rebuild'` is rejected on a contentless table (this
replaces the "FTS rebuild" wording of DITS §9); finalize runs `'optimize'` after the fill;
the read-only open uses `Path.as_uri() + "?mode=ro"` and runs `PRAGMA user_version` before it
returns.

## Decisions

- **D-006 confirmed and amended.** See the amendment in DECISIONS.md (findings 3, 4, 6, 7).
- **D-032 R-11 mitigation.** v1 has no LIKE fallback; a SQLite without FTS5 makes the build
  fail with IngestError and doctor names the cause. This changes ANALYSIS R-11.
- **No U-S3 task.** FTS5 is present everywhere, so no fallback task is needed.

## Impact on plan

No task edits needed. The tasks that touch the index already state what the findings
require:

- **T-4.1** says `open_readonly` uses a `mode=ro` URI and raises `IndexUnavailableError` for a
  missing, corrupt or wrong-`user_version` file. Findings 6 and 7 add how: build the URI with
  `Path.as_uri()` and run `PRAGMA user_version` at open. This is covered by the D-006
  amendment, which T-4.1 refers to, so the task text stays as it is.
- **T-4.2** already fills the contentless `search_fts` from Python in id order and says
  nothing about `'rebuild'`. The D-006 amendment adds `'optimize'`.
- **T-4.4** quotes every token and neutralises the FTS operators; finding 8 confirms that
  quoting is enough.
- **T-9.x doctor** keeps its "SQLite/FTS5" check, which D-032 makes the whole R-11
  mitigation (no LIKE fallback task is added).
- **T-11.x performance budgets** can use 0.23 ms p95 (FTS alone) as the reference for the
  search stage, and 3.8 s for the build.
- **DITS §9** ("FTS rebuild" in finalize) is a design doc and stays untouched; the D-006
  amendment takes precedence, as the binding order says.
