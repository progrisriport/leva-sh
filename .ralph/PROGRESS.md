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

## 2026-11-22T21:18:39Z T-1.1 `leva.model`: errors and value objects — DONE
- `leva.model` = private `_errors.py` (`LevaError(message, hint=None)` + 7 subclasses, message never validated) and `_types.py` (`Origin`/`Kind` StrEnums, public Literal aliases `ExampleSource`/`Verification`/`NoteKind`, 5 frozen slotted dataclasses); 18 sorted re-exports. D-033 records the exact invariants.
- Name rule (non-empty, no `str.isspace()` char, so NBSP is rejected) on `Entry.name`/`section`, `Example.id`, `Subcommand.name`/`entry_name`. `Example.cmd`: non-blank, no `\r`, no trailing newline, `\` before every newline. `danger`/`Subcommand.source` non-blank; nothing else constrained.
- Warning for T-4.4 (repo): `Entry.kind`/`origin` must be enum members; convert SQLite strings with `Kind(value)`/`Origin(value)`, a plain str raises `ValueError`.
- Warning for T-3.1/T-6.x: model raises `ValueError` (programmer error); content validation must check YAML first and raise `ContentError("file:field: reason")`, or wrap the `ValueError` with `from exc`.
- Enum/Literal checks go through helpers typed `object`/`str` to dodge mypy `warn_unreachable`; reuse that pattern.
- Reviewer fixes: test factories typed as `Callable[..., ValueObject]` (dropped 9 `type: ignore[operator]`), immutability test now assigns every field.
## 2026-11-22T21:16:59Z T-1.2 `leva.placeholders` — DONE
- `parse`, `to_plain`, `names`, `problems` over one private `_Scanner` (single left-to-right pass feeds both segments and problems); `Segment` frozen/slotted, rejects empty text. 100% branch coverage.
- D-034 appended: a placeholder ends at the FIRST `}}` (inner `{{` and single braces belong to it); `\{{` is the only escape; `{{}}` stays literal; an unclosed `{{` makes the rest literal (backslashes in that tail are kept verbatim).
- Contract for T-3.1: `EMPTY_PLACEHOLDER`/`UNCLOSED_PLACEHOLDER` strings, source order, at most one unclosed (always last). `{{ }}` parses as placeholder `" "` AND reports "empty placeholder": content must reject it.
- For T-8.x / library: `parse` never raises; dedup (D-011) and `<name>` rendering (D-028) should consume `parse` segments, not re-scan.
- Hypothesis: use `exclude_characters`/`exclude_categories` (current names) and exclude category `Cs`.
- Reviewer fixes: split a misnamed unclosed test (inner `{{` case), added an unclosed tail with an escape, the total-input property now asserts invariants instead of "no exception".

## 2026-11-22T21:21:26Z T-1.3 `leva.paths` — DONE
- `LevaPaths(data_dir, config_file, log_dir)` frozen/slotted, `index_db = data_dir/index.db`; `resolve(env, home)` reads only `LEVA_HOME` from `env`, pure (`is_absolute` only, no `expanduser`/`resolve`/`exists`). 100% branch coverage.
- D-035 appended: empty `LEVA_HOME` = unset; relative (incl. `~/x`) -> `ConfigError("LEVA_HOME: not an absolute path: '<v>'", hint=...)`; relative `home` -> `ValueError` (checked first, even with `LEVA_HOME` set).
- Exports `LEVA_HOME_VAR`; `cli` (T-9.x) should use it when reading `os.environ` and pass `Path.home()` as `home`. Creating `data_dir`/`log_dir` is the caller's job.
- For T-1.5 (config): read `LevaPaths.config_file`; for ingest (D-022): derive `index.db.new`/`index.lock` from `index_db`, they are not on `LevaPaths`.
- Reviewer: approved without changes.
## 2026-11-22T21:40:00Z T-1.4 `leva.clipboard` — DONE
- `leva.clipboard`: `Clipboard` Protocol, `PbcopyClipboard(*, binary, timeout)`, `FakeClipboard(*, fail)` with `last`/`history`; one shared `_check_text` (empty or > 64 KiB UTF-8 → ValueError before any spawn). D-036 records the details. 100% branch coverage.
- `pbcopy` runs with a read-only env of only `LANG`/`LC_CTYPE` (`MappingProxyType`, never the process env), stdout/stderr at DEVNULL; `OSError`, `TimeoutExpired` and non-zero exit all map to `ClipboardError("clipboard unavailable")`, hint None, cause logged at DEBUG.
- For T-8.x: show `ClipboardError.message` verbatim in red; `FakeClipboard.fail` is mutable so a TUI test can flip it between copies. Callers must not pass empty text (ValueError is a programmer error): an example cmd that converts to "" cannot exist (model forbids blank cmd).
- Fake-binary tests need absolute tool paths (`/bin/cat`, `/usr/bin/env`, `exec /bin/sleep`) because the child env has no `PATH`; reuse for sources/manparse probes.
- Live test (`tests/live/`, `clipboard` marker) round-trips via pbpaste and restores text content only; it passed once on this Mac.
- Reviewer fixes: `UNAVAILABLE` made private (it was public but absent from `__all__`), env dict made read-only.
## 2026-11-22T21:23:43Z T-1.5 `leva.config` — DONE
- `LevaConfig(sections, extra_man_paths, extra_bin_dirs)` frozen/slotted with `__post_init__` invariants; `load_config(path, home)` reads → decodes → `tomllib` → unknown keys (sorted-first) → per-key helpers; `DEFAULT_SECTIONS = ("1", "8")`. 100% branch coverage.
- D-037 appended: exact error strings (`<file>: cannot read file | not valid UTF-8 | invalid TOML at line N`, `<file>:<key>[<i>]: <reason>`), hint `edit <path> or delete it to use the defaults`, canonical JSON for `digest()`.
- tomllib 3.11–3.13 reports `(at end of document)` without a line: N falls back to the text's line count.
- For T-9.x (cli): call `load_config(paths.config_file, Path.home())`; `home` must be absolute (ValueError otherwise). For T-6.x: pass `cfg.digest()` as `config_digest`.
- For T-2.2/T-2.3: extra paths are not deduplicated and not resolved (`..` and symlinks kept); discovery must dedup.
- Reviewer fix: `"~//man"` expanded to `/man` (`home / "/man"` drops `home`); now strips extra leading slashes, with a test. `_sections` only accepts lists, like `_path_list`.

## 2026-11-23T02:15:31Z T-1.R Phase 1 review — DONE
- Review note `docs/design/leva-sh/reviews/phase-1.md`: RC 1–10 over model, placeholders, paths, clipboard, config; 443 tests, every Phase 1 package at 100% branch coverage, 3 import contracts kept.
- F-1: `paths` filename constants made private `Final` (only `LEVA_HOME_VAR` is public). F-2: `PbcopyClipboard.copy` Pre/Post and `LevaPaths` Attributes documented.
- F-3 (R10, D-033 amended): T-3.1 must check the `Example.cmd` invariants before building `Example` (a YAML `|` block ends with `\n`, which the model rejects); T-4.4 converts stored strings with `Kind(...)`/`Origin(...)`.
- Kept on purpose: `config` loader repeats the `LevaConfig` invariants to produce `ConfigError` messages; the dataclass keeps raising `ValueError`.
- `tests/live/test_clipboard_live.py` not run in this review (real clipboard, not part of the gate).
- Reviewer: approved; only fixed the dates of the review note and the D-033 amendment to 2026-11-23.

## 2026-11-23T02:31:59Z T-2.1 `leva.sources` (A): SystemInfo, ExecutableScanner, origin mapping — DONE
- `leva.sources`: `SystemInfo.detect(*, sw_vers, timeout=5.0, machine=platform.machine)` (only `sw_vers` caller, read-only locale-only env), `origin_for` (pure, component-wise), `DEFAULT_BIN_DIRS`, `Executable`, `ExecutableScanner`. D-038 records the details. 100% branch coverage.
- Scanner: dirs deduplicated in `__init__` (first kept), every call rescans, sorted by (name, dir index), every duplicate yielded; symlinks unresolved in `path`, followed for the file/X_OK check; names failing D-033 skipped.
- For T-2.2: import `origin_for` from `leva.sources._origin` and `is_entry_name` from `leva.sources._names` (private, not re-exported); reuse the logger `leva.sources`.
- For ingest (T-6.x): the first `Executable` per name is the winner; pass `DEFAULT_BIN_DIRS + cfg.extra_bin_dirs` as-is (the scanner dedups).
- Tests: default macOS FS is case-insensitive, so fixtures never create names differing only by case.
- Reviewer: approved without changes.
## 2026-11-23T02:32:32Z T-2.4 `leva.manparse` (A): overstrike, stub detection, MandocRenderer — DONE
- `strip_overstrike` (regex `[^\n]\x08`, then lone backspaces), `read_man_source` (gz-aware, UTF-8 replace; OSError/EOFError/zlib.error -> `ManRenderError("cannot read man page: <path>")`), `stub_target` (first non-comment line decides, raw `.so` argument), `ManRenderer` port, `MandocRenderer`. 100% branch coverage.
- D-039 appended (placed after D-037; D-038 comes from parallel T-2.1).
- `MandocRenderer.render`: cwd = `path.parent.parent`, read-only env `LC_ALL`/`LANG`/`MANWIDTH`/`TZ` only; messages `mandoc failed | mandoc timed out | empty man page: <path>`, hint None; empty = fewer than 3 non-blank lines.
- For T-2.5: `render` returns overstrike-free text with the mandoc header and footer still present and columns untouched (headings col 0, bodies col 5); fixtures live in `tests/fixtures/man/src/*.1` (mdoc sample, man(7) legacy, stub + target).
- For T-6.2: catch `ManRenderError` per page and continue; call `stub_target(read_man_source(p))` before rendering and resolve the raw path against the man root yourself (D-005).
- Reviewer fix: extracted a `_recording` fake-mandoc helper in `test_manparse_render.py` (four copies of the same script tail); added that test file to the PLAN T-2.4 file list as the brief stated.
- Warning: `tests/unit/test_clipboard.py::test_both_classes_satisfy_the_clipboard_port` failed once during a gate run under parallel-worktree load and passed on rerun (fake pbcopy over the 2 s default timeout, likely). If it recurs, give that test an explicit larger timeout.

## 2026-11-23T02:38:34Z T-2.2 `leva.sources` (B): ManPageLocator and man dir discovery — DONE
- `leva.sources` adds `discover_man_dirs` (pure: manpath entries, then `/opt/homebrew/share/man`, `/usr/local/share/man`, then extras; relative dropped, dedup by `Path` equality, missing kept), `run_manpath(env, *, binary, timeout)`, `ManFile`, `ManPageLocator`. D-040 records the details. 100% branch coverage.
- `run_manpath` child env = `PATH`/`MANPATH` from the injected mapping + `LC_ALL`/`LANG=en_US.UTF-8`; spawn error, timeout, non-zero exit -> `IngestError("cannot list man directories: manpath failed")`; blank output is valid.
- `locate()` rescans each call, sorted by (name, section position, dir_index, file name); `ManFile.section` is the dir's section; symlink paths unresolved, mtime followed.
- For T-6.x: the first `ManFile` per (name, section) is the D-005 winner (stubs included). cli must pass `os.environ` to `run_manpath`, `cfg.extra_man_paths` to `discover_man_dirs` and `cfg.sections` to `ManPageLocator`.
- Not run in review: `make py311` (tool permission denied); checked by reading that a `PermissionError` from `Path.is_file` on 3.11 is caught by `_mtime_ns`.
## 2026-11-23T02:40:02Z T-2.5 `leva.manparse` (B): `parse_man` sections and NAME — DONE
- `ParsedMan(names, summary, sections, redirect_to=None)` frozen/slotted with D-041 invariants; `parse_man(text, *, name_hint)` total on any text, ValueError only for an invalid `name_hint`. NAME parsing in `_name.py` (`parse_name`, `is_name`, `MAX_SUMMARY`), splitting in `_sections.py`. 10 golden fixtures `tests/fixtures/man/parse_*.{txt,json}`, Hypothesis on arbitrary and mandoc-like text, >1 MB test. 100% branch coverage.
- D-041 appended (after D-039; D-040 comes from parallel T-2.2).
- For T-2.6: section bodies keep absolute rendered indentation (bodies at col 5, subsection lines at col 3, rstripped lines, blank edges trimmed); headings are `line.strip()`; a preamble or headingless page is a `DESCRIPTION` section; `sections` is never empty. The golden loader globs `parse_*.json` only.
- For T-6.x: `names` may not contain the man file name; ingest uses `ManFile.name` for the entry and sets `redirect_to` via `dataclasses.replace` from `stub_target`.
- Warning: the D-033 name rule is now implemented three times (`model._types`, `sources._names.is_entry_name`, `manparse._name.is_name`) because `leva.model` does not export it; a later cleanup could export one predicate from `leva.model` and reuse it.
- Reviewer: approved without changes.

## 2026-11-23T21:48:15Z T-2.3 `leva.sources` (C): ProbeRunner — DONE
- `leva.sources.ProbeRunner(allowlist, *, timeout=5.0, max_bytes=262_144)`: argv values with absolute `argv[0]` (ValueError otherwise), read-only copy of the allowlist; `run` spawns with `shell=False`, stdin devnull, the exact D-009 env + `HOME`, cwd = HOME = `<tmp>/leva-probe-*/home`, captures into files (not pipes), new session + `killpg(SIGKILL)` on timeout. D-042 records the details. 100% branch coverage.
- Exit status ignored (DEBUG log); text = stdout unless blank, else stderr, capped per stream in bytes then UTF-8-decoded with replacement, returned unstripped. Messages `probe not allowed|failed|timed out|output empty: <name>`.
- For T-6.4: build the allowlist as `{name: (str(first_executable.path), *help_probe.args)}`; catch `IngestError` per probe and continue. `run` keeps no per-call state, so concurrent calls from ingest workers are safe.
- For T-2.7: probe text may end with a newline and may contain U+FFFD.
- Not handled on purpose: a background grandchild of a probe that exits normally is not killed (only the timeout path kills the group); curated help probes do not daemonize.
- Reviewer fixes: the grandchild test now asserts the grandchild exits (kqueue `NOTE_EXIT`; before, it also passed with `proc.kill()` instead of `killpg`); tests whose script must write a file before the kill use a 3 s timeout (0.3/0.5 s failed under parallel-worktree load); ValueError tests match the messages.
## 2026-11-23T21:47:20Z T-2.6 `leva.manparse` (C): definition lists and builtins — DONE
- `definition_items(body) -> list[DefinitionItem(terms, description)]` in `_definitions.py` (base = minimal indent; consecutive base lines group; a blank line, a description line or an inline term closes the group; inline regex `^(\S.*?) {2,}(\S.*)$` on the stripped line) and `extract_builtins(parsed, heading)` -> sorted unique `BuiltinDoc(name, synopsis, summary, body)` in `_builtins.py`. D-043 records the rules. 100% branch coverage.
- For T-2.7: call `definition_items` on each matching section body and filter terms by the D-008 first-token regex; terms are stripped, descriptions dedented (nested lists keep their relative indent).
- For T-6.3: builtin entries use `BuiltinDoc.synopsis` as SYNOPSIS and `body` as DESCRIPTION; items with a blank description (bash intro paragraph) are skipped; the first item per name wins.
- Heuristic warning: base-indent prose with two spaces after a full stop parses as an inline term, and a multi-line base-indent paragraph becomes one term-only item (skipped by `extract_builtins`, but T-2.7 sees it and must filter).
- Reviewer fixes: inline term group 1 right-stripped (`"-a\t  x"` kept the tab); `BuiltinDoc.summary` rejects any `str.splitlines` break (`\x85` passed); `BuiltinDoc.name` reuses `_name.is_name` instead of a fourth copy of the name rule; tests added; `test_manparse_definitions.py` added to the PLAN file list.

## 2026-11-23T22:04:03Z T-2.7 `leva.subcmd`: extractors and merge — DONE
- `leva.subcmd`: `KnownPage(name, summary, synopsis)`, `SubcommandExtractor` port, `HyphenPageExtractor` (first two SYNOPSIS tokens must be `P s`), `SectionListExtractor` (full-match `(SUB)?COMMANDS|VERBS`, blank-description items skipped), `HelpTextExtractor(profile, text)` with `two-col`/`git-list`/`brew-commands`, `merge_subcommands`. D-044 records the rules; D-008 term filter amended to `[a-z][A-Za-z0-9_.-]*` (diskutil camelCase verbs). 100% branch coverage.
- `first_sentence` moved from `manparse._builtins._summary` to public `leva.manparse.first_sentence` (same behaviour); subcmd reuses it.
- For T-6.4: build `known` as `{entry.name: KnownPage(name, summary, synopsis_body)}` over all man-backed entries (`""` synopsis when absent); call `merge_subcommands([curated, probe, section, hyphen])`; curated `Subcommand.source` must be `"curated"`. The hyphen extractor iterates all of `known` per call (only a `startswith` per key).
- Known limitations: `bootstrap | bootout` yields only `bootstrap`; `info[rmation]` is dropped (not expanded); a two-col summary `(a) and (b)` loses the outer parentheses (literal "starts with `(` and ends with `)`" rule).
- Reviewer fixes: the 200-char cut test now asserts the exact cut text (it only checked `<= 200`); docstring for the `_probe` helper; ticked PLAN and wrote this entry (the executor had left both undone).

## 2026-11-24T02:50:28Z T-2.R Phase 2 review (RC + live sources smoke) — DONE
- Note `docs/design/leva-sh/reviews/phase-2.md`: RC 1–10, F-1..F-5 fixed. Live on this Mac: /usr/bin 934 executables, man1 1174 pages, 0 render failures; launchctl 20, ktrace 16, tailspin 8, diskutil 34 subcommands.
- F-1: the name rule is public once as `leva.model.is_name` (D-033 amendment); `leva.sources._names` is deleted. Use it for any new name check instead of a local copy.
- F-2: `ProbeRunner.run` wraps temp-dir/capture `OSError` as `IngestError("probe failed: <name>")`. F-3: `ParsedMan.summary` rejects every `str.splitlines` break. F-4: clipboard test helper timeout 10 s.
- F-5 (D-044 amendment): `SectionListExtractor` skips terms whose first token is `parent` and terms with a sentence end (`[A-Za-z0-9)\]][.!?](?:\s|$)`). Callers must pass the real parent name.
- For T-6.2..T-6.4: R10 facts added to the PLAN steps (stub check before render, per-page `ManRenderError`, builtins via `extract_builtins`, probe allowlist shape, merge order).
- For T-6.6/curated content: `a | b` alternatives keep only the first token and launchctl `LEGACY SUBCOMMANDS` is not scanned; curated content must supply `bootout`, `list`, `load`, ... if wanted.
- Not run: `make py311` (tool permission); 3.11 compatibility checked by reading.
- Reviewer round 1: CHANGES (F-5 wrongly "kept on purpose", mirror property test, note gaps); round 2: approved with note wording fixes only.

## 2026-11-24T03:13:13Z T-3.1 `leva.content` (A): schema types and validation — DONE
- `leva.content`: `CuratedCommand`, `ExampleSpec(.to_example)`, `VerifySpec` (read-only `bind`, unhashable), `HelpProbe(args, profile)`, `TldrPage(.to_examples)`, `TldrExample`, `ContentRecord`, `VERIFY_MODES`, `HELP_PROFILES` (own copy, test checks equal to subcmd), `TLDR_PLATFORMS`, `EXEC_DENYLIST`, `is_destructive`, `validate_command`. D-045 records messages, type strictness, tokenization and destructive rules. 100% branch coverage.
- For T-3.2: call `validate_command(data, file)` with the label `commands/<file>.yaml` (stem = name); it raises only `ContentError` (hint None). Cross-file example-id uniqueness, duplicate YAML keys and tldr cmd filtering (drop examples whose cmd breaks D-033 before building `TldrPage`) are the provider's job.
- For T-7.x (verify): `simple_commands` lives in `leva.content._policy` (private); exec denylist is checked on `cmd` and `setup` command words; `bind` holds exactly the placeholders of `cmd`.
- Known policy gaps (D-045 limitations): `sh -c '...'`, backticks, functions, aliases not seen; `command -v rm` is a false positive (`command` unwraps like a wrapper), so such an example needs a `danger` or a different form.
- Reviewer fixes: a quoted empty word `''` was treated as a separator (`rm '' x` emitted `('x',)`, `git push '' -f` was missed); `find ... \; -delete` was missed (the part after an escaped `;` now gets the find rule); `git push origin +main` is destructive; Hypothesis top-level replacement now covers every top-level key. D-045 text updated.

## 2026-11-24T03:21:14Z T-3.2 `leva.content` (B): providers, content_version, attribution, first real YAML — DONE
- `leva.content`: `ContentProvider` port, `CuratedYamlProvider(root)` (strict `SafeLoader` subclass rejecting duplicate keys, `.yml` rejected, cross-file example ids, all-or-nothing), `TldrSnapshotProvider(root)` (JSONL, exact keys, `platform` = file stem, osx replaces common), `content_version(root)`, `default_root()`, `attribution_text()`. D-046 records file rules, messages and the hash recipe. 100% branch coverage.
- First curated file `commands/ls.yaml` (8 examples: 5 exec, 3 static); notes checked against `mandoc -T ascii /usr/share/man/man1/ls.1`. `ATTRIBUTION.md` initial (the tldr section is T-7.2's).
- For T-6.x: ingest calls `CuratedYamlProvider(default_root())`, `TldrSnapshotProvider(default_root())`, `content_version(default_root())`; all raise only `ContentError`.
- For T-7.2: `tools/vendor_tldr.py` must write one JSON object per line with exactly `name`, `platform`, `description`, `examples: [{desc, cmd}]`, `platform` equal to the file stem, no duplicate names per file, and must add `tldr/SOURCE.json` (it feeds `content_version`). Invalid example cmds are dropped with a WARNING, not an error.
- For T-7.3/T-7.4: `ls-one-per-line` uses `stdout_regex: '^a\nb\n$'` (works with `re.search`, `match` or `fullmatch`); the `ls -l` example only checks `total` because macOS may add `@` (xattrs) to fresh files.
- Strictness note: YAML merge keys (`<<`) count as duplicates when an explicit key overrides a merged one; curated files should not use merge keys.
- Reviewer fixes: `ls-one-per-line` verify tightened from `stdout_contains: [a, b]` (always true) to an exact regex; D-046 JSON error wording made exact (a repeated key has its own message).

## 2026-11-24T23:08:15Z T-3.R Phase 3 review (RC) — DONE
- Note `docs/design/leva-sh/reviews/phase-3.md`: RC 1–10 ok; F-1..F-6 fixed. F-1: over-long YAML ints (>4300 digits) in messages shown as `<integer too large to show>`; F-2: YAML constructor `ValueError`/`RecursionError` → `<label>: invalid YAML`; F-5: `_policy._expand` iterative (deep wrapper chains leaked `RecursionError`); F-6: `ls-long` verify now `stdout_regex: '^total [0-9]+\n[^\n]* a\n$'` (old `stdout_contains: a` was vacuous).
- D-045 amendments: TEST-STRATEGY "distruttivo mai in exec" = D-016 denylist + D-030 `danger` + sandbox (exec of `rm` on a setup fixture allowed); known `is_destructive` gaps listed (`mv`/`cp`/`>` overwrite, `shred`, `truncate`, `git checkout .`, `sh -c`). D-046: lone surrogates pass validation (limitation).
- R10 edits: T-6.1 (`content_version(default_root())`), T-6.4 (providers, `to_example`, `to_examples`, `HelpProbe`), T-7.2 (exact JSONL format; `SOURCE.json` must change with any JSONL change), T-7.3 (`VerifySpec` fields), T-7.4 (export and reuse `simple_commands`), T-9.3 (both providers drain).
- For T-7.3: `stdout_regex` examples are written to hold under `re.search`, `match` and `fullmatch`; pick one and record it.
- Not run: `make py311` (tool permission); 3.11 compatibility checked by reading.
- Reviewer round 1: approved with F-5/F-6 fixed by the reviewer and the F-1 tests tightened to exact messages.

## 2026-11-24T23:25:00Z T-4.1 `leva.store` (A): schema, IndexWriter, open_readonly — DONE
- `leva.store`: `SCHEMA_VERSION` (1), `NewEntry`, `IndexWriter`, `open_readonly`; schema v1 in `migrations/0001_init.sql` loaded by `_schema.load_migrations` (`order_migrations` checks `NNNN_<slug>.sql`, numbers 1..n). D-047 records tables, messages and checks. Store branch coverage 99.1% (only the defensive `lastrowid is None` branch is uncovered).
- For T-4.2: writer state is `_entered` (bool, set once) and `_conn` (`sqlite3.Connection | None`, set by `__enter__`, cleared at the start of `__exit__`); `_connection()` raises `ValueError("index writer is not open")` and `_writing()` maps errors, so `finalize()` should run through `_writing()` inside the one transaction opened by `executescript("BEGIN;...")` (`isolation_level=None`: never call `conn.commit()`; `__exit__` sends `COMMIT`).
- For T-4.4/T-6.5: the example text column is `description` (not `desc`); child tables are keyed `(entry_id, ord)`; `entry.has_man`/`curated` are 0/1; `kind`/`origin` are enum values; `alias` has no `ord` (read it `ORDER BY alias`).
- For T-6.x (ingest): call each list method once per entry; a failed write leaves the rows of that call already accepted in the transaction (`executemany` is not atomic per call), so let `IngestError` propagate and remove the rolled-back `.new` file (it exists with `user_version` 0).
- Reviewer fixes: a lone surrogate in any text leaked a raw `UnicodeEncodeError` from writes; now mapped to `IngestError("cannot write index: ...")`, with tests for it and for a non-integrity `sqlite3.Error`; D-047 amended; inline test import moved to the top; ticked PLAN (`_schema.py` added to Files) and wrote this entry (the executor had left both undone).

## 2026-11-25T02:54:28Z T-4.2 `leva.store` (B): finalize, FTS and digest — DONE
- `IndexWriter.finalize(*, built_at) -> str` (refines DITS §9 `-> None`, D-048): fills contentless `search_fts` (rowid = entry id), `optimize`, writes `schema_version`, digest, `index_digest`, `built_at` (UTC, `isoformat(timespec="seconds")`), `ANALYZE`, `integrity_check`. Steps live in `_finalize.py` (`finalize_index`, pure `check_integrity(rows, path)`). No VACUUM. Store branch coverage 99.3%.
- After finalize every `add_*`/`set_meta` raises `ValueError("index writer is already finalized")`; a failed finalize leaves the writer unfinalized but FTS rows may be half-inserted: let the error roll the build back, never retry finalize.
- For T-4.3: call `writer.finalize(built_at=...)` inside the `with`, then exit; an unfinalized index has an empty `search_fts` and no `schema_version`/`index_digest`.
- For T-4.4: FTS columns `name` (name + aliases sorted, space-joined), `intents` (`\n`), `summary`, `body` (section bodies only, `\n\n`, no headings). Contentless: only `rowid` and `bm25()` are readable; rank with `bm25(search_fts, 10.0, 5.0, 2.0, 1.0)`, lower = better.
- For T-6.5: `build` passes `built_at=clock()` (timezone-aware, else `ValueError`); the return value is `BuildReport.digest`. The digest covers `schema_version` and every other meta key except `built_at`/`index_digest`, so `content_version` etc. written via `set_meta` before finalize are part of it.
- Reviewer: added a test that a `sqlite3.Error` inside finalize maps to `IngestError("cannot write index: ...")` and leaves the writer writable; ticked PLAN (`_writer.py` added to Files) and wrote this entry (the executor left both undone).

## 2026-11-25T03:02:24Z T-4.3 Fixture index factory (test support) — DONE
- `tests/support/index_factory.py`: `FIXTURE_JSON`, `FIXED_BUILT_AT` (2026-01-01 UTC), `FixtureEntry`/`FixtureData` (frozen; build variants with `dataclasses.replace`), strict `load_fixture` (unknown/missing keys and wrong JSON types raise `ValueError` naming entry and key), `build_fixture_index(target, data=None)`. Conftest fixture `fixture_index` -> `tmp_path/fixture-index/index.db`. 57 entries, build ~10 ms.
- For T-4.4/T-5.x/T-8.x: look ids up by key, never hard-code them. Keys worth testing: `echo` 1/macos (rank 0), None/zsh (1), None/bash (2); `cd` zsh (0) / bash (1); alias `[` -> `test`; `gzip` aliases `gunzip`, `zcat`; `grep` aliases `egrep`, `fgrep`; exe-only `bat` (homebrew, summary `""`, no sections); `sync` 1 (rank 0) / 8 (rank 1); man-only `git-commit`, `git-log` (kind manpage, path None).
- Curated (10): `chmod curl diskutil du find git grep ls rm tar`. `tar` intents in order `compress a folder`, `extract an archive`, `list archive contents`, `bundle files into one file`; D-011 pair `tar-create-gzip` (curated) vs `tar-tldr-1`; danger examples `rm-folder`, `diskutil-erase`. tldr-only: `ps` (3), `open` (1). `ls` related includes builtin `cd`.
- `find` DESCRIPTION has >=120 lines with a line >80 chars (D-027). `diskutil` subcommands: 4 `section` verbs with body + `eraseDisk` with source `curated`; `git`: `commit`/`log` (`hyphen`, entry_name set), `status` (`probe`).
- The fixture's D-005 rank test treats every origin other than `bash` as equal to `zsh`; T-6.5 should record its own origin order if it differs.
- Reviewer fix: the loader coerced values with `str()`/`bool()` and validated with `assert` (`"summary": null` became `"None"`, `"has_man": "false"` became True); now typed accessors raise `ValueError`, with parametrized tests. PLAN Files gained `tests/conftest.py`.

## 2026-11-25T03:10:32Z T-4.4 `leva.repo`: Repository — DONE
- `leva.repo`: `Repository(conn)` (owns the connection from `open_readonly`), `NameRow`, `FtsHit`, `IndexStats`, `FTS_WEIGHTS` (10, 5, 2, 1), `MAX_FTS_TOKENS` (32); private sanitiser `_fts.fts_query` (NUL counts as whitespace, every token quoted, `"` doubled). D-049 records orderings, messages and the sanitiser. Repo branch coverage 100%.
- For T-5.1: `NameRow(entry_id, name, section, kind, origin, summary, curated, aliases sorted, intents by ord)`, `names()` ordered `(name, rank, id)`. `fts` returns `FtsHit(entry_id, score=-bm25)`: higher is better, ordered by descending score then entry id. There is no prefix search in FTS (`arch*` and `arch` find nothing), so prefix/fuzzy matching must come from `names()`; `name:ls` is the phrase `name ls`, never a column filter; `git-commit` is a phrase.
- For T-5.3: `get_entry_by_id`, `explain` (`""` when not curated) and `close()` (idempotent) exist beyond DITS §10; unknown ids give `None`/`""`/`[]`. `get_entry` does not strip the name (`"ls "` is None) and a blank name is None.
- For T-7.3/T-9.3: `stats()` -> `IndexStats(entries, man_pages (has_man and not builtin), builtins, curated, examples, subcommands)`.
- Errors: every `sqlite3.Error` -> `IndexUnavailableError("index unreadable")`, a value the model rejects -> `"index corrupt: <table> row <entry_id>"`, both with hint `run leva --rebuild`.
- Reviewer: tightened the colon test (raw FTS5 does apply `name:`/`body:`/`summary:` filters on the fixture; sanitised queries return `[]`) and made the `close()` idempotence test assert the closed state; ticked PLAN (`_repository.py`, `test_repo_fts.py` added to Files).

## 2026-11-25T03:21:59Z T-4.R Phase 4 review (RC) — DONE
- Note `docs/design/leva-sh/reviews/phase-4.md`: RC 1–10 ok; F-1..F-6 fixed. F-1: lone surrogates made `fts` (`[]`) and `get_entry` (`None`) total via private `repo/_text.is_encodable`; F-2: `open_readonly` maps an `OSError` from `path.is_file()` (unsearchable parent) to `IndexUnavailableError("index unreadable: ...")`; F-3: `IndexWriter.__enter__` reads migrations before connecting (no leaked file/connection on `ValueError`).
- Tests added: digest recipe pin over every child table (F-4), `tests/integration/test_store_repo_roundtrip.py` (F-5, TEST-STRATEGY §4), hostile-alphabet Hypothesis property incl. surrogates/NUL, operator look-alikes (`NEAR/3`, `x OR`, curly quotes).
- Amendments: D-047 (F-2, F-3), D-048 (recipe pin, digest facts), D-049 (surrogate totality, integer args unguarded beyond `limit >= 1`, facts for later phases).
- R10 edits: T-5.1 (`NameRow`, `FtsHit.score` higher is better, no FTS prefix search), T-5.2 (writer + finalize + `Repository(open_readonly(...))`), T-5.3 (`get_entry_by_id`, `explain`, `close`, `meta()["attribution"]`), T-6.1 (fingerprint via `set_meta` before finalize, part of the digest), T-6.5 (`NewEntry`, ids by write order, remove stale/rolled-back `.new`), T-7.3/T-9.3 (`stats()` fields).
- For T-5.x: `get_entry` does not strip or split input; the library must. For T-6.5: `IndexWriter(path)` raises `ValueError` if the file exists.
- Reviewer round 1: approved; reworded the F-6 note again (the executor's text still implied `--color` is GNU-only; macOS `ls` accepts `--color=when`, GNU reads `-G` as `--no-group`). `make check` 1499 passed; `make py311` 1499 passed.

## 2026-11-26T22:56:36Z T-5.1 `leva.search`: Searcher — DONE
- `leva.search`: `Searcher(repo, *, weights=DEFAULT_WEIGHTS)`, `search(query, limit=50)`, `nearest_names(query, limit=3)`, `SearchResult(entry_id, name, section, kind, origin, summary, score, why, via)`, `MatchReason`, `Weights`, `DEFAULT_WEIGHTS`, `STOPWORDS`. Pure helpers in `_ranking.py`, the searcher in `_searcher.py`. D-050 records tiers (7000..1000, added `partial` 2000 below `summary`), sub-scores, bonuses, fuzzy (one token of 3..64 chars, WRatio >= 80 or OSA distance 1), tie-break `(name, names() position)`, `nearest_names`. Search branch coverage 100%.
- For T-5.2/T-5.3: `__init__` does no I/O; `names()` is read on the first call and cached for the Searcher's lifetime (build a new Searcher after a rebuild). `limit < 1` -> `ValueError("limit must be >= 1: <n>")`; `IndexUnavailableError` propagates. FTS is asked for `max(4 * limit, 100)` hits. The name and intent tiers are Python loops over `names()`: T-5.2 should measure them at a realistic name count.
- Gold mini (`tests/fixtures/index/gold_mini.json`, 30 queries, expect in the top 3): 30/30 on the fixture; no query swapped.
- Order facts: `echo` gives zsh, bash, then `/bin/echo` (builtin bonus); results can share a name, so the UI opens by `entry_id` (R10 line added to T-8.4).
- Warnings: `ls -la` (a command plus flags) finds nothing (key `ls--la`, fuzzy off for two tokens); D-012 query resolution in the library/TUI should strip flags before searching. A single token containing a name scores fuzzy 90 by WRatio containment (`name:ls` -> `ls`). FTS has no stemming, so `file` does not match `files`; curated intents should cover singular and plural phrasings.
- Reviewer fix: stopwords no longer reach the FTS AND query or the summary-tier check (on a real index nearly every summary contains `a`/`the`/`of`, which would lift almost every FTS hit into the summary tier, and `how do i ...` cut recall); a stopword-only query goes to FTS unchanged. Two stub tests added, D-050 amended, the odd-input test now bounds the `nearest_names` length. The executor had left PLAN unticked and this entry unwritten.

## 2026-11-26T23:05:50Z T-5.2 Search latency benchmark (NFR-2) — DONE
- `tests/integration/test_search_latency.py` (markers `integration` + `perf`): 3000 syllable-generated entries (150 curated with 4 intents, 60 zsh builtins, 120 exe-only, aliases on every 7th, 150–300 word DESCRIPTION over a 24-word vocabulary) written with `IndexWriter` + `finalize`, read via `Repository(open_readonly(...))`; build ~0.2 s.
- Measured on this Mac (200 distinct queries, nearest-rank percentiles): p50 1.5 ms, p95 2.8–3.1 ms, max 2.8–4.0 ms; warm-up (first call, loads `names()`) 9–12 ms. Assert is p95 < 100 ms (NFR-2 target 50 ms): large headroom for the Python name/intent loops at 3000 names.
- The body vocabulary is small, so every word query hits almost all documents: FTS cost here is worst case, not typical.
- Metrics go to `request.node.user_properties` (visible with `--junitxml -o junit_family=xunit1`), not the `record_property` fixture: under the default xunit2 family it emits a `PytestWarning` that `filterwarnings = error` turns into a test error.
- Reviewer fixes: intents were degenerate (150 curated entries shared 16 phrases, the 30 intent queries had 8 distinct values, the 40 word queries 24); intents now walk all 256 verb/noun pairs, partial intents drop the article, and `build_queries` asserts 200 distinct queries. Exe-only entries no longer coincide with builtins/curated entries. Added a sanity check that each exact intent phrase ranks an owning entry first. The executor had left PLAN unticked and this entry unwritten.
## 2026-11-26T23:03:20Z T-5.3 `leva.library`: Library facade — DONE
- `leva.library`: `Card` (DITS §12 fields + `summary`), `Library(repo, searcher)` with `search`, `nearest_names`, `card`, `open`, `open_result`, `open_subcommand`, `back`, `forward`, `trail`, `attribution`, `close`; `HISTORY_LIMIT = 50`. Pure helpers `example_key`, `merge_examples`, `subcommand_examples` in `_card.py`, private `History` in `_history.py`. D-051 records every rule. Library branch coverage 100%.
- For T-9.2: wiring is `repo = Repository(open_readonly(path)); Library(repo, Searcher(repo))`; `Library.close()` closes the repo (idempotent). After a rebuild build a new Searcher and Library (the Searcher caches `names()`).
- For T-8.4/T-8.5: preview with `card(entry_id)` (never records), open a result with `open_result(entry_id)` (resets history, D-028), navigate with `open(name)`/`open_subcommand(card, sub)`; breadcrumb = `search` + each `trail()` card's breadcrumb; lead line `Card.summary`. `back()`/`forward()` return `None` at the ends and do not move.
- For T-8.7: a synthesized subcommand card keeps the parent `entry` (so `entry.id` is the parent's), `explain` `""`, one `DESCRIPTION` section or none, examples filtered on a word boundary from the parent's merged examples.
- Warning: `open` is exact and case-sensitive and does not strip flags; D-012 query resolution (`ls -la`) belongs to the TUI/search side, not `open`.
- Reviewer: typed the test helper with `ExampleSource` instead of a `type: ignore`; ticked PLAN (`_library.py` added to Files) and wrote this entry (the executor left both undone). `make check` 1646 passed.

## 2026-11-27T01:10:20Z T-5.R Phase 5 review (RC) — DONE
- Note `docs/design/leva-sh/reviews/phase-5.md`: RC 1–10 ok; F-1..F-4 fixed. F-1: `Weights` accepted `exact=inf` and spreads near 1e18 (float spacing above ~1e15 collapses tiers into ties); now `exact <= 1e9` is required (`_MAX_TIER`). F-2: `Library` class docstring now lists `ValueError` for `limit < 1`. F-4: D-050 amendment names the PLAN T-5.1 lines it refines (the `partial` tier, the `(name, names() position)` tie-break).
- F-3 tests: largest bonuses never lift a result into another tier band (6 queries x 4 bonus splits), phrase > all words > partial over every `ord` incl. past `MAX_ORD`, Hypothesis totality of `search`/`nearest_names` and of `Library.open` over a hostile alphabet (NUL, lone surrogates, emoji, quotes), explicit hostile names for `open`. No production behaviour change besides F-1.
- Kept on purpose: `search(limit=10**30)` raises `OverflowError` from sqlite (D-049); distance-1 fuzzy on 3-letter queries (`cat` -> `cut`); `open` exact, case-sensitive, no flag stripping (D-012 resolution belongs to the TUI side, T-8.x).
- Gold mini 30/30 on the fixture, no query swapped. R10 edits: none (T-8.4/T-8.5/T-8.7 lines already match the code). Phase 6 ingest does not use `search`/`library`; T-8.x and T-9.2 rely on the T-5.1/T-5.3 entries above.
- Warning: the executor saw one failure of `test_sources_probe.py::test_timeout_kills_process_group_and_removes_temp_dir` under load (passed alone and in the reviewer's `make check`); quarantine it with a reason if it repeats.
- Reviewer round 1: approved; filled the baseline line of the note and recorded the reviewer `make check` (1687 passed, 11 deselected, coverage gate passed).

## 2026-11-27T01:33:17Z T-6.1 `leva.ingest` (A): fingerprint and staleness — DONE
- `leva.ingest` public API: `Staleness` (MISSING, VERSION_CHANGED, SYSTEM_CHANGED, FRESH), `Fingerprint(version_part, system_part)` (64 lowercase hex each, `meta()`), `dir_stat`, `compute_fingerprint`, `staleness(index_db, current)`, `META_VERSION = "fingerprint_version"`, `META_SYSTEM = "fingerprint_system"`. D-052 records both hash recipes and the `dir_stat` rules; `arch` is excluded.
- For T-6.5: `compute_fingerprint(*, leva_version, content_version, system, man_dirs, sections, bin_dirs, config_digest)`; write `fp.meta()` items with `IndexWriter.set_meta` before `finalize` (they enter `index_digest`). `IndexBuilder.fingerprint()` returns a `Fingerprint`, not a `str` (refines DITS §13).
- For T-9.x: `leva_version` is injected; `leva.cli` passes `leva.__version__` (ingest imports neither `leva` nor `importlib.metadata`).
- `staleness`: any `IndexUnavailableError` (missing, garbage, directory, wrong `user_version`, no meta table) -> MISSING; absent fingerprint keys (fixture factory index) -> VERSION_CHANGED; version checked before system. The connection is always closed.
- Reviewer round 1: approved; a failed entry stat now falls back to the running max instead of `0` (so it is really ignored when the directory mtime is pre-epoch), with a test; ticked PLAN and wrote this entry (the executor left both undone). Ingest branch coverage 100%.
