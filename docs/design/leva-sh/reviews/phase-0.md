# Phase 0 review

- Date: 2026-11-22 · Scope: T-0.1..T-0.7 · Reviewer: ralph loop

## Scope

Everything Phase 0 produced: the constitution (`CLAUDE.md`, `DECISIONS.md`, `.gitignore`, design-system
snapshot), the Python scaffold (`pyproject.toml`, `Makefile`, 17 package stubs), the test harness and
arch fitness functions, the coverage gate, the spikes S-1, S-2 and S-3 (code and findings), and the
design-system update proposal. Checked against PLAN §4 checklist RC and `CLAUDE.md`. No production code
exists yet, so most RC items are not applicable to this phase.

## Checked items

Most RC items have nothing to review before Phase 1, because no package has code yet.

1. Public API matches DITS + DECISIONS: n.a. (no public API yet); the six future tasks that carry
   amended DECISIONS facts were corrected (F-6, F-7, F-8).
2. Module docstrings state the single responsibility: ok. The 17 `src/leva/<pkg>/__init__.py` docstrings
   match the `CLAUDE.md` package table (checked one by one).
3. Only `LevaError` crosses boundaries: n.a. (no code).
4. No global mutable state; env/clock/paths injected: n.a. (no code); the `environment` arch rule
   keeps `os.environ` in `cli` only.
5. Small functions, naming: ok for `tests/arch/rules.py` and `tools/coverage_gate.py` (ruff C901 ≤10
   passes in `make check`).
6. Tests meaningful and deterministic: ok. The arch checker has planted and allowed cases for every
   rule, including prefix traps; the new `dev-code` rule has three planted and one allowed case.
7. Coverage gates: ok. `make check` gate: `leva` 100.0% (threshold 85%), overall 100.0% (85%); the
   17 stub packages have no statements and are skipped.
8. No `Any` in public APIs, no unjustified `cast`: ok (`mypy --strict` passes; no `cast` in src).
9. Layers and arch tests: ok. import-linter: 3 contracts kept, 0 broken; `pytest tests/arch`: 65 passed
   (61 before F-4, plus 3 planted and 1 allowed cases).
10. Docs consistent: findings F-1, F-2, F-3, F-4 (docs part), F-5, F-6, F-7, F-8, F-9, F-10; all fixed.

## T-0.R steps

1. **Scaffold vs `CLAUDE.md`.** `pyproject.toml` matches T-0.2 steps 1–6 (ruff select/ignore/per-file,
   mypy flags and `tests.*` override, pytest addopts/markers/timeout/filterwarnings, coverage, the three
   importlinter contracts). `Makefile` matches PLAN §4 (`check` = lock check, ruff check, format check,
   mypy, lint-imports, pytest with coverage, coverage gate; plus `lint fmt type arch test cov live verify
   py311`). No divergence. `[project.scripts]` is absent on purpose (T-9.1). The one wording gap is F-2.
2. **Spike outcomes in DECISIONS.** D-007 confirmed and amended (S-2); D-004, D-005, D-008 amended (S-2);
   D-027 new (S-2); D-006 amended and D-032 new (S-3); D-012 amended (S-1). All present in `DECISIONS.md`.
3. **"Impact on plan" applied**, confirmed by grep on `PLAN.md`:
   - S-2: T-2.2 `run_manpath(env, ...)` (line 358); T-2.4 `stub_target` raw path and
     cwd = the page's man root, header/footer-only output = ManRenderError (lines 385–386); T-2.5 any-case
     headings, D-027 (line 395); T-2.6 inline terms (line 414); T-6.3 rsync/Xsan/missing-target stub tests
     (line 597).
   - S-3: no task edit needed; T-4.1, T-4.2 and T-4.4 are covered by the D-006 amendment.
   - S-1: T-8.1 names `ansi-background`/`ansi-foreground` and the `block-cursor-*`, `input-cursor-*`,
     `*-selection-*`, `border*`, `scrollbar*` variables (line 722).

## Findings

- **F-1** `CLAUDE.md` docs map omits `UX.md`, `demo/leva-demo.html`, the research note, the design-system
  update proposal and `DESIGN-STATUS.md`.
- **F-2** `CLAUDE.md` says every module starts with `from __future__ import annotations`; the 16
  docstring-only `__init__.py` files and `tools/__init__.py` do not, and ruff `required-imports`
  exempts docstring-only modules.
- **F-3** `CLAUDE.md` content rules miss D-030 (`danger` is required for destructive examples).
- **F-4** D-024 "spike code is never imported by src" was not enforced by any arch rule (and the same
  holds for `tests` and `tools`).
- **F-5** The D-016 denylist names `softwareupdate` twice.
- **F-6** D-030 (`Example.danger`) is carried by T-3.1 and T-8.6 only; the model, schema and ingest tasks
  (T-1.1, T-4.1, T-6.4) do not have the field.
- **F-7** D-029 ranks earlier intents higher, but the schema has no intent order, `SearchResult` has no
  `via`, and "synonym" has no field.
- **F-8** D-031 "up to 3 nearest names" has no lower-layer API, and `tui` may not import `search`.
- **F-9** `DESIGN-STATUS.md` says `ANALYSIS.md` was never written to disk, but it exists.
- **F-10** (found at review) F-6 and F-7 stopped at the schema: DITS §9 `IndexWriter` has no intent
  writer, so nothing says who stores `intent.ord`; T-4.4 does not say `Repository.examples` reads
  `example.danger` back (a default `None` would drop it silently); the fixture index (T-4.3) has no
  example with `danger`, which the card tests of T-8.6 need.

No further findings from the further checks (all "ok" below).

## Fixes

- **F-1** `CLAUDE.md`: one docs-map row each for `UX.md` (marked "binding via D-028"), the demo, the
  research note, the update proposal and `DESIGN-STATUS.md`. The binding-order sentence is unchanged.
- **F-2** `CLAUDE.md` coding conventions reworded: "Every module with code starts with ... (enforced by
  ruff `required-imports`; docstring-only modules are exempt)". The `__init__.py` files are untouched.
- **F-3** `CLAUDE.md` content authoring rules: new bullet on D-030.
- **F-4** `tests/arch/rules.py` gains `Restriction("dev-code", {"spikes", "tests", "tools"}, {})`.
  `tests/arch/test_restricted_imports.py`: three planted cases (`spikes`, `tests`, `tools-even-in-cli`)
  failed first, then passed; one allowed case (`dev-code-prefix-trap`). `CLAUDE.md` stdlib-restrictions
  sentence extended. DECISIONS: amendment under D-025.
- **F-5** DECISIONS: amendment under D-016; recount gives 47 distinct names. PLAN Appendix A untouched.
- **F-6** PLAN: T-1.1 (`Example.danger` step, Refs + D-030), T-4.1 (`example.danger` column, Refs + D-030),
  T-6.4 (attachment copies `danger`, Refs + D-030). DECISIONS: amendment under D-030.
- **F-7** PLAN: T-4.1 (`intent.ord INT`, Refs + D-029), T-4.4 (`NameRow.intents` ordered by `intent.ord`,
  Refs + D-029), T-5.1 (`SearchResult.via`, intent tiers by `ord`). DECISIONS: amendment under D-029.
- **F-8** PLAN: T-5.1 (`Searcher.nearest_names`, Refs + D-031), T-5.3 (`Library.nearest_names`,
  Refs + D-031). DECISIONS: amendment under D-031.
- **F-9** `DESIGN-STATUS.md` (Italian): phase 2 ticked; the `ANALYSIS.md mancante` bullet replaced by a
  one-line note that it was saved afterwards.
- **F-10** PLAN: T-4.1 (`add_intents` stores `ord` = list index; `add_examples` stores `danger`), T-4.3
  (a fixture example with `danger`), T-4.4 (`examples(entry_id)` returns `danger`, Refs + D-030).
  DECISIONS: the D-029 and D-030 amendments name these tasks.

## Commands run

- `make check` (before changes) → green: 148 passed; coverage gate: `leva` 100.0%, overall 100.0%;
  lint-imports 3 contracts kept.
- `uv run pytest tests/arch -q --no-cov` with the new cases and no rule → 3 failed, 62 passed; with the
  rule → 65 passed.
- `uv run python -c "import leva;print(leva.__version__)"` → `0.1.0`.
- `uv run python spikes/s2_mandoc.py --quick` → exit 0 (200 pages, 0 failures).
- `uv run python spikes/s3_fts5.py --quick` → exit 0 (all required checks ok on 3 interpreters).
- `uv run python spikes/s1_textual_background.py --analyze` → exit 0 without `COLORTERM`; "gate failures:
  none".
- Design-system snapshot: `docs/design/design-system-snapshot.md` and the external
  `PyDF Tool/CLAUDE.md` were read side by side with the Read tool (119 lines each, identical). The `diff -q`
  command was denied by the permission mode in this run, so the identity rests on that reading.
- `grep -c '^## ' CLAUDE.md` (Grep count) → 10 (≥ 9).
- Grep for `TODO|FIXME|XXX|NotImplementedError` over `src tools tests spikes` → no match.
- Grep for `type: ignore` and `noqa` → no `type: ignore`; two `noqa: S101` in `spikes/s3_fts5.py`, each
  with a code and a reason.
- Grep of `PLAN.md` for the S-1/S-2/S-3 impact markers → all present (see T-0.R step 3).
- `uv run ruff format .` → 32 files left unchanged; final `make check` → green: 152 passed,
  coverage gate passed, lint-imports 3 contracts kept.

## Open items

- U-1 (S-1 manual run in Terminal.app, iTerm2, Ghostty): open, non-blocking.
- U-2 (apply the design-system update to the external file, then refresh the snapshot): open; blocks T-8.11.
- U-3 (user review of D-001..D-024): open, non-blocking.
- U-4 (confirm the curated command list and priorities): open, non-blocking.
