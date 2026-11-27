# PLAN.md — Leva v1 (encyclopedia), autonomous build

## 1. Goal of this run
Build Leva v1 as specified in `docs/design/leva-sh/` (PRD, ARCHITECTURE, DESIGN-PATTERNS, DESIGN-IN-THE-SMALL (DITS), TEST-STRATEGY, ADR-0001..0006, ANALYSIS) plus `docs/design/leva-sh/DECISIONS.md`. Scope:
- local man ingest into an SQLite+FTS5 index;
- curated YAML + tldr content, with automatically verified examples;
- search, card, manual, subcommands, copy;
- Textual TUI that follows the Flosh design system;
- `leva <query>`, `--rebuild`, `--about`, `--version`, `doctor`.

Out of scope: PyPI publish, brew tap, making the repo public, CI runs that consume Actions minutes, and any change to the system or to files outside this repo.

## 2. Definition of done (whole run)
1. Every task not tagged `[USER]` is `[x]`. The only exceptions are tasks whose `Blocked-by` names an open `[USER]` task; T-FINAL lists those.
2. T-FINAL passes on this Mac: `make check`, `make live`, packaging checks, Python 3.11 test run, and smoke runs of `leva --help`, `--version`, `doctor`.
3. PRD metrics are met:
 - ≥150 curated commands;
 - curated examples verified exec or static ≥85%, exec ≥60%, skip <15%;
 - live gold set ≥90% in the top 3;
 - 100% of executables in /bin, /sbin, /usr/bin, /usr/sbin have an entry;
 - ≥95% of man-backed entries have a summary;
 - first build ≤30 s, index ≤100 MB, wheel ≤15 MB.
4. There are no TODO/FIXME/XXX markers, no `NotImplementedError` and no placeholder bodies. Every `# type: ignore[...]` or `# noqa: ...` carries a code and a one-line reason.

## 3. Global rules for every iteration (MANDATORY)
Repo conventions live in `CLAUDE.md` (auto-loaded once T-0.1 is done). Design refinements are binding in `docs/design/leva-sh/DECISIONS.md`; until T-0.1 seeds it, Appendix A below is binding.

**R1 Select the task.** Take the first task in document order that meets all of these:
- it is `- [ ]`;
- it is not tagged `[USER]`;
- every ID in its `Blocked-by:` line is `[x]`;
- it does not depend (via `Blocked-by:` or an obvious prerequisite) on a task marked `[!]`.

Tasks marked `[!]` are blocked (see R7) and are skipped, together with anything depending on them; the loop continues with the next independent task. Then:
- If nothing is selectable, print `RALPH_STATUS: NOTHING_TO_DO`, or `RALPH_STATUS: WAITING_FOR_USER <ids>` if open `[USER]` tasks block the rest, and stop.
- Do exactly ONE task per iteration.

**R2 Read before coding.** Read `CLAUDE.md`, this file's sections 3 and 4, `DECISIONS.md`, the task's `Refs`, and the code the task touches.

**R3 Start green.** Run `make check`; if it is not yet available, run the task's own checks. If the tree is red before you start, first repair it in a separate commit `repair: <what>`, then do the task.

**R4 TDD.** Write or extend tests first and run them to see them fail. Then implement the minimum and refactor. Tests must assert behaviour, including negative and edge cases from TEST-STRATEGY §2–3. A test that only checks "no exception" is not acceptable.

**R5 Done means:**
- every `Accept` command passes;
- `make check` passes;
- `ruff format .` has been applied;
- docs are updated: DECISIONS.md gets an entry for any intentional refinement, and design docs are never silently contradicted;
- this task's box is ticked `[x]` in the SAME commit;
- commit message first line is `T-x.y: <title>`, the body lists the tests and commands run, and there are no other trailers;
- then `git push origin HEAD:main`. If the push fails twice, note it in the output and continue.

**R6 Splitting.** If a task cannot be finished within one iteration:
- finish a coherent, green part;
- replace the task line with sub-tasks `T-x.y.1` (ticked) and `T-x.y.2` (open), with the same field format;
- commit.

**R7 Blocked.** If the task cannot be completed without a human decision, or is stuck on an external failure:
- do NOT tick it; change `[ ]` to `[!]`;
- add an indented line `- BLOCKED <date>: <reason>; options: ...`;
- insert a `[USER]` task `U-n` right after it;
- commit docs-only and print `RALPH_STATUS: BLOCKED T-x.y`.

**R8 Safety (never violate):**
- no `sudo`; never modify files outside this repo or the system temp dir;
- never edit `/Users/flosh/Desktop/Coding.nosync/Progetti/PyDF Tool/CLAUDE.md`;
- never touch the real `~/Library/Application Support/leva` or `~/Library/Logs/leva` (any manual run uses `LEVA_HOME=$(mktemp -d)`);
- never run curated example commands except through `leva.verify`;
- no installs outside `uv` into the project env; no brew installs;
- network only for `uv lock/sync/add` and the explicit vendoring task;
- no force-push or history rewrite; never change the repo's visibility or remotes;
- no PyPI or brew publishing.

**R9 Output.** The last line is always `RALPH_STATUS: DONE T-x.y`, `BLOCKED ...`, `NOTHING_TO_DO`, or `WAITING_FOR_USER ...`.

**R10 Later tasks.** Do not edit future tasks except:
- when a spike, or a decision recorded in DECISIONS.md, changes a fact they rely on (log it in DECISIONS.md);
- R6 splits.

## 4. Shared definitions
- **Gate commands** (Makefile, created in T-0.2/T-0.3):
- `make check` = `uv lock --check` + `ruff check .` + `ruff format --check .` + `mypy` (strict on src+tools) + `lint-imports` + `pytest` (non-live, with coverage) + `tools/coverage_gate.py`;
- `make live` = `pytest -m macos_live`;
- `make verify CMD=<name>` = headless rebuild into `.cache/leva`, then `uv run python -m leva.verify --index .cache/leva/index.db --command <name>`.
- **Coverage gates** (D-019), branch coverage:
- ≥90% for `placeholders`, `content`, `manparse`, `store`, `repo`, `search`, `ingest`;
- ≥70% for `tui`;
- ≥85% for every other package and overall.
- **Review checklist RC** (used by every T-x.R):
1. public API matches DITS + DECISIONS;
2. module docstring states the single responsibility; public items are documented, with pre/post conditions where DITS gives them;
3. only `LevaError` subclasses cross package boundaries, and third-party errors are wrapped with `from exc`;
4. no global mutable state, and env/clock/paths are injected;
5. small functions (C901 ≤10), no duplication, naming per DITS §0;
6. tests are meaningful and deterministic, cover TEST-STRATEGY edge cases, and contain no sleeps;
7. coverage gates are met;
8. no `Any` in public APIs and no unjustified `cast`;
9. layers and arch tests are green;
10. docs are consistent.

Each review writes `docs/design/leva-sh/reviews/phase-N.md` (checked items, findings, fixes) and fixes the findings.
- **Content batch procedure CB** (used by content tasks), for each command:
1. Read its local man page (`mandoc -T ascii <path> | col -bx`).
2. Write original text in `src/leva/content/commands/<name>.yaml` (schema 1). Never copy man page or tldr prose.
   - summary ≤120 chars;
   - explain of 2–6 sentences;
   - 3–8 intents;
   - notes: `bsd-gnu`/`zsh-bash`/`macos`/`safety` where relevant, every claim checked against the macOS man page;
   - 3–8 examples, each with `verify`. Prefer `exec`, with fixtures created by `setup` inside the sandbox. Use `static` for anything on the exec denylist (D-016) or anything nondeterministic. Use `skip` with a `reason` only for destructive or privileged examples;
   - 2–6 related commands;
   - `subcommands`/`help_probe` where relevant.
3. Run `make verify CMD=<name>`; everything must pass.
4. After the batch, run `uv run python -m leva.verify --index .cache/leva/index.db --stats`. Record the cumulative ratios in the commit body; the cumulative target is exec ≥60% and skip <15%.

## 5. Phases and tasks

### Phase 0 — Foundations, conventions, spikes

- [x] T-0.1 Repo constitution: CLAUDE.md, DECISIONS.md, gitignore, design-system snapshot
- Files: `CLAUDE.md`, `docs/design/leva-sh/DECISIONS.md`, `.gitignore`, `docs/design/design-system-snapshot.md` (commit as is).
- Refs: all design docs; external design system; Appendix A of this file.
- Steps:
  1. Write CLAUDE.md with these sections:
     - Project & docs map (PRD/ARCH/DITS/TEST-STRATEGY/ADRs/DECISIONS/spikes/reviews/PLAN);
     - Language (code, comments, UI and content in English; existing design docs stay Italian; new docs in English);
     - Architecture: the package list with single responsibilities and the layer contract from D-002;
     - Coding conventions:
       - Python ≥3.11 target, no 3.12+ syntax, `from __future__ import annotations`;
       - frozen slotted dataclasses; Protocol ports with tech-prefixed adapters;
       - invariant violations raise `ValueError`, user-facing failures are `LevaError` subclasses;
       - no `os.environ` outside `leva.cli`; inject clock/env/paths;
       - every module is a package; private submodules start with `_`, and other packages import only from the package root;
       - logging via `logging.getLogger("leva.<pkg>")`, never print in src except `cli`/`verify.__main__`;
     - Testing conventions (markers, synthetic fixtures only — never copy third-party man pages; `clean_env`; hypothesis profile; Pilot; snapshot update policy; how to view SVG snapshots: `qlmanage -t -s 1600 -o <tmpdir> file.svg`, then read the PNG);
     - TUI rules (palette hex values, no backgrounds except the documented S-1 fallback, `solid` borders, header + footer on every screen, one accent, bold only for the selected item, one-line green success / red error, no emoji, colours only in `theme.py`/`leva.tcss`, binding source = external design system file, snapshot = repo copy);
     - Content authoring rules (CB, schema, exec denylist, licensing);
     - Safety rules (R8);
     - Commands (`make check`, `make test`, `make live`, `make verify`, `uv run ...`);
     - Git rules (R5).
  2. Write DECISIONS.md: copy Appendix A verbatim (D-001..D-024) under a header that says entries can only be appended or amended, each with date and reason.
  3. Add to .gitignore: `.venv-*/`, `.cache/`, `.coverage*`, `coverage.json`, `htmlcov/`, `.hypothesis/`, `spikes/out/`.
- Accept:
  - `grep -c '^## ' CLAUDE.md` ≥ 9;
  - `grep -q 'D-024' docs/design/leva-sh/DECISIONS.md`;
  - `diff -q docs/design/design-system-snapshot.md "/Users/flosh/Desktop/Coding.nosync/Progetti/PyDF Tool/CLAUDE.md"` reports no difference;
  - `git status --porcelain` is empty after the commit.

- [x] T-0.2 Python project scaffold
- Files: `pyproject.toml`, `.python-version` (3.13), `uv.lock`, `Makefile`, `src/leva/__init__.py`, `src/leva/py.typed`, `src/leva/<pkg>/__init__.py` for each of model, paths, placeholders, clipboard, config, sources, manparse, subcmd, content, store, repo, search, library, ingest, tui, cli, verify (docstring stating the D-002 responsibility, nothing else), `tools/__init__.py`, `tests/unit/test_package.py`.
- Refs: ADR-0001, ADR-0006, TEST-STRATEGY §5, D-002, D-016, D-018.
- Steps:
  1. pyproject:
     - hatchling; name `leva`; version `0.1.0`; requires-python `>=3.11`; `license = "MIT"`; `license-files = ["LICENSE", "LICENSE-CONTENT", "NOTICE.md"]`; author progrisriport; macOS/Console classifiers.
     - deps: `textual>=8.2,<9`, `rapidfuzz>=3.14,<4`, `pyyaml>=6.0.2,<7`.
     - `[dependency-groups] dev`: `pytest>=8.4,<9` (with a comment: capped by syrupy==4.8.0 via pytest-textual-snapshot), pytest-asyncio>=1.5, pytest-textual-snapshot>=1.1, pytest-cov, pytest-timeout, pytest-socket, hypothesis, mypy, ruff, import-linter, types-PyYAML.
     - No `[project.scripts]` yet (added in T-9.1).
     - wheel: `packages=["src/leva"]`, exclude `src/leva/verify` (D-016).
  2. ruff: target py311, line-length 100, src=[src, tests, tools, spikes].
     - select: E,W,F,I,N,UP,B,C4,SIM,RUF,PT,PTH,RET,ARG,TID,BLE,T20,ERA,PGH,PIE,C90,S,D.
     - ignore: S603, S607, D102, D105, D107, D203, D213; pydocstyle convention google; max-complexity 10.
     - per-file: tests → S101, D, ARG; tools/spikes → T20, D.
  3. mypy: strict, python_version 3.11, files src+tools, warn_unreachable; enable ignore-without-code, redundant-expr, truthy-bool, possibly-undefined. Override for `tests.*`: check_untyped_defs, no disallow_untyped_defs.
  4. pytest:
     - testpaths tests, pythonpath ["."];
     - addopts `-ra --strict-markers --strict-config --disable-socket --allow-unix-socket -m "not macos_live"`;
     - markers integration, tui, macos_live, perf, clipboard, quarantine;
     - timeout 60; asyncio_mode auto; xfail_strict; filterwarnings error (targeted ignores only with a comment).
  5. coverage: branch, source leva, exclude_also TYPE_CHECKING, overload, Protocol `...`.
  6. importlinter: root_package leva; the layers contract with `containers=["leva"]`, the layers from D-002 and `exhaustive=true`; forbidden contracts from D-002.
  7. Makefile targets: check, lint, fmt, type, arch, test, cov, live, verify, py311.
  8. `leva.__version__` via `importlib.metadata.version("leva")`.
- Accept:
  - `uv sync` ok;
  - `uv run python -c "import leva;print(leva.__version__)"` prints `0.1.0`;
  - `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run lint-imports` all pass (contracts KEPT);
  - `uv run pytest -q` passes;
  - `uv lock --check` passes.

- [x] T-0.3 Test harness and architecture fitness functions
- Files: `tests/conftest.py`, `tests/support/__init__.py`, `tests/support/fake_bin.py`, `tests/arch/test_restricted_imports.py`, `tests/arch/rules.py`, `tools/coverage_gate.py`, `tests/unit/test_coverage_gate.py`, `tests/unit/test_harness.py`, Makefile `check`.
- Refs: TEST-STRATEGY §2 (architectural tests), §5, D-002, D-018, D-019.
- Steps:
  1. `clean_env` autouse fixture (monkeypatch): `LEVA_HOME=tmp`, `HOME=tmp/home`, `TZ=UTC`, `LC_ALL=LANG=en_US.UTF-8`, `LANGUAGE=en`, `MANWIDTH=80`, `COLUMNS=120`.
  2. Hypothesis profile `leva` (derandomize=True, deadline=None, print_blob=True), loaded in conftest.
  3. Auto-apply markers by directory (integration, tui, live → macos_live).
  4. `fake_bin(tmp_path, name, script)` helper that writes an executable `/bin/sh` script.
  5. Arch rules as a pure AST checker, `find_violations(root, rules)`, itself unit-tested on synthetic snippets:
     - `subprocess` only in clipboard, sources, manparse, verify;
     - `sqlite3` only in store, repo, cli;
     - `os.environ`/`os.getenv`/`os.putenv` only in cli;
     - no socket/urllib/http/ssl/ftplib/smtplib anywhere in src;
     - `print(` only in cli and `verify/__main__.py`;
     - imports of `leva.X._private` only from inside `leva.X`.
  6. `coverage_gate.py` reads coverage JSON and enforces D-019, skipping packages with 0 statements. Exit 1 with a readable table.
  7. Tests show that pytest-socket blocks AF_INET connect and allows `socket.socketpair()`.
  8. `make check` complete as in section 4.
- Accept:
  - `uv run pytest tests/arch tests/unit/test_coverage_gate.py tests/unit/test_harness.py -q` passes;
  - a planted violation in a tmp tree is reported (tested);
  - `make check` is green.

- [x] T-0.4 Spike S-2: mandoc on sample pages + full benchmark
- Files: `spikes/s2_mandoc.py`, `docs/design/leva-sh/spikes/S-2-mandoc.md`.
- Refs: ADR-0002, ANALYSIS §9, D-004, D-005, D-007, D-008.
- Steps:
  1. Sample about 20 pages and record, without committing man page text (≤1 structural line per finding):
     - pages: ls, tar, test, `[` (stub), git (Homebrew and CLT), zshbuiltins, bash, builtin, find, grep, sed, launchctl, diskutil, defaults, brew, ssh, openssl (`.1ssl`), the largest man1 page, any `.gz` page;
     - what to record: exit codes, overstrike, NAME separators (` - `, ` -- `, multiple names), heading conventions and duplicate headings, definition-list indentation (builtins, VERBS, COMMANDS), `.so` behaviour, non-UTF-8 bytes, time.
  2. Benchmark rendering of all unique (name, section) pages in sections 1/8 over the manpath dirs + /opt/homebrew/share/man + /usr/local/share/man, with 1, 4 and 8 workers; dedup statistics (/usr/share/man vs the CLT SDK); failures.
  3. Confirm or amend D-007 (stub detection from source, overstrike stripping in Python, `-T ascii`, width 80).
  4. Add an "Impact on plan" section.
  5. If the 8-worker full render exceeds 20 s, insert `[USER]` U-S2 (plan-B lazy rendering decision) after this task.
- Accept:
  - `uv run python spikes/s2_mandoc.py --quick` exits 0;
  - the doc has the sections Method, Environment, Samples, Benchmark, Findings, Decisions, Impact on plan, and the 8-worker timing;
  - `uv run ruff check spikes` passes.

- [x] T-0.5 Spike S-3: FTS5 availability and index size
- Files: `spikes/s3_fts5.py`, `docs/design/leva-sh/spikes/S-3-fts5.md`.
- Refs: ADR-0003, DITS §9, D-006.
- Steps:
  1. For the project interpreter (uv 3.13), `/usr/local/bin/python3`, `/opt/homebrew/bin/python3*` if present, and `/usr/bin/python3`, record:
     - the SQLite version;
     - fts5 with `unicode61 remove_diacritics 2`;
     - a contentless table (`content=''`) with insert/query/`bm25` column weights;
     - the `IFNULL` expression unique index;
     - `mode=ro` URI open.
  2. Build a prototype index (temp dir under `spikes/out/`, gitignored) from all rendered bodies. Record DB size, build time, and p50/p95 latency of 20 queries.
  3. Write a conclusion on NFR-15, R-11 and D-006.
- Accept: `uv run python spikes/s3_fts5.py --quick` exits 0; the doc has the interpreter table, size in MB, latencies and conclusion.

- [x] T-0.6 Spike S-1: Textual transparent background (automated part)
- Files: `spikes/s1_textual_background.py`, `docs/design/leva-sh/spikes/S-1-textual-background.md`.
- Refs: ADR-0005, external design system, D-012.
- Steps:
  1. Demo app variants `--variant transparent|surface`:
     - Theme with `ansi=True`, palette hex colours, and background/surface/panel/boost = `ansi_default`;
     - header box with border title, body boxes with `border: solid`, an OptionList with a selected row, an Input, a custom footer with `─` separator;
     - automatic exit after 1 s.
  2. `--analyze`: run the app in a pty, capture the output and parse SGR. Report:
     - background codes used (49 vs 48;2) — any truecolour background other than the surface variant is a finding;
     - foreground colours ⊆ palette;
     - presence of `┌┐└┘│─`.
  3. List the Textual default styles that inject backgrounds (OptionList highlight, Input, scrollbars, Tabs, Toast) and the CSS overrides needed.
  4. Write a "Recommended theme/CSS" section and a "Manual verification checklist" for U-1 (Terminal.app, iTerm2, Ghostty with a non-black profile background).
- Accept: `uv run python spikes/s1_textual_background.py --analyze` exits 0 and prints the report; the doc has both sections.

- [ ] U-1 [USER] Run the S-1 demo in Terminal.app, iTerm2 and Ghostty using the checklist, and fill in the results table in `S-1-textual-background.md`. Non-blocking: the theme defaults to the S-1 recommendation; adjust in T-8.1 if results differ.

- [x] T-0.7 Design-system update proposal (text only)
- Files: `docs/design/leva-sh/design-system-update-proposal.md`.
- Refs: ADR-0005 (conventions 1–6, Consequences), S-1 findings, external file.
- Steps:
  1. Write the exact Markdown to insert into the external file:
     - Textual as an approved framework (one Theme + one `.tcss`; `ansi=True` + `ansi_default` background per S-1; `solid` borders; `border_title` for box titles; custom footer/status widgets; no inline colours);
     - conventions 1–6;
     - `leva-sh` added to the project list.
  2. Add a rationale and a diff summary. Do NOT edit the external file.
- Accept: the file exists with sections "Proposed text", "Where to insert", "Rationale".

- [ ] U-2 [USER] Approve and apply the design-system update (NB-2) to `/Users/flosh/Desktop/Coding.nosync/Progetti/PyDF Tool/CLAUDE.md`, starting from the T-0.7 proposal. Then copy the result to `docs/design/design-system-snapshot.md`, commit, and tick. Blocks T-8.11.

- [ ] U-3 [USER] Review `DECISIONS.md` (D-001..D-024) and amend any decision you disagree with. Non-blocking.

- [ ] U-4 [USER] Confirm the curated command list and batch priorities (NB-5, Phases 7 and 10). Non-blocking; the default is the order in this plan.

- [x] T-0.R Phase 0 review
- Files: `docs/design/leva-sh/reviews/phase-0.md`, `DECISIONS.md`, PLAN.md (future tasks only, per R10).
- Steps:
  1. Check the scaffold against CLAUDE.md.
  2. Fold spike outcomes into DECISIONS: mark D-007 confirmed or amended, adjust the D-012 theme details.
  3. Make sure every spike's "Impact on plan" has been applied.
- Accept: `make check` green; review note present.

### Phase 1 — Domain leaves

- [x] T-1.1 `leva.model`: errors and value objects
- Files: `src/leva/model/{__init__.py,_errors.py,_types.py}`, `tests/unit/test_model.py`.
- Refs: DITS §0 (errors), §1; D-003, D-011, D-030.
- Steps:
  - `LevaError(message, hint=None)` with `__str__` returning the message. Subclasses IngestError, ManRenderError, ContentError, IndexUnavailableError, ClipboardError, VerificationError, ConfigError.
  - StrEnum `Origin` and `Kind`.
  - Frozen slotted `Entry`, `Section`, `Example`, `Note`, `Subcommand(name, summary, entry_name, source, body="")`.
  - `Example` gains `danger: str | None = None` (non-empty, no newline, when set; D-030).
  - Invariants in `__post_init__` raise `ValueError`:
    - names are non-empty with no whitespace;
    - `Example.cmd` is non-empty with no newline unless preceded by `\`;
    - Literal fields are checked at runtime;
    - `Section.ord` ≥ 0.
  - Re-export everything from `leva.model`.
- Accept: `uv run pytest tests/unit/test_model.py -q` (equality, hash, immutability, slots, every invariant, error message/hint); `make check`.

- [x] T-1.2 `leva.placeholders`
- Files: `src/leva/placeholders/__init__.py`, `tests/unit/test_placeholders.py`.
- Refs: DITS §2; TEST-STRATEGY §4.1; D-013.
- Steps:
  - A state-machine tokenizer: `parse`, `to_plain`, `names` (unique, in order of first appearance), `problems(cmd) -> list[str]` (empty/unclosed placeholders, for strict content validation).
  - Escape `\{{` produces a literal `{{`; an unclosed placeholder is literal text; adjacent placeholders work; unicode works.
  - Hypothesis properties: the concatenation invariant; segments never empty; no two adjacent literal segments; `to_plain` is the identity on brace-free text.
- Accept: `uv run pytest tests/unit/test_placeholders.py -q`, including the TEST-STRATEGY §4 first test verbatim; coverage of `placeholders` ≥90%; `make check`.

- [x] T-1.3 `leva.paths`
- Files: `src/leva/paths/__init__.py`, `tests/unit/test_paths.py`.
- Refs: DITS §4; D-003.
- Steps: `LevaPaths(data_dir, config_file, log_dir)`, `index_db`, `resolve(env, home)`:
  - with `LEVA_HOME`: data_dir = LEVA_HOME, logs = LEVA_HOME/logs, config = LEVA_HOME/config.toml;
  - otherwise: data_dir = ~/Library/Application Support/leva, logs = ~/Library/Logs/leva, config = data_dir/config.toml;
  - an empty LEVA_HOME counts as unset; a relative LEVA_HOME raises ConfigError;
  - no I/O.
- Accept: `uv run pytest tests/unit/test_paths.py -q`; `make check`.

- [x] T-1.4 `leva.clipboard`
- Files: `src/leva/clipboard/__init__.py`, `tests/unit/test_clipboard.py`, `tests/live/test_clipboard_live.py`.
- Refs: DITS §3; TEST-STRATEGY (clipboard row).
- Steps:
  - `Clipboard` Protocol.
  - `PbcopyClipboard(binary, timeout)`: UTF-8 stdin, env `LANG=LC_CTYPE=en_US.UTF-8`; an empty text or one over 64 KiB raises ValueError; a missing binary, timeout or non-zero exit raises `ClipboardError("clipboard unavailable")`.
  - `FakeClipboard` with `.last`, `.history` and an optional failure mode.
  - Unit tests use fake binaries (one writes stdin to a file, one exits 1, one sleeps past the timeout, one is absent).
  - Live test (`macos_live`, `clipboard`): pbcopy/pbpaste round trip that saves and restores the user's clipboard.
- Accept: `uv run pytest tests/unit/test_clipboard.py -q`; `make check`.

- [x] T-1.5 `leva.config`
- Files: `src/leva/config/__init__.py`, `tests/unit/test_config.py`.
- Refs: ARCHITECTURE §5; ADR-0002 §2, §9; D-003.
- Steps:
  - `LevaConfig(sections=("1","8"), extra_man_paths=(), extra_bin_dirs=())`.
  - `load_config(path, home)` with tomllib:
    - missing file → defaults;
    - invalid TOML → `ConfigError("config.toml: invalid TOML at line N")`;
    - unknown keys, wrong types and non-absolute paths (after `~` expansion) raise ConfigError with `config.toml:key: reason`.
  - `digest()` returns a stable sha256 of the normalised config.
- Accept: `uv run pytest tests/unit/test_config.py -q`; `make check`.

- [x] T-1.R Phase 1 review (RC on model, placeholders, paths, clipboard, config)
- Accept: `reviews/phase-1.md`; `make check`.

### Phase 2 — System sources, man parsing, subcommands

- [x] T-2.1 `leva.sources` (A): SystemInfo, ExecutableScanner, origin mapping
- Files: `src/leva/sources/{__init__.py,_system.py,_executables.py,_origin.py}`, `tests/unit/test_sources_executables.py`, `tests/unit/test_sources_system.py`.
- Refs: DITS §5; ADR-0002 §2; TEST-STRATEGY (sources row, §3); D-004.
- Steps:
  - `SystemInfo.detect(*, sw_vers="/usr/bin/sw_vers")`: parses ProductVersion/BuildVersion; arch via `platform.machine()`; failure raises IngestError.
  - `origin_for(path)` per D-004.
  - `ExecutableScanner(dirs)`:
    - skips missing dirs, directories, non-executables, broken and circular symlinks;
    - yields every (name, path), sorted by (name, dir index);
    - origin per D-004.
  - Tests on tmp trees.
- Accept: `uv run pytest tests/unit/test_sources_executables.py tests/unit/test_sources_system.py -q`; `make check`.

- [x] T-2.2 `leva.sources` (B): ManPageLocator and man dir discovery
- Files: `src/leva/sources/_manpages.py`, `tests/unit/test_sources_manpages.py`.
- Refs: DITS §5; ADR-0002 §2; D-004.
- Steps:
  - `discover_man_dirs(manpath_output, extra)` (pure: split on `:`, dedup keeping the first occurrence, append the Homebrew/local dirs and extras).
  - `run_manpath(env, binary="/usr/bin/manpath", timeout=5)` raises IngestError on failure. `env` is the injected user environment: only `PATH` and `MANPATH` are passed on, plus the locale variables (D-004 amendment, S-2).
  - `ManPageLocator(man_dirs, sections)`:
    - scans `man<sec>/`;
    - parses `name.sec[suffix][.gz]`, e.g. `openssl-x509.1ssl` → name `openssl-x509`, section `1`;
    - yields `ManFile(path, name, section, origin, mtime_ns, dir_index)` in a deterministic order.
    - Note: DITS ManFile gains `name` and `dir_index` (D-005).
- Accept: `uv run pytest tests/unit/test_sources_manpages.py -q`; `make check`.

- [x] T-2.3 `leva.sources` (C): ProbeRunner
- Files: `src/leva/sources/_probe.py`, `tests/unit/test_sources_probe.py`.
- Refs: DITS §5; ADR-0002 §6; NFR-11; D-009.
- Steps:
  - `ProbeRunner(allowlist: Mapping[str, tuple[str, ...]], timeout=5.0, max_bytes=262144)`.
  - `run(name)`:
    - a name outside the allowlist raises IngestError and is never executed;
    - `shell=False`, `stdin=DEVNULL`, cwd and HOME in a fresh temp dir (removed afterwards), env per D-009;
    - text = stdout if not blank, else stderr; truncated to max_bytes; the exit status is ignored;
    - spawn error, timeout or empty output raises IngestError.
  - Tests with fake scripts: stdout-only, stderr-only with exit 1, sleeper, huge output, env and cwd assertions.
- Accept: `uv run pytest tests/unit/test_sources_probe.py -q`; `make check`.

- [x] T-2.4 `leva.manparse` (A): overstrike, stub detection, MandocRenderer
- Files: `src/leva/manparse/{__init__.py,_overstrike.py,_stub.py,_render.py}`, `tests/unit/test_manparse_overstrike.py`, `tests/unit/test_manparse_stub.py`, `tests/unit/test_manparse_render.py`, `tests/integration/test_mandoc_renderer.py`, `tests/fixtures/man/src/*.1` (synthetic roff only).
- Refs: DITS §6; ADR-0002 §3–4; S-2; D-007.
- Steps:
  - `strip_overstrike(text)`: pure; handles `X\bX` and `_\bX`.
  - `read_man_source(path)`: gz-aware; decodes UTF-8 with `errors="replace"`.
  - `stub_target(source) -> str | None`: the raw path of a leading `.so` request (`manN/x.N`, or a relative path through `..`), skipping roff comments. Resolution against the man root happens in ingest (D-005 and D-007 amendments, S-2).
  - `ManRenderer` Protocol; `MandocRenderer(binary, width, timeout)`: argv `-T ascii -O width=W`, env `LC_ALL=en_US.UTF-8`, `MANWIDTH`, `TZ=UTC`, cwd = the page's man root (`path.parent.parent`); returns stripped text. A non-zero exit, a timeout, or an output with no non-blank line between the header and footer raises ManRenderError (D-007 amendment).
  - Integration tests (skipped if mandoc is absent) on synthetic `.1` files.
- Accept: `uv run pytest tests/unit/test_manparse_overstrike.py tests/unit/test_manparse_stub.py -q`; `uv run pytest -m integration tests/integration/test_mandoc_renderer.py -q`; `make check`.

- [x] T-2.5 `leva.manparse` (B): `parse_man` sections and NAME
- Files: `src/leva/manparse/{_sections.py,_name.py}`, `tests/unit/test_manparse_parse.py`, `tests/fixtures/man/*.txt` (synthetic golden inputs + expected `.json`).
- Refs: DITS §6; ADR-0002 §4; TEST-STRATEGY (manparse row, §3); S-2.
- Steps:
  - `ParsedMan(names, summary, sections, redirect_to)`.
  - Headings are column-0 lines containing a letter, in any case (D-027). Drop the header and footer (the first and last non-blank lines). Keep duplicate headings as separate sections in order.
  - NAME parsing (the NAME heading is matched without regard to case):
    - split on the first `\s+(-|--|–|—)\s+`;
    - names are comma-separated, including `[`;
    - multi-line NAME is supported;
    - summary is one line of ≤200 chars;
    - names fall back to `name_hint`.
  - Odd or empty text degrades to a single DESCRIPTION section; never raises.
  - Hypothesis "never raises".
  - Golden fixtures: ls-like, test/`[`, multi-line NAME, non-standard headings (including title-case `Name` and a letterless `____` rule line), duplicate headings, empty, >1 MB text.
- Accept: `uv run pytest tests/unit/test_manparse_parse.py -q`; `make check`.

- [x] T-2.6 `leva.manparse` (C): definition lists and builtins
- Files: `src/leva/manparse/{_definitions.py,_builtins.py}`, `tests/unit/test_manparse_builtins.py`, `tests/unit/test_manparse_definitions.py`, `tests/fixtures/man/builtins_*.txt` (synthetic, zsh-like and bash-like layouts).
- Refs: ADR-0002 §5; FR-3; S-2; D-002.
- Steps:
  - `definition_items(body) -> list[DefinitionItem(terms, description)]`:
    - a term line sits at the minimal indent and its description at a deeper indent;
    - consecutive term lines are grouped (`. file` + `source file`);
    - indents are relative to the body, never fixed columns. An inline term (term, then two or more spaces, then text on the same line) starts its description on that line (D-027).
  - `extract_builtins(parsed, heading="SHELL BUILTIN COMMANDS") -> list[BuiltinDoc(name, synopsis, summary, body)]`:
    - name = first token of each term;
    - summary = first sentence of the description, ≤200 chars;
    - sorted and unique.
- Accept: `uv run pytest tests/unit/test_manparse_builtins.py -q`; coverage of `manparse` ≥90%; `make check`.

- [x] T-2.7 `leva.subcmd`: extractors and merge
- Files: `src/leva/subcmd/{__init__.py,_types.py,_hyphen.py,_section_list.py,_help_text.py,_merge.py}`, `src/leva/manparse/{_name.py,_builtins.py,__init__.py}` (`first_sentence`), `tests/unit/test_subcmd.py`, `tests/unit/test_manparse_builtins.py`, `tests/fixtures/help/*.txt` (synthetic two-col, git-list, brew-commands).
- Refs: DITS §7; ADR-0002 §6; D-008.
- Steps:
  - `SubcommandExtractor` Protocol `extract(parent, parsed, known: Mapping[str, KnownPage])`.
  - `HyphenPageExtractor` follows the SYNOPSIS rule; `SectionListExtractor` follows the heading regex and term filter, with body = description.
  - `HelpTextExtractor(profile, text)` with profiles two-col, git-list, brew-commands.
  - `merge_subcommands(by_priority)` with per-field merge.
  - Negative tests: ssh-keygen is not a subcommand of ssh; `system/[service]` is filtered out; unknown profile raises ValueError.
- Accept: `uv run pytest tests/unit/test_subcmd.py -q`; `make check`.

- [x] T-2.R Phase 2 review (RC; plus "live" smoke: `uv run pytest -m macos_live tests/live/test_sources_live.py`. Create that test: /usr/bin has ≥500 executables, `ls` present, man1 renders with ≤2% failures.)
- Accept: review note; `make check`; the live test passes.

### Phase 3 — Content layer

- [x] T-3.1 `leva.content` (A): schema types and validation
- Files: `src/leva/content/{__init__.py,_schema.py,_validate.py,_policy.py}`, `tests/unit/test_content_{validate,policy,schema}.py`.
- Refs: DITS §8; ADR-0004; D-010, D-016; D-030 (`Example.danger`); D-033 (`Example.cmd` invariants)
- Steps:
  - Dataclasses: CuratedCommand, ExampleSpec, VerifySpec, HelpProbe(args, profile), TldrPage, TldrExample; `ContentRecord = CuratedCommand | TldrPage`.
  - `validate_command(data, file) -> CuratedCommand`, strict:
    - schema must be 1; `kind` other than `command` → "not supported in schema 1";
    - unknown keys are errors; name == file stem;
    - required summary (≤120), explain and ≥1 intent;
    - notes kinds checked; example id `^<name>-[a-z0-9-]+$`;
    - cmd uses `placeholders.problems`;
    - cmd meets the `Example.cmd` invariants of D-033 (no `\r`, no trailing newline, `\` before every newline; a YAML `|` block ends with a newline, so strip it or reject it) before `Example` is built, so no `ValueError` escapes;
    - exec: bind covers all placeholders, `stdout_regex` compiles, exec denylist (D-016);
    - skip requires reason; `min_macos` pattern; related/subcommand names valid.
  - Messages look like `commands/tar.yaml:examples[2].cmd: unclosed placeholder`.
  - Each rule has a negative test.
- Accept: `uv run pytest tests/unit/test_content_validate.py -q`; `make check`.

- [x] T-3.2 `leva.content` (B): providers, content_version, attribution, first real YAML
- Files: `src/leva/content/{_yaml_provider.py,_tldr_provider.py,_version.py}`, `src/leva/content/commands/ls.yaml`, `src/leva/content/ATTRIBUTION.md` (initial: curated content CC BY 4.0; the tldr section is added in T-7.2), `tests/fixtures/content/**`, `tests/fixtures/tldr/*.jsonl`, `tests/unit/test_content_providers.py`, `tests/integration/test_content_real.py`.
- Refs: DITS §8; ADR-0004 §4; TEST-STRATEGY (content row); D-017.
- Steps:
  - `CuratedYamlProvider(root)`: sorted files, `yaml.safe_load`, cross-file unique example ids, YAML errors become ContentError.
  - `TldrSnapshotProvider(root)`: reads `common.jsonl`/`osx.jsonl` (osx overrides common); a missing snapshot means an empty iterator.
  - `content_version(root)`: sha256 of curated files + `tldr/SOURCE.json`.
  - `attribution_text()` via importlib.resources.
  - `ls.yaml`: 3 or more examples, at least one `exec`.
  - The integration test loads every real file.
- Accept: `uv run pytest tests/unit/test_content_providers.py tests/integration/test_content_real.py -q`; coverage of `content` ≥90%; `make check`.

- [x] T-3.R Phase 3 review (RC)
- Accept: review note; `make check`.

### Phase 4 — Index storage and repository

- [x] T-4.1 `leva.store` (A): schema, IndexWriter, open_readonly
- Files: `src/leva/store/{__init__.py,_schema.py,_writer.py,_open.py}`, `src/leva/store/migrations/0001_init.sql`, `tests/unit/test_store_writer.py`.
- Refs: DITS §9; ADR-0003; D-006; D-029; D-030.
- Steps:
  - Schema v1 per DITS plus the D-006 changes: `entry.rank`, the null-safe unique index, `subcommand.body`, indexes on alias/name.
  - The `intent` table gains `ord INT` (curated list order, 0-based; D-029); the `example` table gains `danger TEXT` (NULL when absent; D-030).
  - `add_intents(entry_id, texts: Sequence[str])` stores `ord` = list index (DITS §9 has no intent writer); `add_examples` stores `danger`.
  - `SCHEMA_VERSION` = `PRAGMA user_version`.
  - `NewEntry` dataclass.
  - `IndexWriter(path)`: the path must not exist; one transaction; `__exit__` rolls back and closes on exception; `add_*` methods; sqlite errors become IngestError.
  - `open_readonly(path)`: `mode=ro` URI; missing, corrupt or wrong `user_version` raises IndexUnavailableError.
- Accept: `uv run pytest tests/unit/test_store_writer.py -q` (rollback, UNIQUE incl. NULL section, ro open errors); `make check`.

- [x] T-4.2 `leva.store` (B): finalize, FTS and digest
- Files: `src/leva/store/_finalize.py`, `src/leva/store/_writer.py`, `tests/integration/test_store_finalize.py`.
- Refs: DITS §9; ADR-0003; S-3.
- Steps:
  - `finalize()`:
    - fills contentless `search_fts` per entry (rowid = id; name + aliases, intents, summary, body = ordered sections), built in Python in id order;
    - `ANALYZE`; `integrity_check == ok`;
    - meta: schema_version, built_at (from the injected clock), index_digest;
    - `index_digest` = sha256 over a canonical dump of content tables ordered by key, excluding built_at.
  - Determinism test: two writes of the same input give the same digest.
- Accept: `uv run pytest -m integration tests/integration/test_store_finalize.py -q`; `make check`.

- [x] T-4.3 Fixture index factory (test support)
- Files: `tests/support/index_factory.py`, `tests/fixtures/index/entries.json`, `tests/unit/test_index_factory.py`, `tests/conftest.py`.
- Refs: TEST-STRATEGY §5.
- Steps:
  - Build a fixture index of about 60 synthetic entries with IndexWriter:
    - ls, tar, grep, find, sed, du, df, chmod, curl, pbcopy, open, ditto, unzip, zip, gzip, kill, pkill, ps;
    - git + git-commit + git-log, diskutil (with subcommands), brew;
    - echo (macos + zsh + bash), cd (zsh builtin), test with alias `[`;
    - an exe-only entry; a curated entry with examples (curated + tldr duplicate, one with `danger`, D-030); notes; related; long sections.
  - Deterministic clock.
  - Fixture `fixture_index(tmp_path)` in conftest.
- Accept: `uv run pytest tests/unit/test_index_factory.py -q`; `make check`.

- [x] T-4.4 `leva.repo`: Repository
- Files: `src/leva/repo/{__init__.py,_rows.py,_fts.py,_repository.py}`, `tests/unit/{test_repo.py,test_repo_fts.py}`.
- Refs: DITS §10; D-005, D-010, D-029, D-030, D-033.
- Steps:
  - `NameRow(entry_id, name, section, kind, origin, summary, curated, aliases, intents)`, `FtsHit(entry_id, score)`, `IndexStats`.
  - `NameRow.intents` is ordered by `intent.ord` (D-029); `examples(entry_id)` returns each `Example` with its `danger` (D-030).
  - `Entry.kind`/`origin` are enum members (D-033): convert the stored strings with `Kind(value)`/`Origin(value)`; a plain string raises `ValueError`.
  - `get_entry(name, section=None)`: name match ordered by rank, then alias match.
  - The other query methods; ordered results.
  - `fts(query, limit)`: tokens quoted, operators and `"` `*` `-` `NEAR` `:` neutralised, empty → []; bm25 with weights name > intents > summary > body.
  - DB errors become IndexUnavailableError.
  - Injection tests.
- Accept: `uv run pytest tests/unit/test_repo.py -q`; coverage of `store`/`repo` ≥90%; `make check`.

- [x] T-4.R Phase 4 review (RC)
- Accept: review note; `make check`.

### Phase 5 — Search and library

- [x] T-5.1 `leva.search`: Searcher
- Files: `src/leva/search/{__init__.py,_ranking.py,_searcher.py}`, `tests/unit/test_search.py`, `tests/fixtures/index/gold_mini.json` (30 queries).
- Refs: DITS §11; ADR-0003; D-010; D-029 (intent ranking + `via`); D-031
- Steps:
  - `Weights`/`DEFAULT_WEIGHTS`.
  - Candidates: in-memory NameRows loaded once (exact name/alias, prefix, `rapidfuzz.fuzz.WRatio ≥ 80` on names/aliases, intent token match) + FTS hits.
  - Strict tiers: exact > prefix > fuzzy > intent > summary > body. Small fixed curated/builtin bonus that never crosses tiers.
  - `why` per D-010; ties broken by (name, section, origin).
  - Dedup by entry_id; ≤ limit; blank query → [].
  - `SearchResult` with section/kind/origin.
  - `SearchResult` gains `via: str | None` (the matched intent text, D-029); intent tiers: exact phrase > all words > partial, then lower `ord` first.
  - `Searcher.nearest_names(query, limit=3) -> list[str]`: best `rapidfuzz` WRatio over names and aliases with no threshold, distinct names, ties by name; blank query → [].
  - Repo facts (D-049): `Repository.names()` returns `NameRow(entry_id, name, section, kind, origin, summary, curated, aliases, intents)` ordered `(name, rank, id)`; `Repository.fts(query, limit)` returns `FtsHit(entry_id, score)` with `score = -bm25` (higher is better, ties by ascending entry id) using `FTS_WEIGHTS` (10, 5, 2, 1: name, intents, summary, body). FTS has no prefix search (`arch*` and `arch` find nothing, every token is a quoted whole-word phrase, at most 32 tokens): the prefix and fuzzy tiers come from `names()`. A text with a lone surrogate gives `[]`.
  - Tests: gold mini ≥ 27/30 in the top 3, typos (`gerp` → grep), case, multiple spaces, 1-char query, unicode/emoji, very long query, stable order.
- Accept: `uv run pytest tests/unit/test_search.py -q`; coverage ≥90%; `make check`.

- [x] T-5.2 Search latency benchmark (NFR-2)
- Files: `tests/integration/test_search_latency.py`.
- Steps: 3000 synthetic entries via `with IndexWriter(path) as w: ...; w.finalize(built_at=<aware datetime>)` (`finalize` fills `search_fts`; an unfinalized index has an empty FTS table), read back through `Repository(open_readonly(path))` (D-047, D-048); 200 queries; p95 < 50 ms (CI-tolerant: assert < 100 ms, report the real p95).
- Accept: `uv run pytest -m integration tests/integration/test_search_latency.py -q`; `make check`.

- [x] T-5.3 `leva.library`: Library facade
- Files: `src/leva/library/{__init__.py,_card.py,_history.py,_library.py}`, `tests/unit/test_library.py`.
- Refs: DITS §12; DESIGN-PATTERNS (library); D-011; D-031.
- Steps:
  - `Card`.
  - `Library.nearest_names(query, limit=3)` delegates to the Searcher (D-031).
  - `open(name)`:
    - name or alias;
    - multi-word input: try `<a>-<b>` hyphen entry first, else `open_subcommand`;
    - records history.
  - `open_subcommand` per D-011, with a synthesized card when the subcommand has no page of its own.
  - Examples: curated first, then tldr; duplicates merged by normalised command.
  - History max 50 with browser semantics.
  - `attribution()` from meta; `close()`.
  - Repo facts (D-049): `Repository` has `get_entry_by_id(entry_id) -> Entry | None`, `explain(entry_id) -> str` (`""` when not curated or the id is unknown) and an idempotent `close()` that closes the connection; `meta()["attribution"]` holds the attribution text (written through `IndexWriter.set_meta`). `get_entry` does not strip the name (`"ls "` is `None`); multi-word input must be split by the library. Every `Repository` method raises `IndexUnavailableError` (hint `run leva --rebuild`) on a database or stored-value problem.
- Accept: `uv run pytest tests/unit/test_library.py -q`; `make check`.

- [x] T-5.R Phase 5 review (RC)
- Accept: review note; `make check`.

### Phase 6 — Ingest

- [x] T-6.1 `leva.ingest` (A): fingerprint and staleness
- Files: `src/leva/ingest/{__init__.py,_fingerprint.py}`, `tests/unit/test_ingest_staleness.py`.
- Refs: DITS §13; ADR-0002 §9; D-020.
- Steps:
  - `Staleness` enum.
  - `Fingerprint(version_part, system_part)`:
    - version part = leva version, `content_version(default_root())` from `leva.content` (D-046), schema;
    - system part = macOS version and build, per-dir (count, max mtime) for man and bin dirs, config digest.
  - Stored in meta: the parts are written with `IndexWriter.set_meta` before `finalize`, so they are covered by the `index_digest` (D-048: every meta key except `built_at` and `index_digest`); read them back with `Repository.meta()`.
  - `staleness(index_db)`: missing or unreadable → MISSING; version mismatch → VERSION_CHANGED; system mismatch → SYSTEM_CHANGED; else FRESH.
  - Tests with fake SystemInfo and tmp dirs, one per cause.
- Accept: `uv run pytest tests/unit/test_ingest_staleness.py -q`; `make check`.

- [x] T-6.2 `leva.ingest` (B): page pipeline
- Files: `src/leva/ingest/_pipeline.py`, `src/leva/ingest/_progress.py`, `tests/support/ingest_fakes.py`, `tests/unit/test_ingest_pipeline.py`.
- Refs: DITS §13; ADR-0002 §3, §8; NFR-12.
- Steps:
  - Dedup ManFiles per D-005.
  - Stub detection before rendering: `stub_target(read_man_source(path))` (a `ManRenderError` from reading counts as a failure of that page); the raw `.so` argument is resolved against the man root by ingest (D-005, D-040).
  - Render + parse in a `ThreadPoolExecutor(workers)`; results reassembled in input order (deterministic).
  - Per page, catch `ManRenderError` from `render`/`read_man_source` (the only error `leva.manparse` raises); `parse_man` never raises for valid input; the entry name is `ManFile.name`, and `redirect_to` is set with `dataclasses.replace`.
  - A failure means `progress.warn` + an entry in skipped; more than 20% failures raises `IngestError("man pages unreadable; run leva doctor")`.
  - Cooperative cancel token checked between pages.
  - Tests with a FakeRenderer (random delays, failures).
- Accept: `uv run pytest tests/unit/test_ingest_pipeline.py -q`; `make check`.

- [x] T-6.3 `leva.ingest` (C): catalog assembly
- Files: `src/leva/ingest/_catalog.py`, `tests/unit/test_ingest_catalog.py`.
- Refs: D-005 (all rules), FR-2, FR-3.
- Steps:
  - A pure function that turns pages, executables and builtins into catalog entries with aliases, sections and ranks.
  - Builtin entries come from `extract_builtins` (zsh and bash pages, D-043): `BuiltinDoc.synopsis` becomes the SYNOPSIS section, `body` the DESCRIPTION, `summary` the entry summary; origins ZSH and BASH.
  - One test per D-005 rule: echo three ways, cd via stub plus builtin, `[` alias, exe-only, an exe attached through an alias, section 1 vs 8, CLT duplicate, Homebrew-first manpath, a stub shadowing a later real page (rsync), a stub whose target is outside the man dirs (Xsan), a stub with a missing target.
- Accept: `uv run pytest tests/unit/test_ingest_catalog.py -q`; `make check`.

- [ ] T-6.4 `leva.ingest` (D): enrichment
- Files: `src/leva/ingest/_enrich.py`, `tests/unit/test_ingest_enrich.py`.
- Refs: D-005, D-008, D-009, D-011, D-017, D-021, D-030.
- Steps:
  - Subcommands: run the extractors chain per entry, plus probes declared by curated `help_probe` (allowlist `{name: (str(first_executable.path), *help_probe.args)}` built from curated content + scanned executables; catch `IngestError` per probe and continue), then merge with `merge_subcommands([curated, probe, section, hyphen])` (D-044); `known` is `{entry.name: KnownPage(name, summary, synopsis_body)}` over all man-backed entries (`""` when no SYNOPSIS); curated `Subcommand.source` is `"curated"`.
  - Curated attachment: explain, intents, notes, examples (each with its `danger`, D-030), related (only names that resolve), subcommands; `curated` flag; re-rank. Records come from `CuratedYamlProvider(default_root()).load()`; an example becomes `spec.to_example()` (source `curated`, `verified` = verify mode, `danger` kept); the probe allowlist and the `HelpTextExtractor` profile come from `command.help_probe.args` and `.profile` (`HelpProbe`, D-045).
  - tldr attachment: `TldrSnapshotProvider(default_root()).load()` yields one `TldrPage` per name (osx already replaced common); examples are `page.to_examples()` (ids `<name>-tldr-<n>`, source `tldr`, verified `none`, D-017).
  - Curated commands that are not installed are skipped and reported.
- Accept: `uv run pytest tests/unit/test_ingest_enrich.py -q`; `make check`.

- [ ] T-6.5 `leva.ingest` (E): IndexBuilder.build
- Files: `src/leva/ingest/{_builder.py,_lock.py}`, `tests/integration/test_ingest_build.py`.
- Refs: DITS §13; ARCHITECTURE §3.1; TEST-STRATEGY (ingest row, §3); NFR-8, NFR-12; D-020, D-022.
- Steps:
  - `IndexBuilder(...)`. The DITS signature changes per D-002: no `builtins` argument; added `config_digest` and `clock`.
  - `build(target, progress, *, cancel=None)`:
    - flock on `target.parent/index.lock`;
    - remove a stale `.new` file;
    - phases: scan, render, enrich, write, finalize;
    - write `index.db.new` in (name, section, origin) order, then `os.replace`;
    - the old index stays intact on any failure; `OSError` becomes IngestError; KeyboardInterrupt and cancel clean up;
    - returns `BuildReport`;
    - meta also holds fingerprint parts and attribution.
  - `NullProgress`.
  - Store facts (D-047, D-048): entries are `NewEntry(name, section, kind, origin, summary, path, has_man, curated, rank=0, explain="")` with `rank` computed by ingest (D-005); ids are assigned in write order (1, 2, 3, ...), so the write order (name, section, origin) fixes them; the child lists (`add_sections`, `add_examples`, `add_subcommands`, `add_notes`, `add_related`, `add_intents`) are called once per entry. Use `with IndexWriter(path) as w: ...; digest = w.finalize(built_at=clock())` (`clock()` timezone-aware; `digest` becomes `BuildReport.digest`); `IndexWriter(path)` raises `ValueError` when the file exists, so remove a stale `.new` first. A failed build rolls back and leaves the `.new` file with no tables and `user_version` 0: the builder removes it. Every writer failure is an `IngestError`.
  - Integration tests: full build on a fixture tree with FakeRenderer; same digest twice; old index kept on failure; lock contention; real-mandoc variant on synthetic pages.
- Accept: `uv run pytest -m integration tests/integration/test_ingest_build.py -q`; coverage of `ingest` ≥90%; `make check`.

- [ ] T-6.6 Live ingest on this Mac
- Files: `tests/live/conftest.py` (session fixture `real_index` built into a tmp LEVA_HOME), `tests/live/test_ingest_live.py`.
- Refs: PRD §7; NFR-3, NFR-15; TEST-STRATEGY (ingest live).
- Steps:
  - Assert:
    - 100% of executables in the 4 system dirs resolve via `get_entry`;
    - ≥95% of man-backed entries have a summary;
    - build ≤30 s (logged); index ≤100 MB;
    - git, diskutil and launchctl yield at least 20, 15 and 10 subcommands (before curated content).
  - Write the numbers into `docs/design/leva-sh/reviews/ingest-live.md`.
- Accept: `make live` (this file) passes; `make check`.

- [ ] T-6.R Phase 6 review (RC + determinism + failure paths)
- Accept: review note; `make check`; `make live`.

### Phase 7 — Verification and first curated content

- [ ] T-7.1 Verify the tldr-pages licence (NB-3)
- Files: `docs/design/leva-sh/spikes/NB-3-tldr-license.md`.
- Refs: ADR-0004 §4–5; ANALYSIS R-7; NOTICE.md.
- Steps:
  1. Get the latest release tag from the GitHub API (expected v2.3 or newer).
  2. Read `LICENSE.md` at that tag (`https://raw.githubusercontent.com/tldr-pages/tldr/<tag>/LICENSE.md`) and also the root licence file inside `tldr-pages.en.zip`.
  3. Record the URL, tag, date, the one-line licence statement and the conclusion.
  4. If the content licence is NOT CC BY 4.0, mark T-7.2 `[!]`, add U-NB3 (decision: drop tldr or relicense), and stop per R7.
- Accept: the doc concludes "CC BY 4.0 confirmed at <tag>" (or the R7 path was taken).

- [ ] T-7.2 Vendor the tldr snapshot
- Blocked-by: T-7.1
- Files: `tools/vendor_tldr.py`, `tests/unit/test_vendor_tldr.py` (synthetic zip, no network), `src/leva/content/tldr/{common.jsonl,osx.jsonl,SOURCE.json,LICENSE.md}`, `src/leva/content/ATTRIBUTION.md`, `tests/unit/test_attribution.py`, `NOTICE.md`.
- Refs: ADR-0004 §4; D-017.
- Steps:
  - The tool (idempotent):
    - downloads `tldr-pages.en.zip` and `tldr.sha256sums` for `--tag`, then verifies sha256;
    - keeps `common/`, `osx/`;
    - converts pages to JSONL `{name, platform, description, examples:[{desc, cmd}]}`, sorted;
    - normalises `{{[-x|--long]}}` to `-x` and drops mnemonic `[c]` brackets in descriptions;
    - writes SOURCE.json (tag, url, sha256, license, retrieved date) and copies the licence.
  - ATTRIBUTION.md: tldr-pages, CC BY 4.0, tag and sha, list of changes.
  - Licence test: ATTRIBUTION mentions tldr-pages and the SOURCE.json tag.
  - Run the tool once (network allowed only here).
  - The provider (D-046) rejects any JSONL line that is not exactly `{name, platform, description, examples: [{desc, cmd}]}` with string values, a `platform` different from the file stem, or a second page with the same name in one file; example commands that break the D-033 invariants are dropped with a warning. `content_version` hashes `SOURCE.json` and not the JSONL files, so any change of the JSONL output, also a converter change at the same tag, must change `SOURCE.json` (record a converter revision in it).
- Accept: `uv run pytest tests/unit/test_vendor_tldr.py tests/unit/test_attribution.py tests/integration/test_content_real.py -q`; `make check`.

- [ ] T-7.3 `leva.verify` (A): sandbox and exec mode
- Files: `src/leva/verify/{__init__.py,_sandbox.py,_exec.py}`, `tests/unit/test_verify_exec.py`.
- Refs: DITS §16; ADR-0004 §3; TEST-STRATEGY (verify row); D-016.
- Steps:
  - `VerifyResult`.
  - Repo facts (D-049): `Repository.examples(entry_id)` returns each `Example` with its `danger`; `Repository.stats()` is `IndexStats(entries, man_pages, builtins, curated, examples, subcommands)` with no per-verify-mode counts, so `--stats` counts modes itself.
  - `Verifier(repo, *, workdir, timeout, sandbox_exec="/usr/bin/sandbox-exec", allow_unsandboxed=False)`.
  - exec mode:
    - fresh `workdir/<id>/`; HOME and TMPDIR inside it; env minimal per DITS; `/bin/zsh -f -c`; stdin `/dev/null`;
    - setup runs first, then the cmd with placeholders substituted from `bind`;
    - SBPL profile: `(allow default)`, `(deny network*)`, deny `file-write*` except the realpath of the sandbox and `/dev/null`/`/dev/tty`/`/dev/fd`, `(deny signal (target others))`;
    - no sandbox-exec → `fail` ("os sandbox unavailable") unless allow_unsandboxed;
    - assertions: exit code, stdout_contains/regex, files_exist; unbound placeholder → fail;
    - `min_macos` greater than the current version → skip.
  - skip mode returns the reason.
  - Input is `leva.content.VerifySpec` (`mode`, `setup`, read-only `bind`, `expect_exit`, `stdout_contains`, `stdout_regex`, `files_exist` as sandbox-relative paths, `reason`, `min_macos`) via `ExampleSpec`; validation (D-045) already guarantees `bind` holds exactly the placeholders of `cmd`, so "unbound placeholder → fail" is a defensive check for hand-built specs.
  - Tests: HOME isolation; a write outside the sandbox is denied and the outside file does not exist; TCP connect to a test-owned 127.0.0.1 listener is denied (`@pytest.mark.enable_socket`); timeout; bind missing.
- Accept: `uv run pytest tests/unit/test_verify_exec.py -q`; `make check`.

- [ ] T-7.4 `leva.verify` (B): static mode, CLI and live suite
- Files: `src/leva/verify/{_static.py,_report.py,__main__.py}`, `tests/unit/test_verify_static.py`, `tests/unit/test_verify_cli.py`, `tests/live/test_curated_examples.py`, `tests/live/test_tldr_static_report.py`, `docs/CONTENT-GUIDE.md`, Makefile `verify`.
- Refs: DITS §16; D-016, D-017.
- Steps:
  - static mode (`leva.content` already owns `EXEC_DENYLIST` and the lexical tokenizer `simple_commands` in `_policy`, which is not exported: export it from the package root and reuse it instead of a second copy; it also handles wrappers and `find -exec`):
    - `shlex.split` of the plain command; split at pipes and command separators;
    - each program must exist in the index or in the standard PATH dirs;
    - each flag must appear in the entry's man/help text (short clusters split into single flags; long flags compared before `=`).
  - CLI: `python -m leva.verify --index P [--command N] [--source curated|tldr] [--min-macos V] [--stats]`; exit 0, or 1 on any fail.
  - Stats: counts per mode, exec%, skip%.
  - Live: parametrised over all curated examples (must pass); tldr static is a report only.
  - CONTENT-GUIDE for authors (US-10).
- Accept: `uv run pytest tests/unit/test_verify_static.py tests/unit/test_verify_cli.py -q`; `make verify CMD=ls`; `make check`.

- [ ] T-7.5 Curated batch 1: git, brew, diskutil, defaults, launchctl
- Every one of these has subcommands, and `help_probe` where available (D-009).
- Refs: CB, FR-8.
- Accept: CB passes for each; the live ingest assertion that FR-8 subcommands are ≥ thresholds (update `tests/live/test_ingest_live.py`: git ≥20, brew ≥20 if installed, diskutil ≥15, defaults ≥8, launchctl ≥10); `make check`.

- [ ] T-7.6 Curated batch 2: ls (extend), cd, pwd, mkdir, rmdir, rm, cp, mv, ln, touch, cat, less, head, tail, wc
- Accept: CB; `make check`.

- [ ] T-7.7 Curated batch 3: find, grep, sed, awk, tar, zip, unzip, gzip, open, pbcopy, pbpaste, ps, kill
- Accept: CB; `make check`; `--stats` reports exec ≥60% and skip <15% cumulatively.

- [ ] T-7.R Phase 7 review (RC + content sample self-review: re-check 10 random examples and notes against man pages)
- Accept: review note; `make check`; `make live`.

### Phase 8 — TUI
UI note: T-8.1 to T-8.10 use only conventions the design system already approves (palette, borders, header/footer, one-line green/red messages, bold+accent selection). Placeholder highlighting and the `>` marker are T-8.11.

- [ ] T-8.1 Theme and stylesheet
- Files: `src/leva/tui/{__init__.py,theme.py,leva.tcss}`, `tests/tui/test_theme.py`.
- Refs: ADR-0005; S-1; D-012.
- Steps:
  - One `Theme` (`ansi=True`, palette, ansi_default backgrounds), copied from S-1 "Recommended theme/CSS": mandatory variables `ansi-background`/`ansi-foreground`, plus the `block-cursor-*`, `input-cursor-*`, `*-selection-*`, `border*` and `scrollbar*` variables.
  - `leva.tcss`: copied from S-1: `solid` borders (never `tall`/`outer`), `border-title-color` accent, `Input` cursor/placeholder rules (they beat the `Input:ansi` defaults), `OptionList` highlight, `Tabs Underline { display: none }`, `Tab`, scrollbars, `Toast`.
  - Palette test: every colour in tcss/theme ∈ palette ∪ {`ansi_default`, `transparent`}; the only `background:` value is `ansi_default` (S-1 found no widget that needs the `#1A1A1A`/`#202020` fallback); no `tall`/`wide`/`outer`/`round`/`heavy`/`double` border.
- Accept: `uv run pytest tests/tui/test_theme.py -q`; `make check`.

- [ ] T-8.2 Shared widgets: HeaderBox, FooterBar, StatusLine
- Files: `src/leva/tui/widgets/{__init__.py,header.py,footer.py,status.py}`, `tests/tui/test_widgets_chrome.py`.
- Refs: design system (layout); DITS §14 (footer, StatusLine).
- Steps:
  - Header: box with title `Leva` (bold accent) and tagline "less effort, more thought" in secondary.
  - Footer: `─` separator at width + "key desc" pairs from visible bindings, in secondary.
  - StatusLine: `success(text)`/`error(text)`, one line, auto-clear after a configurable duration (3 s default, 0 in tests).
  - Pilot tests with a minimal host app.
- Accept: `uv run pytest tests/tui/test_widgets_chrome.py -q`; `make check`.

- [ ] T-8.3 LevaApp shell, routing, narrow screen, help
- Files: `src/leva/tui/{app.py,screens/__init__.py,screens/narrow.py,screens/help.py}`, `tests/tui/test_app_shell.py`.
- Refs: DITS §14; FR-10, FR-19; D-012, D-013, D-014.
- Steps:
  - `LevaApp(open_library, clipboard, builder, start, paths, needs_build)`.
  - Global bindings: `/`, `?`, Esc, `q` (not inside inputs), ctrl+c, `r` (double press, D-013), `a`.
  - Below 60x12, a "terminal too narrow (min 60 cols)" screen that keeps header and footer.
  - `LevaError` from the library becomes a red status line; the app never crashes.
  - Help screen lists the bindings.
- Accept: `uv run pytest tests/tui/test_app_shell.py -q`; `make check`.

- [ ] T-8.4 SearchScreen and ResultList
- Files: `src/leva/tui/screens/search.py`, `src/leva/tui/widgets/result_list.py`, `tests/tui/test_search_screen.py`.
- Refs: ARCHITECTURE §3.2; DITS §14; FR-9–11; D-012; UX.md §3.1; D-028, D-029, D-031
- Steps:
  - Input with debounce (30 ms, injectable).
  - Rows: name, origin/section tag (secondary), summary (secondary); selected row bold+accent.
  - Navigation: Up/Down, j/k, PgUp/PgDn, g/G; Enter/click opens.
  - StartTarget `query` resolution per D-012.
  - Search facts (D-050): results come from `Library.search` as `SearchResult(entry_id, name, section, kind, origin, summary, score, why, via)`; show `via: <intent>` when `via` is not None; several results can share a name (echo zsh/bash/macos), so open a result by `entry_id`, never by name.
- Accept: `uv run pytest tests/tui/test_search_screen.py -q` (type a query, see results, arrows, Enter opens the card, click on a row); `make check`.

- [ ] T-8.5 CardView, CardScreen, Overview tab, history
- Files: `src/leva/tui/widgets/card_view.py`, `src/leva/tui/screens/card.py`, `tests/tui/test_card_screen.py`.
- Refs: DITS §12, §14; FR-4, FR-15; D-012; UX.md §3.2; D-028
- Steps:
  - Tabs Overview/Examples/Subcommands/Manual/Related; keys 1–5, h/l, Left/Right, click.
  - Breadcrumb (click goes back); Backspace and Alt+Left go back; forward.
  - Overview: summary, explain, notes by kind, origin/path/section, "no manual entry" when needed.
  - Two-pane layout at ≥100 cols (CardView preview in SearchScreen), single pane at 60–99.
  - Library facts (D-051): `Library.card(entry_id)` builds the preview without touching history; `open_result(entry_id)` opens from Results and resets history (D-028); `open(name)`/`open_subcommand(card, sub)` grow it; `back()`/`forward()` return `None` at the ends; the breadcrumb is `search` + `' '.join(c.breadcrumb)` of each card in `trail()`; the lead line is `Card.summary`.
- Accept: `uv run pytest tests/tui/test_card_screen.py -q`; `make check`.

- [ ] T-8.6 Examples tab and copy
- Files: `src/leva/tui/widgets/example_list.py`, `tests/tui/test_examples_copy.py`.
- Refs: ARCHITECTURE §3.3; FR-12, FR-7; DITS §14; UX.md §3.2–3.3; D-030
- Steps:
  - Curated examples, then tldr under a "from tldr-pages" label (secondary); long commands wrap.
  - `c` or click → `to_plain` → `clipboard.copy` → `copied: <cmd>` in green.
  - `ClipboardError` → red `clipboard unavailable`.
  - `c` with no selection does nothing and shows a hint.
  - Placeholders render as plain text until T-8.11.
- Accept: `uv run pytest tests/tui/test_examples_copy.py -q` (FakeClipboard receives the exact text; repeated `{{x}}`; failure path); `make check`.

- [ ] T-8.7 Subcommands and Related tabs
- Files: `src/leva/tui/widgets/{subcommand_list.py,related_list.py}`, `tests/tui/test_subcommands_related.py`.
- Refs: FR-8, FR-15; D-011.
- Steps: Enter/click opens a subcommand (synthesized card when it has no page) or a related entry; breadcrumb updates; back works.
  - Library facts (D-051): `open_subcommand(card, sub)` matches `sub` exactly against `card.subcommands` and returns the page card (breadcrumb `(parent, sub)`) or a synthesized one (`entry` = parent, `sections` = `DESCRIPTION` with the subcommand body, examples starting with `parent sub`); related names open with `open(name)`.
- Accept: `uv run pytest tests/tui/test_subcommands_related.py -q`; `make check`.

- [ ] T-8.8 Manual tab
- Files: `src/leva/tui/widgets/manual_view.py`, `tests/tui/test_manual_view.py`.
- Refs: FR-5; DITS §14 (`[`/`]`); D-012 (80-column text: no soft wrap, horizontal scroll).
- Steps: sections loaded lazily; headings in accent; `[`/`]` jump between sections; scrolling with mouse wheel and keys.
- Accept: `uv run pytest tests/tui/test_manual_view.py -q`; `make check`.

- [ ] T-8.9 IngestScreen and rebuild flow
- Files: `src/leva/tui/screens/ingest.py`, `tests/tui/test_ingest_screen.py`.
- Refs: FR-1, FR-16, US-8; DITS §13–14; D-013, D-020.
- Steps:
  - The build runs in `run_worker(thread=True)`.
  - A ProgressSink adapter uses `call_from_thread` and updates at most every 50 ms; shows phases and a warnings count.
  - On success: open the library and route to the StartTarget. On error: red line + hint, and the footer stays.
  - SYSTEM_CHANGED shows a hint "system changed: press r twice to rebuild".
  - Quitting cancels the build cooperatively.
- Accept: `uv run pytest tests/tui/test_ingest_screen.py -q` (fake builder); `make check`.

- [ ] T-8.10 About screen and snapshot suite
- Files: `src/leva/tui/screens/about.py`, `tests/tui/test_snapshots.py`, `tests/tui/__snapshots__/`.
- Refs: FR-17; TEST-STRATEGY (tui snapshots).
- Steps:
  - About shows attribution, licences, versions and content_version.
  - Snapshots at 120x40 and 70x30: Search, Card (each tab), Ingest progress, About, error state, narrow screen.
  - Fixed clock, fixture index, zero debounce.
  - Review the SVGs visually (CLAUDE.md tip).
- Accept: `uv run pytest tests/tui -q`; coverage of `tui` ≥70%; `make check`.

- [ ] T-8.11 New visual conventions: placeholders and selection marker
- Blocked-by: U-2
- Files: `src/leva/tui/_format.py`, `widgets/example_list.py`, `widgets/result_list.py`, `leva.tcss`, snapshots.
- Refs: ADR-0005 conventions 1–2; FR-14; the updated design system; D-028 (placeholder display `<name>`)
- Steps:
  - `segments_to_text(segments, selected)`: placeholders in accent; in the selected example, accent + underline.
  - `>` marker in column 0 for the selected row (lists and examples).
  - Unit-test the formatter; update snapshots and review the diff.
- Accept: `uv run pytest tests/tui -q`; `make check`.

- [ ] T-8.R Phase 8 review (RC + design-system checklist "Applicare" 1–6 on every screen)
- Accept: review note; `make check`.

### Phase 9 — CLI and doctor

- [ ] T-9.1 `leva.cli`: arguments, exit codes, logging
- Files: `src/leva/cli/{__init__.py,_args.py,_logging.py}`, `pyproject.toml` (`[project.scripts] leva = "leva.cli:main"`), `tests/unit/test_cli_args.py`.
- Refs: DITS §0 (exit codes), §15; D-014.
- Steps:
  - argparse: `leva [query...]`, `--rebuild`, `--about`, `--version` (version + content_version), `doctor [--offline]`.
  - Exit codes 0/1/2/130.
  - Non-TTY TUI launch prints "leva needs an interactive terminal" and exits 2.
  - Rotating log, 1 MB × 3, in `paths.log_dir`; never on stdout.
- Accept: `uv run pytest tests/unit/test_cli_args.py -q`; `uv run leva --help` exits 0; `uv run leva --version`; `make check`.

- [ ] T-9.2 Composition root and headless rebuild
- Files: `src/leva/cli/_wiring.py`, `tests/integration/test_cli_wiring.py`, `tests/tui/test_cli_smoke.py`.
- Refs: ARCHITECTURE §3, §5; DITS §15; D-012, D-014.
- Steps:
  - Wire paths, config, sources, renderer, extractors, providers, probes and IndexBuilder.
  - Staleness: MISSING/VERSION_CHANGED → `needs_build`.
  - `open_library` factory.
  - Headless `--rebuild` with line progress on stderr; Ctrl-C → 130.
  - Smoke: `leva ls` opens the card (Pilot with the wired app on a fixture tree).
- Accept: `uv run pytest -m integration tests/integration/test_cli_wiring.py -q`; `uv run pytest tests/tui/test_cli_smoke.py -q`; `LEVA_HOME=$(mktemp -d) uv run leva --rebuild < /dev/null` exits 0; `make check`.

- [ ] T-9.3 `leva doctor`
- Files: `src/leva/cli/_doctor.py`, `tests/integration/test_doctor.py`.
- Refs: FR-20; DITS §15; D-015.
- Steps:
  - Checks: Python, SQLite/FTS5, mandoc, manpath, pbcopy, content loads (both `CuratedYamlProvider(default_root()).load()` and `TldrSnapshotProvider(default_root()).load()` drain without `ContentError`), index present/fresh/counts, versions. Counts come from `Repository.stats()` (`IndexStats(entries, man_pages, builtins, curated, examples, subcommands)`) and the versions from `Repository.meta()`; `open_readonly` raises `IndexUnavailableError` (hint `run leva --rebuild`) for a missing, unreadable or other-schema index.
  - Plain text, one check per line `ok|warn|fail name: detail`; exit 0 if no fail.
  - `--offline` per D-015.
- Accept: `uv run pytest -m integration tests/integration/test_doctor.py -q`; `LEVA_HOME=$(mktemp -d) uv run leva doctor --offline` exits 0; `make check`.

- [ ] T-9.R Phase 9 review (RC; end-to-end: build into a tmp LEVA_HOME, `leva --about`, `leva doctor`)
- Accept: review note; `make check`; `make live`.

### Phase 10 — Curated content expansion (CB for each; `make check` + `make verify` for each command)

- [ ] T-10.1 Batch 4: more, file, stat, du, df, basename, dirname, realpath, readlink, mktemp
- [ ] T-10.2 Batch 5: chmod, chown, chgrp, chflags, xattr, ditto, rsync, scp, tree
- [ ] T-10.3 Batch 6: egrep, cut, sort, uniq, tr, tee, xargs, diff, cmp, comm
- [ ] T-10.4 Batch 7: paste, join, column, fold, fmt, nl, rev, printf, echo, jq
- [ ] T-10.5 Batch 8: gunzip, bzip2, xz, hdiutil, base64, shasum, md5, cksum
- [ ] T-10.6 Batch 9: top, killall, pkill, uptime, uname, sw_vers, sysctl, system_profiler, caffeinate, pmset
- [ ] T-10.7 Batch 10: log, date, cal, time, sleep, which, whereis, type, env, crontab, lsof
- [ ] T-10.8 Batch 11: curl, ping, traceroute, netstat, ifconfig, networksetup, dig, nslookup, host
- [ ] T-10.9 Batch 12: ssh, ssh-keygen, ssh-add, sftp, nc, route, arp, scutil, openssl
- [ ] T-10.10 Batch 13: say, screencapture, plutil, osascript, mdfind, mdls, mdutil, softwareupdate, tmutil
- [ ] T-10.11 Batch 14: dscl, spctl, codesign, security, xcode-select, xcrun, sips, textutil, qlmanage
- [ ] T-10.12 Batch 15: make, clang, cc, ld, lldb, otool, nm, strings, lipo
- [ ] T-10.13 Batch 16: python3, ruby, perl, swift, swiftc, xcodebuild, man, apropos, whatis
- [ ] T-10.14 Batch 17 (builtins): alias, unalias, export, source, set, unset, read, trap, fg, bg, wait, history, jobs
- [ ] T-10.15 Batch 18 (builtins): pushd, popd, test, setopt, unsetopt, autoload, typeset, local, return, exit, eval, exec, ulimit, umask
- [ ] T-10.16 Batch 19: whoami, id, groups, sudo, su, w, who, last, passwd, tput, clear, stty, script
- [ ] T-10.17 Batch 20: dd, hexdump, xxd, od, bc, expr, seq, yes, true, false
- [ ] T-10.18 Live gold set (50 queries)
- Files: `tests/live/gold_queries.yaml`, `tests/live/test_gold_set.py`.
- Refs: PRD §7; TEST-STRATEGY (search live); D-029 (include intent queries)
- Steps: 50 realistic "forgot the command" queries spread across categories; assert ≥90% in the top 3 on `real_index`. If it fails, tune `Weights` or intents, never the queries; record the tuning in DECISIONS.
- Accept: `make live`; `make check`.
- [ ] U-5 [USER] Spot-review 10 random curated cards (`LEVA_HOME=... uv run leva <cmd>`) for accuracy. Non-blocking.
- [ ] T-10.R Phase 10 review
- Steps:
  - Content audit (`--stats`): ≥150 curated, verified ≥85%, exec ≥60%, skip <15%.
  - Re-verify everything with `make live`.
  - Fix weak entries.
- Accept: review note with metrics; `make check`; `make live`.

### Phase 11 — Performance, robustness, polish

- [ ] T-11.1 Startup performance (NFR-1)
- Files: `tools/bench_startup.py`, `tests/integration/test_startup_perf.py` (marker perf).
- Steps:
  - Run `.venv/bin/leva` in a pty with a prebuilt fixture LEVA_HOME; time until the header appears; median of 10 runs ≤300 ms.
  - If needed: lazy imports, deferring the SYSTEM_CHANGED check to a worker after the first frame (D-020).
- Accept: `uv run python tools/bench_startup.py` reports a median ≤300 ms; `make check`.

- [ ] T-11.2 Robustness edge cases (TEST-STRATEGY §3)
- Steps: tests (and fixes) for:
  - terminal resize while running; click on an empty area;
  - very long examples; `{{x}}` repeated;
  - non-UTF-8 man page; page larger than 1 MB;
  - disk full (`OSError`) during build; two simultaneous instances;
  - Ctrl-C mid-build; pbcopy absent.
- Accept: the new tests pass; `make check`.

- [ ] T-11.3 Packaging checks (NFR-15, NFR-14, D-016)
- Files: `tests/integration/test_packaging.py`.
- Steps: `uv build` into a tmp dir. Assert:
  - wheel ≤15 MB;
  - `leva/content/commands/*.yaml`, `tldr/*.jsonl`, `ATTRIBUTION.md`, `leva.tcss` and migrations are present;
  - no `leva/verify`; no man pages.
- Accept: `uv run pytest -m integration tests/integration/test_packaging.py -q`; `make check`.

- [ ] T-11.4 CI workflow (manual trigger only, D-023) and Python 3.11 run
- Files: `.github/workflows/ci.yml`, Makefile `py311`.
- Steps:
  - Jobs: lint, type, arch, test on ubuntu and macOS; live on macOS; `on: workflow_dispatch` only.
  - `make py311` = `UV_PROJECT_ENVIRONMENT=.venv-py311 uv run --python 3.11 pytest -q`.
- Accept: `make py311` passes; the workflow parses as YAML (test); `make check`.

- [ ] U-6 [USER] Decide whether to enable push/PR triggers for CI (GitHub Actions minutes cost; macOS runners bill at 10x). Non-blocking.

- [ ] T-11.5 Documentation
- Files: `README.md`, `LICENSE-CONTENT` (path wording `src/leva/content/`), `docs/CONTENT-GUIDE.md`.
- Steps: status, features, keys table, usage, install from source (documented only, not executed), development commands, content authoring, licences/attribution.
- Accept: README covers every CLI flag and every binding in DITS §14; `make check`.

- [ ] T-11.R Phase 11 review (RC on everything touched)
- Accept: review note; `make check`.

- [ ] T-FINAL Full quality gate
- Steps:
  1. Run `make check` (ruff check, ruff format --check, `mypy --strict` on src+tools, `lint-imports`, arch tests, pytest non-live with the coverage gates).
  2. Run `make live`: ingest coverage, curated examples, gold set ≥90%, clipboard round trip.
  3. Run `make py311`.
  4. Run the packaging test.
  5. Run `uv run leva --help` (exit 0), `uv run leva --version`, and `LEVA_HOME=$(mktemp -d) uv run leva --rebuild </dev/null && LEVA_HOME=<same> uv run leva doctor` (exit 0).
  6. `grep -rnE 'TODO|FIXME|XXX|NotImplementedError' src tools tests` finds nothing.
  7. Check that `docs/design/design-system-snapshot.md` equals the external file.
  8. Write `docs/design/leva-sh/reviews/final.md`: metrics vs PRD §7, coverage table, open `[USER]` tasks, and tasks blocked by them.
- Accept: every step passes and final.md exists. If a previously blocked task completes after T-FINAL, re-run steps 1–7 in that iteration.

## Appendix A — Seed for DECISIONS.md (binding)
- **D-001 Language.** Code, comments, docstrings, UI strings and content are in English. Existing design docs stay in Italian. New docs (CLAUDE.md, DECISIONS, spikes, reviews, README) are in English.
- **D-002 Packages and layers.** Every module is a package `leva.<pkg>`. Private submodules use a `_` prefix; other packages import only from the package root.
- Corrected edges:
  - `subcmd → manparse` (ParsedMan, `definition_items`);
  - `clipboard → model` (ClipboardError);
  - `tui → paths`, `tui → model`;
  - new leaf `config → model`.
- `sources.BuiltinSource` is dropped. Builtins are derived in ingest from the already-parsed zshbuiltins(1) and bash(1) (first in manpath order) via `manparse.extract_builtins`. Origins ZSH and BASH.
- Layers, top to bottom (import-linter, `containers=["leva"]`, exhaustive):
  1. `cli | verify`
  2. `tui`
  3. `library | ingest`
  4. `search | sources | subcmd | content | store`
  5. `repo | manparse | config | paths | placeholders | clipboard`
  6. `model`
- Forbidden contracts:
  - no runtime package imports `verify`;
  - `tui` must not import store, repo, search, sources, manparse, subcmd, content or config.
- Stdlib restrictions are enforced by AST arch tests (T-0.3).
- **D-003 Config.** `leva.config` reads TOML at `LevaPaths.config_file` (`<data_dir>/config.toml`). Keys: `sections`, `extra_man_paths`, `extra_bin_dirs`. Errors are `ConfigError(LevaError)`. Its `digest()` is part of the fingerprint. NB-6, NB-7 and NB-8 take the PRD defaults (sections 1 and 8; arm64 + x86_64; macOS ≥13; Python ≥3.11).
- **D-004 Discovery and origin.**
- Bin dirs, in order: `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`, `/bin`, `/usr/sbin`, `/sbin`, then `extra_bin_dirs`.
- Man dirs: `manpath` output order + `/opt/homebrew/share/man` + `/usr/local/share/man` + `extra_man_paths` (deduplicated, missing dirs ignored).
- Origin: HOMEBREW if the path is under `/opt/homebrew` or `/usr/local`, else MACOS.
- **D-005 Entry catalog.**
- Man pages: one entry per (name, section); the first in man-dir order wins (`man` semantics). The CLT SDK copy is dropped. Origin comes from the dir. `ManFile` carries `name` and `dir_index`.
- `.so` stubs never become entries: they add an alias on the target entry.
- NAME-line names add aliases.
- Executables:
  - `path` = first executable of that name in bin-dir order, set on every man entry with that name;
  - an executable whose name resolves via an alias attaches to that entry;
  - otherwise it becomes an exe-only entry (name, None, origin), `has_man=0`, summary "".
- Builtins: entries (name, None, ZSH|BASH), `kind=builtin`, `has_man=1`. Sections: SYNOPSIS (the term lines) and DESCRIPTION.
- Rank per name: sort by (not curated, not has_man, section order 1 < 8 < other < None, kind executable/manpage before builtin, origin zsh < bash, id); rank 0 is the primary.
- Curated attachment targets the best entry for (name[, section]) using the same key without "curated", then everything is re-ranked.
- `Repository.get_entry(name, section=None)`: exact name match by rank, else alias match ordered by (rank, name, id). `section=None` means any section.
- **D-006 Schema refinements.** Unique index on `entry(name, IFNULL(section,''), origin)`. Add `entry.rank INT` and `subcommand.body TEXT`. FTS5 is contentless, filled at finalize. Unchanged otherwise.
- **D-007 Rendering.** `.so` stubs are detected from the roff source (gz-aware) before rendering. Overstrike is stripped in Python (no `col` subprocess). Output is `mandoc -T ascii -O width=80`. Status: confirm in S-2.
- **D-008 Subcommands.**
- `known: Mapping[str, KnownPage(name, summary, synopsis)]` replaces `Mapping[str, Entry]`.
- Hyphen rule: page `P-s` is a subcommand of P only if its SYNOPSIS starts with `P s`.
- Section lists: headings matching `(SUB)?COMMANDS|VERBS`, excluding `CUSTOM EXTERNAL COMMANDS`. Terms whose first token matches `^[a-z][a-z0-9_.-]*$`.
- Merge by name with priority curated > probe > section > hyphen, per field (summary, body, entry_name = first non-empty). Union of names, sorted.
- **D-009 Probes.**
- Allowlist built only from curated `help_probe: {args: [...], profile: two-col|git-list|brew-commands}`. The binary resolves to the first scanned executable.
- env: `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, HOME and cwd in a temp dir, `LC_ALL=LANG=en_US.UTF-8`, `LANGUAGE=en`, `NO_COLOR=1`, `TERM=dumb`, `HOMEBREW_NO_AUTO_UPDATE=1`, `HOMEBREW_NO_ANALYTICS=1`, `HOMEBREW_NO_ENV_HINTS=1`.
- stdin devnull; 5 s timeout; 256 KiB cap.
- Exit status is ignored (`defaults` exits 255, `diskutil` exits 1). Text = stdout, else stderr. Failure = spawn error, timeout or empty output.
- **D-010 Content and search API details.** The curated schema is strict: unknown keys are errors, `name` must equal the file stem, `help_probe` is a mapping. `SearchResult` adds `section`, `kind`, `origin`. For FTS hits, `why` = intent or summary if a query token occurs there (in memory), else body.
- **D-011 Library.**
- `close()`.
- `attribution()` reads `meta['attribution']`, which ingest writes from `content.attribution_text()`.
- A subcommand without its own page gets a synthesized Card: parent entry, breadcrumb (parent, sub), sections = [sub body], examples = the parent's examples whose plain cmd starts with `parent sub`.
- History: max 50, opening after going back truncates forward.
- Example duplicate key: whitespace collapsed + every placeholder replaced by `{}`; the curated example wins.
- **D-012 TUI composition.**
- `LevaApp(open_library: Callable[[], Library], clipboard, builder, start, paths, needs_build)`, so a first run can build before any library exists.
- `StartTarget.kind` gains `"query"`, resolved in-app (exact name/alias → card, else prefilled search).
- `CardView` is reused by CardScreen and by SearchScreen's right pane at ≥100 cols.
- Manual text keeps its 80-column layout: no soft wrap, horizontal scroll.
- Theme per S-1: `ansi=True`, `ansi_default` backgrounds, palette hex colours.
- **D-013 Rebuild confirmation.** Press `r` twice within 3 s (status-line hint) instead of a modal: the design system forbids confirmation dialogs for non-destructive operations. Also `placeholders.problems()` is added for strict content validation.
- **D-014 TTY.** Only TUI launches require a TTY (exit 2 otherwise). `--help`, `--version`, `--about`, `doctor` and `--rebuild` (headless, line progress on stderr) work without one.
- **D-015 Doctor.** `--offline` runs only the checks that need neither system man pages nor an index (Python, SQLite/FTS5, content loads, versions). It is the brew `test do` mode.
- **D-016 Verification safety.**
- `src/leva/verify` is excluded from the wheel and has no console script; run it as `uv run python -m leva.verify` (NFR-11).
- exec mode runs under `sandbox-exec`: deny network, deny writes outside the example sandbox, deny signals to other processes. It fails closed when sandbox-exec is missing.
- Content validation rejects exec for the denylist: sudo, su, doas, shutdown, reboot, halt, diskutil, hdiutil, launchctl, defaults, pmset, networksetup, scutil, softwareupdate, tmutil, systemsetup, kill, killall, pkill, crontab, ssh, ssh-add, ssh-agent, scp, sftp, curl, ping, traceroute, dig, nslookup, host, nc, open, osascript, say, screencapture, pbcopy, pbpaste, security, xcode-select, mdutil, mdfind, spctl, dscl, passwd, login, brew, softwareupdate.
- **D-017 tldr.** Vendor `common` + `osx` (English) from the release zip; the osx page replaces the common page. Normalise `{{[-x|--long]}}` to `-x` and strip mnemonic brackets. Index examples with `source="tldr"`, `verified="none"`: Leva does not verify them. A static check of tldr examples is a non-blocking live report.
- **D-018 Hypothesis.** `derandomize=True` always. Regressions are pinned with `@example`. `.hypothesis/` is gitignored.
- **D-019 Coverage.** TEST-STRATEGY targets + an 85% floor for other packages and overall, branch coverage, enforced by `tools/coverage_gate.py`.
- **D-020 Staleness.** A missing, corrupt or unreadable index means MISSING. MISSING and VERSION_CHANGED trigger an automatic blocking build; SYSTEM_CHANGED shows a hint only, and may be computed after the first frame for NFR-1.
- **D-021 Curated not installed.** A curated command with no matching entry on this Mac is skipped and reported in `BuildReport.skipped`.
- **D-022 Build API.** `build(target, progress, *, cancel=None)` with cooperative cancellation; `fcntl.flock` on `index.lock`; a stale `.new` file is removed at start; `IndexBuilder` receives `config_digest` and `clock`.
- **D-023 CI.** The workflow is committed with `workflow_dispatch` only, so no Actions minutes are used until the user enables triggers (U-6).
- **D-024 Spikes and reviews.** Findings live in `docs/design/leva-sh/spikes/`, reviews in `docs/design/leva-sh/reviews/`. Spike code lives in `spikes/`: ruff-checked, excluded from mypy and coverage, never imported by src.
