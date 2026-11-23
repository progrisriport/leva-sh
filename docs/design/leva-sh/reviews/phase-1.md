# Phase 1 review

- Date: 2026-11-23 · Scope: T-1.1..T-1.5 · Reviewer: ralph loop

## Scope

The five leaf packages Phase 1 delivered, read in full: `leva.model` (`_errors.py`, `_types.py`),
`leva.placeholders`, `leva.paths`, `leva.clipboard`, `leva.config`, and their tests
(`tests/unit/test_{model,placeholders,paths,clipboard,config}.py`, `tests/live/test_clipboard_live.py`).
Checked against PLAN §4 checklist RC, DITS §0–§4, D-002, D-003, D-011, D-013, D-030 and D-033..D-037,
and cross-checked against the later PLAN tasks that consume them (T-3.1, T-4.4, T-6.x, T-8.x, T-9.x).

## Checked items

Baseline before changes: `make check` green, 443 passed (291 in the five Phase 1 test files),
lint-imports 3 contracts kept.

1. Public API matches DITS + DECISIONS: ok. Field order, defaults and keyword-only arguments match
   DITS §1–§4 and D-033..D-037 (`test_value_objects_keep_field_order`, exact error strings asserted in
   the tests). The known deviations are recorded: `leva.model._errors` (D-033), `resolve(env, home)`
   (D-035), `ConfigError` (D-003), `Example.danger` and `Subcommand.body` (D-030, T-1.1). Finding F-3
   (later tasks that miss D-033).
2. Module docstrings and public docs: finding F-2. All five module docstrings state the single
   responsibility (`tests/unit/test_package.py` passes). `parse`, `Clipboard.copy`, `LevaPaths.resolve`
   and `load_config` document pre/post conditions; `PbcopyClipboard.copy` had only the `Raises` part and
   `LevaPaths` had no `Attributes` section.
3. Only `LevaError` crosses boundaries: ok. `clipboard` maps `OSError`, `TimeoutExpired` (both `from exc`)
   and a non-zero exit; `config` maps `OSError`, `UnicodeDecodeError` and `TOMLDecodeError` (`from exc`);
   `paths` raises `ConfigError` for a relative `LEVA_HOME`. `ValueError` is used only for programmer
   errors (relative `home`, empty or oversized clipboard text, non-positive timeout, model invariants).
   The tests assert `__cause__` for each wrapped error.
4. No global mutable state, injected env/clock/paths: ok. Grep for `os.environ|getenv|expanduser|
   Path.home|datetime|time.time|monotonic|sleep(` over `src/leva` → no match. The only module-level
   containers are `_PBCOPY_ENV` (a `MappingProxyType`) and tuples/`Final` strings.
5. Small functions, no duplication, naming: ok. ruff C901 ≤10 passes. Two observations, no change:
   `config._sections`/`_path_list` repeat the invariants of `LevaConfig.__post_init__`, on purpose (the
   loader reports `file:key[i]: reason` as `ConfigError`, the dataclass raises `ValueError` for
   programmers; the messages differ); `placeholders` has one scanner shared by `parse`, `names`,
   `to_plain` and `problems`; clipboard text validation is one shared `_check_text`.
6. Tests meaningful and deterministic: ok. TEST-STRATEGY §2 rows are covered (model equality/hash/immutability/
   slots; paths `LEVA_HOME` vs default and no I/O; placeholders properties, escape, unclosed, adjacent,
   unicode; clipboard fake binaries for exit ≠ 0, timeout, missing binary, plus the live round trip). §3
   edge cases that apply: names `[`, `[[`, `.`, `:` (`VALID_NAMES`), unicode and NBSP, 64 KiB counted in
   bytes, repeated `{{x}}`. No test only asserts "no exception"; the Hypothesis profile is derandomized.
   Grep for `sleep` in `tests` → only `exec /bin/sleep 5` inside a fake `pbcopy` with a 0.2 s timeout
   (the timeout path itself), no `time.sleep`. Tests do not depend on order. The live test was not run
   here (it touches the real clipboard; not part of the gate).
7. Coverage gates: ok (before and after the fixes). `tools/coverage_gate.py`: clipboard 100.0% (85%),
   config 100.0% (85%), leva 100.0% (85%), model 100.0% (85%), paths 100.0% (85%), placeholders 100.0%
   (90%), overall 100.0% (85%); 376 statements, 98 branches, 0 missed.
8. No `Any`, no unjustified `cast`: ok. Grep for `\bAny\b|cast\(` over `src` and `tests` → no match. The
   9 `# type: ignore[...]` and the one `# noqa: PT011` are in tests only, each with a code and a reason.
   Grep for `TODO|FIXME|XXX|NotImplementedError` → no match.
9. Layers and arch tests: ok. `make arch` → 3 contracts kept, 0 broken; `uv run pytest tests/arch -q` →
   65 passed. `paths`, `clipboard` and `config` import only `leva.model`; `placeholders` imports nothing.
10. Docs consistent: finding F-3. DITS §0 `leva.model.errors` (D-033), ARCHITECTURE `resolve(env)` (D-035)
    and the DITS §1 `Example`/`Subcommand` fields (D-030, D-033) are all covered by DECISIONS entries.
    CLAUDE.md states no fact Phase 1 made wrong.

## Findings

- **F-1** `src/leva/paths/__init__.py:11-14`: `CONFIG_FILE_NAME`, `INDEX_DB_NAME` and `LOG_DIR_NAME` were
  public names missing from `__all__`, used only inside the module (the same defect the T-1.4 reviewer
  fixed for `UNAVAILABLE`). `LEVA_HOME_VAR` was not `Final`.
- **F-2** `src/leva/clipboard/__init__.py:64` `PbcopyClipboard.copy` lacked the DITS §3 pre/post
  conditions (only `Raises`); `src/leva/paths/__init__.py:20` `LevaPaths` lacked an `Attributes` section
  (the `model` dataclasses have one).
- **F-3** Two later tasks rely on facts D-033 changed. T-3.1 builds an `Example` from YAML after
  `placeholders.problems`; a YAML `|` block ends with a newline, which `Example.cmd` rejects with
  `ValueError`, so a valid-looking file would crash validation instead of raising `ContentError`. T-4.4
  reads `kind`/`origin` back from SQLite; the model rejects plain strings (the T-1.1 warning was only in
  PROGRESS.md, not in the task).

No other finding. Cross-checks that passed: T-3.1 message `commands/tar.yaml:examples[2].cmd: unclosed
placeholder` is `file:field: ` + `UNCLOSED_PLACEHOLDER` (D-034); T-6.1 `config digest` is
`LevaConfig.digest()` (D-037); T-9.2 wires `LevaPaths.resolve(env, home)` and `load_config(paths.config_file,
home)` without contradicting D-035/D-037; T-8.6 uses `FakeClipboard.last`/`history`/`fail` and shows
`ClipboardError.message` (D-036); `Example.danger` is stored as text and read back by T-4.4 (D-030).

## Fixes

- **F-1** The three constants are now private `Final` (`_CONFIG_FILE_NAME`, `_INDEX_DB_NAME`,
  `_LOG_DIR_NAME`); `LEVA_HOME_VAR` is `Final`; `__all__` moved above the constants. No other file
  referenced the old names (Grep over the repo).
- **F-2** `PbcopyClipboard.copy` states `Pre`/`Post` like the `Clipboard` Protocol; `LevaPaths` documents
  its three attributes.
- **F-3** PLAN R10: T-3.1 gets a step "cmd meets the `Example.cmd` invariants of D-033 ... before
  `Example` is built" and `D-033` in its Refs; T-4.4 gets a step on `Kind(value)`/`Origin(value)` and
  `D-033` in its Refs. DECISIONS: amendment under D-033 naming both tasks.

## Commands run

- `make check` (before changes) → green: 443 passed, coverage gate passed (table above), lint-imports 3
  contracts kept.
- Reads of every Phase 1 source and test file; Grep for `os.environ|getenv|expanduser|Path.home|datetime|
  time.time|monotonic|sleep(` (src) → no match; `\bAny\b|cast\(|type: ignore|noqa|TODO|FIXME|XXX|
  NotImplementedError` (src, tests) → only the 9 + 1 justified suppressions in tests; `sleep` (tests) → one
  fake-binary script; `CONFIG_FILE_NAME|INDEX_DB_NAME|LOG_DIR_NAME` (repo) → only `paths`.
- Grep of `PLAN.md` for `problems|digest|FakeClipboard|LevaPaths|load_config|Kind(|Origin(` → consumer
  cross-checks above.
- `uv run pytest --no-cov -q` on the five Phase 1 test files → 291 passed.
- `make arch` → 3 contracts kept; `uv run pytest tests/arch -q --no-cov` → 65 passed.
- `uv run ruff format .` → 40 files left unchanged; final `make check` → green: 443 passed, coverage gate
  passed (all packages 100.0%), lint-imports 3 contracts kept.
- `make live` / `tests/live/test_clipboard_live.py`: not run in this review (real clipboard; it passed once
  during T-1.4 according to PROGRESS.md).

## Open items

None new. U-1..U-4 from the Phase 0 review are unchanged.
