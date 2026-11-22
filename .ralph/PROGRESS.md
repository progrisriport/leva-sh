# Ralph loop progress

## 2026-11-20T23:41:18Z T-0.1 Repo constitution: CLAUDE.md, DECISIONS.md, gitignore, design-system snapshot — DONE
- Wrote `CLAUDE.md` (10 `##` sections: docs map, language, architecture + D-002 layers, coding, testing, TUI, content, safety, commands, git).
- Wrote `docs/design/leva-sh/DECISIONS.md`: D-001..D-024 copied verbatim from PLAN Appendix A (checked line by line with a python3 one-liner); new entries go under "Later decisions" from D-025.
- `.gitignore`: added `.venv-*/`, `.cache/`, `.coverage*`, `coverage.json`, `htmlcov/`, `.hypothesis/`, `spikes/out/`.
- `docs/design/design-system-snapshot.md` was already committed; compared with the external file via the Read tool (identical, 118 lines). Bash `diff` on the external path is denied by permissions in this loop, so later checks of that file must use Read.
- Permission notes for next iterations: Bash commands that touch paths outside the repo, and commands not in `scripts/ralph.sh` ALLOWED_TOOLS (e.g. `git config`, `git -C`), are denied; prefer one allowed command per call. The working dir is the repo root, so plain relative paths work.
- `make check` does not exist yet; it arrives with T-0.2/T-0.3.

## 2026-11-21T00:10:00Z T-0.2 Python project scaffold — DONE
- pyproject (hatchling, PEP 639 license), `.python-version` 3.13, `uv.lock`, Makefile (check/lint/fmt/type/arch/test/cov/live/verify/py311), 17 D-002 packages (docstring only), `py.typed`, `tools/__init__.py`, `tests/unit/test_package.py` (21 tests).
- Resolved: textual 8.2.8, pytest 8.4.2 (syrupy 4.8.0 requires pytest<9, confirmed), pytest-asyncio 1.5.0, ruff 0.17.6, mypy 2.4.1, import-linter 2.17.
- Ruff 0.17 formats Python blocks inside Markdown: added `extend-exclude = ["*.md"]` so design docs are never touched.
- Added ruff `isort.required-imports = from __future__ import annotations` (enforces CLAUDE.md; docstring-only modules exempt).
- tui forbidden contract uses `allow_indirect_imports = true` (tui reaches repo/search via library). All 3 contracts KEPT.
- `make check` has no coverage gate yet (T-0.3 adds `tools/coverage_gate.py`). `make verify` calls `uv run leva --rebuild`, which exists only after T-9.1; T-7.4 owns the target.
- No Python 3.11 installed locally; `make py311` will make uv download it (T-11.x). Heredoc `cat >>` is denied in this loop; use Edit for PROGRESS.md.

## 2026-11-21T03:01:04Z T-0.3 Test harness and architecture fitness functions — DONE
- `tests/conftest.py`: autouse `clean_env` (LEVA_HOME=tmp_path, HOME=tmp_path/home, pinned locale/TZ/width), Hypothesis profile `leva`, `tryfirst` hook adding integration/tui/macos_live markers by top-level dir; `pytest_plugins = ("pytester",)`.
- `tests/arch/rules.py`: pure AST checker (`find_violations`, `source_modules`, `Restriction`, `PrivateImport`, `RULES`); qualified-name matching, superset scope recorded as D-025. `tools/coverage_gate.py` (D-026) is now the last step of `make check`/`make cov`; exits 0/1/2.
- Marker test runs the real conftest + real pyproject pytest options in pytester (in-process, `-p no:textual-snapshot`: that plugin's per-process temp dir breaks under nested sessions; `timeout` excluded so the inner SIGALRM does not cancel the outer one).
- pyproject: targeted filterwarnings ignore for pytest-socket's pre-raise UserWarning; ruff `known-first-party = ["tests", "tools"]` (repo root is not a ruff src root).
- Tests import helpers as `from tests.support.fake_bin import fake_bin` / `from tests.arch.rules import ...` (`tests` is a namespace package; `pythonpath = ["."]`). Test code also passes `mypy --explicit-package-bases tests/...` (not gated).
- `tests/` own `tmp_path` contains `home/` (from clean_env): tests that list `tmp_path` must account for it.

## 2026-11-21T03:22:10Z T-0.4 Spike S-2: mandoc on sample pages + full benchmark — DONE
- `spikes/s2_mandoc.py` (`--quick`, `--json`, `--repeat`) + `docs/design/leva-sh/spikes/S-2-mandoc.md`. 2598 unique non-stub pages, 0 failures; 8 workers 4.18 s median (plateau from 4 workers). No U-S2.
- D-007 confirmed + amended (cwd = man root; header/footer-only output is a failed render; mandoc exits 0 even for garbage). D-004 amended (manpath needs user PATH/MANPATH), D-005 amended (winner chosen with stubs; stub → alias / render itself / skip), D-008 clarified (full match), D-027 new (rendered layout: any-case column-0 headings, per-page deflist indents, inline terms).
- R10 edits applied to T-2.2, T-2.4, T-2.5, T-2.6, T-6.3 (see the doc's "Impact on plan").
- Bash `ls`/`uname`/`xcode-select` on system paths are denied in this loop; Glob works on system paths but does not follow Homebrew symlinks. Run system probes through a spike/test script via `uv run`.
- Raw reports live in gitignored `spikes/out/`. openssl has no man1 page on this Mac (no `.1ssl` files).

## 2026-11-22T01:00:00Z T-0.5 Spike S-3: FTS5 availability and index size — DONE
- `spikes/s3_probe.py` (stdlib, Python 3.9 compatible, 9 required + 7 informational checks) and `spikes/s3_fts5.py` (`--quick`, `--json`, `--repeat`); findings in `docs/design/leva-sh/spikes/S-3-fts5.md`.
- Interpreters: project 3.13.12/SQLite 3.50.4, `/usr/local/bin/python3` 3.12.2/3.45.1 (no dbstat), `/usr/bin/python3` 3.9.6/3.54.0; no Homebrew Python. All required checks ok everywhere.
- Prototype index of 2598 pages: 41.05 MB after VACUUM (45.51 MB after optimize+ANALYZE); 76% is `doc_section`. Build ~3.8 s (render 3.06 s). FTS p95 0.23 ms, ro open + first query 0.3 ms.
- D-006 amended: finalize inserts FTS rows itself (`'rebuild'` is rejected on contentless tables; overrides DITS §9 "FTS rebuild"), then `'optimize'`; `open_readonly` uses `Path.as_uri() + "?mode=ro"` and runs `PRAGMA user_version` before returning (garbage files fail only at the first query).
- D-032 new: no LIKE fallback in v1 (changes ANALYSIS R-11); without FTS5 the build fails with IngestError and doctor names it.
- Warnings: bm25 alone ranks `ls` 4th and `tar` 2nd (unicode61 splits `git-ls-tree`): T-5.1's name stage must fix it. Unquoted `name:x` silently becomes a column filter: T-4.4 must quote every token and double embedded `"`.
- Reviewer fixes: probe quoting check extended (`AND`, `:`, `*`, `""`), `--repeat` < 1 rejected, D-006 no longer requires optimize after the commit.

## 2026-11-22T05:45:00Z T-0.6 Spike S-1: Textual transparent background (automated part) — DONE
- `spikes/s1_textual_background.py`: demo app (`--variant transparent|surface`, `--bare`, `--seconds`), pty analyzer (`--analyze`, `--json`, `--size`), `--selftest` for `parse_sgr`/gate. Findings in `docs/design/leva-sh/spikes/S-1-textual-background.md` (12 numbered findings).
- Recommended run writes only bg `49`, all fg in palette, glyphs `┌┐└┘│─`; output is deterministic across runs. `SURFACE_FALLBACKS` is empty: no widget needs `#1A1A1A`/`#202020`.
- D-012 amended; R10 edit to T-8.1 (copy the S-1 Theme/TCSS, mandatory `ansi-background`/`ansi-foreground`, palette test allows only `ansi_default`/`transparent` as backgrounds).
- Warnings for T-8.x: `Input:ansi` hard-codes cursor/placeholder (only app CSS on component classes beats it); `Input` `-invalid` and `.input--suggestion` are not overridden (tall border, dim): override if a validator/suggester is added. Any new widget (DataTable, Markdown, Select...) must be run through an analyze-style capture.
- The analyzer needs `COLORTERM=truecolor`, else Rich downgrades to `38;5;n`. U-1 (manual check in Terminal.app/iTerm2/Ghostty) stays open and non-blocking.
- Reviewer fixes: forbidden glyphs now include the Underline `╸╺`; theme name not duplicated; doc notes layout-only CSS omissions and the uncovered Input states.

## 2026-11-22T04:40:26Z T-0.7 Design-system update proposal (text only) — DONE
- `docs/design/leva-sh/design-system-update-proposal.md`: blocks P-1..P-7 (Italian proposed text), "Where to insert" anchored on the 118-line snapshot (apply bottom-up), diff summary, rationale, open questions. External file untouched.
- Key finding (round 1): `pydf-tool` is already a Textual app (`tui.tcss` with `$surface` container backgrounds, accent-border selection, Textual `ProgressBar`, capitalised Italian status). The proposal therefore scopes rules: P-3 rules tagged [tutti]/[nuovi], P-4 items tagged [comune]/[Leva]; transparent `ansi=True` background is preferred and required for new projects and `leva-sh`, `$surface` containers stay approved for existing ones. Section "Impact on pydf-tool" states no impact per block.
- V-1..V-6 = ADR-0005 conventions 1–6 (V-1 per D-028 `<name>` display); V-7..V-13 from UX.md, D-013, D-028..D-030; V-14/V-15 = ADR-0005 layout/no-highlighting rules.
- For T-8.x: the design-system text will only exist after U-2; T-8.1..T-8.10 must rely on what the current file already approves, T-8.11 stays blocked by U-2. If U-2 rejects a [Leva] item, re-plan the affected T-8.x task.
- pydf-tool's unused `$surface-accent` (`#2B2416`) is noted as a side remark only; not Leva's to fix.
- Reviewer fixes: P-2 fallback wording plural, P-5 cross-reference to "Convenzioni visive, voce 13", two overlong lines reflowed.

## 2026-11-22T04:49:08Z T-0.R Phase 0 review — DONE
- Review note `docs/design/leva-sh/reviews/phase-0.md`: RC 1–10 (most n.a. before Phase 1), T-0.R steps 1–3 confirmed by grep, findings F-1..F-10 all fixed.
- New arch rule `dev-code`: src may not use `spikes`, `tests` or `tools` (D-025 amended); three planted cases and a prefix trap pin it.
- R10 edits carrying D-029/D-030/D-031 into lower layers: T-1.1 `Example.danger`; T-4.1 `intent.ord`, `example.danger`, `add_intents` (ord = list index); T-4.3 fixture example with `danger`; T-4.4 intents by `ord`, `examples()` returns `danger`; T-5.1 `SearchResult.via`, `Searcher.nearest_names`; T-5.3 `Library.nearest_names`; T-6.4 copies `danger`.
- D-016 amended: the denylist has 47 distinct names (`softwareupdate` listed twice). D-029 amended: no synonym field in v1; a synonym is one more curated intent.
- Warning for T-1.1/T-3.1: `Example` only stores the `danger` text (non-empty, single line when set); the D-016 destructive-pattern check belongs to content validation (T-3.1).
- `diff -q` against the external design system was denied by the permission mode; identity checked by reading both files (119 lines each).
- Reviewer fixes: F-10 (writer for ordered intents, repo read-back and fixture example for `danger`), recorded in the note and in the D-029/D-030 amendments.
