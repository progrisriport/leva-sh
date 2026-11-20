# CLAUDE.md — Leva (`leva-sh`)

Leva is a macOS terminal encyclopedia of shell commands: a Textual TUI over a local
SQLite+FTS5 index built from the installed man pages, executables and shell builtins, plus
curated YAML content and a vendored tldr-pages snapshot. CLI command: `leva`.

## Project and docs map

Binding order when sources disagree: `PLAN.md` §3–4 (process) > `DECISIONS.md` > design docs.

| Doc | Purpose |
|---|---|
| `PLAN.md` | Task list, global rules R1–R10, gate commands, coverage gates, review checklist RC, content batch procedure CB |
| `docs/design/leva-sh/DECISIONS.md` | Binding refinements D-001.. of the design docs (append or amend only) |
| `docs/design/leva-sh/PRD.md` | Problem, user stories, FR/NFR, success metrics (§7) |
| `docs/design/leva-sh/ARCHITECTURE.md` | C4 views, modules, data flow, contracts, extension points |
| `docs/design/leva-sh/DESIGN-IN-THE-SMALL.md` (DITS) | Signatures, pre/post conditions, errors, naming (§0) |
| `docs/design/leva-sh/DESIGN-PATTERNS.md` | Pattern per module and cross-cutting patterns |
| `docs/design/leva-sh/TEST-STRATEGY.md` | Test pyramid, per-module tests, edge cases (§3), determinism (§5) |
| `docs/design/leva-sh/ANALYSIS.md` | Risks, dependencies, initial curated command list, spikes |
| `docs/design/leva-sh/ADR/ADR-0001..0006` | Stack, man ingest, storage, curated content, TUI, distribution |
| `docs/design/leva-sh/spikes/` | Spike findings (S-1, S-2, S-3, NB-3); spike code lives in `spikes/` |
| `docs/design/leva-sh/reviews/` | Phase reviews `phase-N.md`, `ingest-live.md`, `final.md` |
| `docs/design/design-system-snapshot.md` | Repo copy of the external Flosh TUI design system |
| `docs/CONTENT-GUIDE.md` | Guide for curated content authors (created in T-7.4) |
| `.ralph/PROGRESS.md` | Iteration log of the autonomous loop; read the tail before starting |

## Language

- Code, identifiers, comments, docstrings, log messages, UI strings and curated content: English (D-001).
- Existing design docs (PRD, ARCHITECTURE, DITS, DESIGN-PATTERNS, TEST-STRATEGY, ANALYSIS, ADRs) stay in Italian.
- New docs (this file, DECISIONS, spikes, reviews, README, CONTENT-GUIDE): English.
- UI status messages are lowercase: `copied: ls -la`, `clipboard unavailable`.

## Architecture

Every module is a package `leva.<pkg>` with a single responsibility (D-002):

| Package | Single responsibility |
|---|---|
| `model` | Immutable shared domain types (`Entry`, `Section`, `Example`, `Note`, `Subcommand`, `Origin`, `Kind`) and the `LevaError` hierarchy |
| `paths` | Resolve data, config and log locations from an injected env and home (no I/O) |
| `placeholders` | Parse `{{name}}` placeholders in example commands |
| `clipboard` | Copy text to the system clipboard (`Clipboard` port, `PbcopyClipboard`, `FakeClipboard`) |
| `config` | Load and validate `config.toml` into `LevaConfig`; provide its digest |
| `sources` | Read raw material from the OS: executables, man files, `SystemInfo`, allowlisted help probes |
| `manparse` | Render man pages (`ManRenderer`, `MandocRenderer`) and parse them into sections, NAME, definition lists, builtins |
| `subcmd` | Extract subcommands from parsed man pages and help text, and merge them |
| `content` | Load and strictly validate curated YAML and the tldr snapshot; content version; attribution |
| `store` | Own the versioned SQLite schema and the only index writer (`IndexWriter`, `open_readonly`) |
| `repo` | Typed read-only queries over the index (`Repository`) |
| `search` | Rank search results (`Searcher`, `SearchResult`) |
| `library` | High-level read API for the UI (`Library`, `Card`, history) |
| `ingest` | Orchestrate building the index (`IndexBuilder`, staleness, `ProgressSink`, `BuildReport`) |
| `tui` | Present the library in a Textual app (`LevaApp`, screens, widgets, theme) |
| `cli` | Composition root: parse arguments, wire dependencies, run the app, headless rebuild, `doctor` |
| `verify` | Dev-only: verify curated examples in an OS sandbox (never shipped, never imported by runtime) |

Layer contract (import-linter, `containers=["leva"]`, exhaustive), top to bottom. A package may
import only from lower layers; packages separated by `|` are independent of each other:

1. `cli | verify`
2. `tui`
3. `library | ingest`
4. `search | sources | subcmd | content | store`
5. `repo | manparse | config | paths | placeholders | clipboard`
6. `model`

Forbidden: any runtime package importing `verify`; `tui` importing store, repo, search, sources,
manparse, subcmd, content or config. `tui` talks only to `Library`, `Clipboard`, the ingest
builder, `paths`, `model` and `placeholders`. There is no `sources.BuiltinSource`: builtins come
from `manparse.extract_builtins` in ingest (D-002).

Stdlib restrictions (AST arch tests in `tests/arch/`): `subprocess` only in clipboard, sources,
manparse, verify; `sqlite3` only in store, repo, cli; `os.environ`/`os.getenv`/`os.putenv` only
in cli; no socket/urllib/http/ssl/ftplib/smtplib anywhere in `src`; `print(` only in `cli` and
`verify/__main__.py`; `leva.X._private` imported only from inside `leva.X`.

## Coding conventions

- Target Python ≥3.11 (develop on 3.13): no 3.12+ syntax or stdlib APIs (no `type` statements,
  no PEP 695 generics, no `itertools.batched`). Every module starts with
  `from __future__ import annotations`.
- Domain types are `@dataclass(frozen=True, slots=True)`. Ports are `typing.Protocol` named by role
  (`Clipboard`, `ManRenderer`, `ContentProvider`, `SubcommandExtractor`, `ProgressSink`); adapters
  carry a technology prefix (`PbcopyClipboard`, `MandocRenderer`, `CuratedYamlProvider`).
- Invariant violations (programmer errors) raise `ValueError` from `__post_init__` or the function.
  User-facing failures raise `LevaError` subclasses (`message` short and displayable, optional
  `hint`). Only `LevaError` crosses package boundaries; wrap third-party errors
  (`sqlite3`, `yaml`, `subprocess`, `OSError`) with `raise XError(...) from exc`.
- No global mutable state. Env, clock, paths and system info are injected; `os.environ` is read
  only in `leva.cli`.
- Package layout: every module is a package; private submodules start with `_`; the package
  `__init__.py` re-exports the public API and other packages import only from the package root.
- Logging: `logging.getLogger("leva.<pkg>")`. Never `print` in `src` except `cli` and
  `verify/__main__.py`; never log to stdout while the TUI runs.
- Naming per DITS §0: short noun modules, `PascalCase` classes, verb-first functions
  (`parse_man`, `locate`), `UPPER_SNAKE` constants.
- Small functions (ruff C901 ≤10), no duplication, no `Any` in public APIs, no unjustified `cast`.
- `mypy --strict` on `src` and `tools`. Every `# type: ignore[code]` or `# noqa: CODE` carries the
  code and a one-line reason.
- No TODO/FIXME/XXX, no `NotImplementedError`, no placeholder bodies, no stubs.
- Module docstring states the single responsibility; public items have Google-style docstrings
  with pre/post conditions where DITS gives them.

## Testing conventions

- TDD: write the failing test first, run it, implement the minimum, refactor. Tests assert
  behaviour, including negative and edge cases (TEST-STRATEGY §2–3); "no exception" alone is
  not a test.
- Layout: `tests/unit`, `tests/integration`, `tests/tui`, `tests/live`, `tests/arch`,
  `tests/support`, `tests/fixtures`. Names: `test_<module>.py`, `test_<behaviour>_<condition>`.
- Markers (strict): `integration`, `tui`, `macos_live`, `perf`, `clipboard`, `quarantine`.
  Directory markers are auto-applied: `tests/integration` → `integration`, `tests/tui` → `tui`,
  `tests/live` → `macos_live`. Default runs exclude `macos_live`.
- Fixtures are synthetic and written by us. Never copy third-party man pages, help output or
  tldr prose into the repo.
- The autouse `clean_env` fixture sets `LEVA_HOME=<tmp>`, `HOME=<tmp>/home`, `TZ=UTC`,
  `LC_ALL=LANG=en_US.UTF-8`, `LANGUAGE=en`, `MANWIDTH=80`, `COLUMNS=120`. Tests never read the real `~`.
- Network is blocked by pytest-socket (`--disable-socket --allow-unix-socket`); only the
  verify sandbox test may use `@pytest.mark.enable_socket` against a test-owned 127.0.0.1 listener.
- Hypothesis profile `leva`: `derandomize=True`, `deadline=None`, `print_blob=True`, loaded in
  conftest. Pin regressions with `@example`.
- Deterministic tests only: no sleeps, injected clocks, zero debounce in TUI tests, sorted
  iteration. A flaky test goes to `quarantine` with a reason and an expiry; never skip tests to go green.
- TUI tests use Textual `Pilot` (`async with app.run_test(size=...) as pilot`). Snapshots
  (pytest-textual-snapshot) at fixed sizes with the fixture index; update only with
  `--snapshot-update` and review every changed SVG.
- Viewing an SVG snapshot: `qlmanage -t -s 1600 -o <tmpdir> file.svg`, then read the PNG.
- Coverage (branch, D-019): ≥90% for placeholders, content, manparse, store, repo, search,
  ingest; ≥70% for tui; ≥85% for every other package and overall (`tools/coverage_gate.py`).

## TUI rules

Binding source: `/Users/flosh/Desktop/Coding.nosync/Progetti/PyDF Tool/CLAUDE.md` (read it before
any TUI change; never edit it). Repo copy: `docs/design/design-system-snapshot.md`. Leva-specific
decisions: ADR-0005, D-012, D-013, S-1 findings.

- Palette (the only colours allowed):

  | Role | Hex |
  |---|---|
  | accent | `#E8B84B` |
  | text | `#D4D4D4` |
  | secondary | `#7A7A7A` |
  | border | `#3A3A3A` |
  | error | `#E85B4B` |
  | success | `#4BE87A` |
  | `$surface` / `$surface-soft` (S-1 fallback only) | `#1A1A1A` / `#202020` |

- Background is the terminal's own: no `background` anywhere except the resets and the neutral
  `$surface` fallback documented by S-1.
- Borders are Textual `solid` (box-drawing `┌ ┐ └ ┘ │ ─`); box titles via `border_title` in accent.
  No `round`, `heavy`, `double` or ASCII borders.
- Every screen (including error, progress and "terminal too narrow") has the header box
  (`Leva` bold accent, tagline "less effort, more thought" in secondary) and the footer
  (`─` separator + "key desc" pairs in secondary).
- One accent colour per screen. Bold only for the selected item.
- Feedback is one line: success in green (`copied: <cmd>`), error in red, no stack traces.
  No confirmation dialogs for non-destructive operations (rebuild = press `r` twice, D-013).
- No emoji, no icons: text and box-drawing only.
- Colours are defined only in `src/leva/tui/theme.py` and `src/leva/tui/leva.tcss`; no inline colours in widgets.
- Every mouse action has a keyboard equivalent. Layout: ≥100 cols two panes, 60–99 single pane,
  below 60x12 the "terminal too narrow (min 60 cols)" screen.
- New visual conventions (placeholder highlighting, `>` selection marker) only after the design
  system documents them (U-2, then T-8.11).

## Content authoring rules

- One file per command: `src/leva/content/commands/<name>.yaml`, `schema: 1`, `kind: command`,
  `name` equal to the file stem; strict schema (unknown keys are errors, D-010).
- Follow the content batch procedure CB in `PLAN.md` §4: read the local man page
  (`mandoc -T ascii <path> | col -bx`), write original text (summary ≤120 chars, explain 2–6
  sentences, 3–8 intents, notes checked against the macOS man page, 3–8 examples each with
  `verify`, 2–6 related), then `make verify CMD=<name>` must pass.
- Verify modes: prefer `exec` with fixtures created by `setup` inside the sandbox; `static` for
  commands on the exec denylist (D-016) or nondeterministic output; `skip` with `reason` only for
  destructive or privileged examples. Targets: exec ≥60%, skip <15% (cumulative, `--stats`).
- Licensing: curated content is CC BY 4.0 (`LICENSE-CONTENT`), code is MIT (`LICENSE`). Never copy
  man page or tldr prose. tldr data enters only through `tools/vendor_tldr.py` with
  `SOURCE.json` and `ATTRIBUTION.md` (D-017).

## Safety rules

From `PLAN.md` R8; never violate:

- No `sudo`. Never modify files outside this repo or the system temp dir.
- Never edit `/Users/flosh/Desktop/Coding.nosync/Progetti/PyDF Tool/CLAUDE.md`.
- Never touch the real `~/Library/Application Support/leva` or `~/Library/Logs/leva`; every
  manual run uses `LEVA_HOME=$(mktemp -d)`.
- Never run curated example commands except through `leva.verify`.
- No installs outside `uv` into the project env; no brew installs.
- Network only for `uv lock/sync/add` and the explicit tldr vendoring task (T-7.2).
- No force-push or history rewrite; never change the repo's visibility or remotes.
- No PyPI or brew publishing.

## Commands

| Command | What it does |
|---|---|
| `make check` | `uv lock --check`, `ruff check .`, `ruff format --check .`, `mypy`, `lint-imports`, `pytest` (non-live, coverage), `tools/coverage_gate.py` |
| `make lint` / `make fmt` / `make type` / `make arch` | ruff check / ruff format / mypy strict / import-linter |
| `make test` / `make cov` | pytest (non-live) / pytest with coverage and the coverage gate |
| `make live` | `pytest -m macos_live` on this Mac |
| `make verify CMD=<name>` | headless rebuild into `.cache/leva`, then `uv run python -m leva.verify --index .cache/leva/index.db --command <name>` |
| `make py311` | test suite on Python 3.11 in `.venv-py311` |
| `uv run pytest <path> -q` | run selected tests |
| `LEVA_HOME=$(mktemp -d) uv run leva ...` | manual run with an isolated data dir |

## Git rules

From `PLAN.md` R5–R7:

- One task per commit. First line `T-x.y: <title>` (or `repair: <what>` for fixing a red tree
  before a task); the body lists the tests and commands run. No other trailers: never
  `Co-Authored-By`, "Generated with" or any AI attribution. Commits use the user's git identity.
- The task's box in `PLAN.md` is ticked `[x]` in the same commit, together with the
  `.ralph/PROGRESS.md` entry and any DECISIONS.md entry for intentional refinements.
- Before committing: `ruff format .`, `make check` green, and a full read of `git diff` as a strict reviewer.
- Then `git push origin HEAD:main`; if it fails twice, note it and continue.
- Splits follow R6 (`T-x.y.1` ticked, `T-x.y.2` open); blocked tasks follow R7 (`[!]`,
  `BLOCKED <date>` line, a `[USER]` task, docs-only commit).
