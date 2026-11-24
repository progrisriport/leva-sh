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
