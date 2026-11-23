# DECISIONS — Leva

- Project: Leva (`leva-sh`) · Created: 2026-11-21 · Status: binding
- Related: [PRD](PRD.md) · [ARCHITECTURE](ARCHITECTURE.md) · [DESIGN-IN-THE-SMALL](DESIGN-IN-THE-SMALL.md) · [TEST-STRATEGY](TEST-STRATEGY.md) · [DESIGN-PATTERNS](DESIGN-PATTERNS.md) · [ANALYSIS](ANALYSIS.md) · [PLAN](../../../PLAN.md)

This file holds the binding refinements of the design docs. Where an entry here differs from
PRD, ARCHITECTURE, DESIGN-IN-THE-SMALL, TEST-STRATEGY or an ADR, this file wins.

Rules for editing this file:

- Entries are only appended (next free `D-NNN`) or amended. Nothing is deleted or renumbered.
- Every amendment is written under the entry it changes as `- Amended <YYYY-MM-DD>: <change>. Reason: <why>.`
- Every new entry states its date and reason on its first line.
- Design docs are never silently contradicted: if a decision changes a fact they state, the
  decision says so explicitly.

## Seed decisions (D-001..D-024, from PLAN.md Appendix A, 2026-11-21)

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
- Amended 2026-11-21: `manpath` runs with the user's `PATH` and `MANPATH` (injected from `leva.cli`) plus the fixed locale variables; the extras are still appended after its output. Reason: S-2 finding 12. With a minimal PATH, `manpath` omits the Homebrew dirs, so the CLT `git(1)` would beat the Homebrew one, whose binary wins the bin-dir order.
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
- Amended 2026-11-21: the winner per (name, section) is chosen over all copies in man-dir order, stubs included. Then a winning stub is handled by its target:
  - target's (name, section) is an entry: the stub adds an alias on it;
  - target resolves outside every man dir: the stub is rendered as itself (mandoc follows the `.so` from the man root, D-007) and indexed under its own name;
  - target missing: the stub is skipped and counted.
  Targets resolve against the man root, then against the page's dir, gz-aware; `..` paths are allowed. The section is the directory's; files whose extension does not start with it are skipped. Reason: S-2 findings 2–3. `rsync(1)` is a stub to openrsync(1) and must shadow the SDK's unrelated real page; 58 Xsan stubs point outside the man dirs.
- **D-006 Schema refinements.** Unique index on `entry(name, IFNULL(section,''), origin)`. Add `entry.rank INT` and `subcommand.body TEXT`. FTS5 is contentless, filled at finalize. Unchanged otherwise.
- Amended 2026-11-22: confirmed by S-3. FTS5 with `unicode61 remove_diacritics 2`, a contentless table with `bm25` weights and the `IFNULL` unique index work on SQLite 3.45.1 to 3.54.0; the full prototype index is 41.05 MB (45.51 MB before `VACUUM`), against NFR-15's 100 MB. Additions:
  - `'rebuild'` is rejected on a contentless table, so finalize inserts the `search_fts` rows itself (explicit `rowid = entry.id`, in id order). This replaces the "FTS rebuild" wording of DITS §9;
  - finalize runs `INSERT INTO search_fts(search_fts) VALUES('optimize')` after the fill (it works inside an open transaction too);
  - `open_readonly` builds the URI with `Path.as_uri() + "?mode=ro"` (a raw `file:{path}` breaks on `#`) and runs `PRAGMA user_version` before returning, because a missing file fails at `connect` but a corrupt file fails only at the first query; every `sqlite3.Error` becomes IndexUnavailableError.
  Reason: S-3 findings 3, 4, 6 and 7.
- **D-007 Rendering.** `.so` stubs are detected from the roff source (gz-aware) before rendering. Overstrike is stripped in Python (no `col` subprocess). Output is `mandoc -T ascii -O width=80`. Status: confirm in S-2.
- Amended 2026-11-21: confirmed by S-2. Python stripping equals `col -bx` on 2598 of 2598 pages. The output is pure ASCII, and a glyph mandoc cannot transliterate becomes `<?>`. Width 80 is a target, not a limit: 375 pages have longer lines. Additions:
  - mandoc runs with cwd = the page's man root (the parent of `man<sec>/`), so `.so` requests resolve as they do for `man`;
  - mandoc exits 0 for empty, garbage or `.so`-broken input, so an output with no non-blank line between the header and footer raises ManRenderError, as a non-zero exit or a timeout does;
  - `stub_target` returns the raw `.so` path.
  This replaces the `col -bx` step of ADR-0002 §3. Reason: S-2 findings 1, 2 and 4–6.
- **D-008 Subcommands.**
- `known: Mapping[str, KnownPage(name, summary, synopsis)]` replaces `Mapping[str, Entry]`.
- Hyphen rule: page `P-s` is a subcommand of P only if its SYNOPSIS starts with `P s`.
- Section lists: headings matching `(SUB)?COMMANDS|VERBS`, excluding `CUSTOM EXTERNAL COMMANDS`. Terms whose first token matches `^[a-z][a-z0-9_.-]*$`.
- Merge by name with priority curated > probe > section > hyphen, per field (summary, body, entry_name = first non-empty). Union of names, sorted.
- Amended 2026-11-21: "headings matching" means a full match of the whole heading text. Every section with a matching heading is scanned, repeated headings included (launchctl has two `SUBCOMMANDS`). Reason: S-2 finding 11. A substring search would also take `OPTIONS INHERITED FROM PARENT COMMANDS` (88 gh pages) and `SHELL BUILTIN COMMANDS`.
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
- Amended 2026-11-22: the theme must also define `ansi-background` and `ansi-foreground` (`ansi_default`) and the `block-cursor-*`, `input-cursor-*`, `*-selection-*`, `border*` and `scrollbar*` variables, and the stylesheet overrides `Input` (`solid` border, cursor and placeholder rules), `OptionList` highlight, `Tabs` (underline hidden), `Tab`, scrollbars and `Toast`; the only `background:` value is `ansi_default`, and no widget needs the `#1A1A1A`/`#202020` fallback. The exact Theme and TCSS are in `spikes/S-1-textual-background.md` ("Recommended theme/CSS"). Reason: S-1 findings 1, 2, 4, 5, 6, 7, 8.
- **D-013 Rebuild confirmation.** Press `r` twice within 3 s (status-line hint) instead of a modal: the design system forbids confirmation dialogs for non-destructive operations. Also `placeholders.problems()` is added for strict content validation.
- **D-014 TTY.** Only TUI launches require a TTY (exit 2 otherwise). `--help`, `--version`, `--about`, `doctor` and `--rebuild` (headless, line progress on stderr) work without one.
- **D-015 Doctor.** `--offline` runs only the checks that need neither system man pages nor an index (Python, SQLite/FTS5, content loads, versions). It is the brew `test do` mode.
- **D-016 Verification safety.**
- `src/leva/verify` is excluded from the wheel and has no console script; run it as `uv run python -m leva.verify` (NFR-11).
- exec mode runs under `sandbox-exec`: deny network, deny writes outside the example sandbox, deny signals to other processes. It fails closed when sandbox-exec is missing.
- Content validation rejects exec for the denylist: sudo, su, doas, shutdown, reboot, halt, diskutil, hdiutil, launchctl, defaults, pmset, networksetup, scutil, softwareupdate, tmutil, systemsetup, kill, killall, pkill, crontab, ssh, ssh-add, ssh-agent, scp, sftp, curl, ping, traceroute, dig, nslookup, host, nc, open, osascript, say, screencapture, pbcopy, pbpaste, security, xcode-select, mdutil, mdfind, spctl, dscl, passwd, login, brew, softwareupdate.
- Amended 2026-11-22: the denylist is the set of the names above; `softwareupdate` appears twice, so it has 47 distinct names. Reason: Phase 0 review F-5.
- **D-017 tldr.** Vendor `common` + `osx` (English) from the release zip; the osx page replaces the common page. Normalise `{{[-x|--long]}}` to `-x` and strip mnemonic brackets. Index examples with `source="tldr"`, `verified="none"`: Leva does not verify them. A static check of tldr examples is a non-blocking live report.
- **D-018 Hypothesis.** `derandomize=True` always. Regressions are pinned with `@example`. `.hypothesis/` is gitignored.
- **D-019 Coverage.** TEST-STRATEGY targets + an 85% floor for other packages and overall, branch coverage, enforced by `tools/coverage_gate.py`.
- **D-020 Staleness.** A missing, corrupt or unreadable index means MISSING. MISSING and VERSION_CHANGED trigger an automatic blocking build; SYSTEM_CHANGED shows a hint only, and may be computed after the first frame for NFR-1.
- **D-021 Curated not installed.** A curated command with no matching entry on this Mac is skipped and reported in `BuildReport.skipped`.
- **D-022 Build API.** `build(target, progress, *, cancel=None)` with cooperative cancellation; `fcntl.flock` on `index.lock`; a stale `.new` file is removed at start; `IndexBuilder` receives `config_digest` and `clock`.
- **D-023 CI.** The workflow is committed with `workflow_dispatch` only, so no Actions minutes are used until the user enables triggers (U-6).
- **D-024 Spikes and reviews.** Findings live in `docs/design/leva-sh/spikes/`, reviews in `docs/design/leva-sh/reviews/`. Spike code lives in `spikes/`: ruff-checked, excluded from mypy and coverage, never imported by src.

## Later decisions

- **D-025 Arch rule scope (2026-11-21).** Reason: the D-002 stdlib restrictions name modules, but the same capability is reachable through neighbouring names; the AST checker in `tests/arch/rules.py` closes those gaps. It resolves every import, every dotted attribute chain rooted at an imported name, and every builtin reference to a qualified name, then:
  - `subprocess` also covers `asyncio.subprocess`, `asyncio.create_subprocess_exec` and `asyncio.create_subprocess_shell` (`os.system`/`os.popen`/`os.spawn*` are already rejected by ruff `S605`/`S606`);
  - the environment rule also covers `os.environb`, `os.getenvb` and `os.unsetenv`;
  - the print rule flags any reference to the builtin `print` (also `builtins.print`), not only calls;
  - the private-import rule flags any `leva.X.<..._private...>` path used outside `leva.X`, including private attributes reached through an imported name (`Store._cache`) and relative imports. Dunder names (`__main__`, `__version__`) are not private.
  - Amended 2026-11-22: a `dev-code` rule rejects any use of `spikes`, `tests` or `tools` from src (D-024 "never imported by src"). Reason: Phase 0 review F-4.
- **D-026 Coverage gate details (2026-11-21).** Reason: D-019 leaves the arithmetic and edge cases open. `tools/coverage_gate.py` computes coverage as coverage.py does with branch coverage, (covered lines + covered branches) / (statements + branches), summed per top-level package; compares exactly (no rounding) and displays rounded down; gates the root `leva/__init__.py` as package `leva` at 85%; gates `overall` at 85% over all packages with statements; exits 2 when the report is unreadable, lacks branch data or has malformed summaries.
- **D-027 Rendered man text layout (2026-11-21).** Reason: S-2 measured the `mandoc -T ascii` layout on 2598 pages, and parts of ADR-0002 §4 and T-2.5 assumed uppercase headings. This changes ADR-0002 §4 ("intestazione a colonna 0 in maiuscolo").
  - The header and footer are the first and last non-blank lines. They are dropped without matching any pattern (41 headers do not match `TITLE(SEC) volume TITLE(SEC)`).
  - A heading is any other column-0 line that contains at least one letter, in any case (`Sed Addresses`, `Incompatible Changes`, `Name`). Column-0 lines without letters (`____` rules) are body text. Lines at indent 3 are subsection headings and stay in the body.
  - NAME is found without regard to case. A page without NAME keeps `name_hint` as its only name. A NAME without a separator yields an empty summary.
  - Section bodies start at indent 5. Definition lists use per-page indents: first-level terms sit at the minimal indent of the body, descriptions at the next deeper indent (9 to 17 observed), and nested lists go deeper still. A term may share its line with the start of its description, separated by two or more spaces (inline term). Consecutive term lines share one description.
  - Lines may exceed the render width (up to 512 observed). `<?>` stands for a glyph mandoc cannot transliterate (the Apple logo in 488 footers).
- **D-028 UX concept: launcher + card (2026-11-21, approved by the user on the web demo).** Reason: lookup is the #1 job and Leva lives in a split pane. Binding spec: `docs/design/leva-sh/UX.md`; reference demo: `docs/design/leva-sh/demo/leva-demo.html`.
  - Wide (≥100 cols): Search box + Results on the left, Card of the highlighted result on the right as a live preview while moving. Medium (60–99): stack Search → Card → `Esc` back. Narrow rule unchanged (DITS §14).
  - Card tabs: 1 Overview (lead, explanation, top 3 examples, notes, related), 2 Examples (all; curated first, then `[tldr]`), 3 Subcommands, 4 Related, 5 Manual.
  - History (breadcrumb `search › a › b`) resets when a card is opened from Results; it grows only when navigating from a card (related, subcommand).
  - Placeholders are displayed as `<name>` in the accent colour (storage stays `{{name}}`, copy stays unbracketed `name`). This refines FR-14's display only; it is one of the new visual conventions handled by T-8.11 / U-2.
- **D-029 Intent search as a first-class ranking signal (2026-11-21).** Reason: "compress a folder" must surface `tar` first, deterministically. Results show a secondary line `via: <intent>` when the match came from a curated intent or synonym. Ranking must never fall back to alphabetical order between intent matches of different strength: exact intent phrase > all-words match > partial; an earlier (primary) intent in a card's list ranks higher; curated beats uncurated on ties; name order is only the last tiebreak. The gold set (T-10.18) includes intent queries.
  - Amended 2026-11-22: intent order is stored as `intent.ord` by `IndexWriter.add_intents` (T-4.1) and `NameRow.intents` follows it (T-4.4); `SearchResult` gains `via` (T-5.1). v1 has no separate synonym field: a synonym is written as one more curated intent, and `via` shows that intent's text. Reason: Phase 0 review F-7.
- **D-030 Danger warnings (2026-11-21).** Reason: beginners copy destructive commands. Schema: `Example.danger: str | None` (YAML key `danger`, a specific reason such as "deletes permanently, no Trash, no undo"). Content validation fails when an example matches a D-016 destructive pattern and has no `danger`. UI: an amber `[danger] <reason>` line under the command; copying it shows `copied (danger): …` in the accent colour instead of green. Copy is never blocked.
  - Amended 2026-11-22: applied to plan: T-1.1 (`Example.danger`), T-4.1 (`example.danger` column), T-4.3 (fixture example with `danger`), T-4.4 (`Repository.examples` reads it back), T-6.4 (attachment). Reason: Phase 0 review F-6; DITS §1 and §9 do not have the field.
- **D-031 Home and empty states (2026-11-21).** Reason: never show an empty screen. Home (empty query) shows a session-only Recent list (no persistence in v1) and a "Start here" panel with clickable "Try" queries and the badge legend (`[curated]`, `[macos]`, `[builtin]`, `(man)`). No-match state: `No match for "<q>". Try fewer words, or a command name.` plus up to 3 nearest names.
  - Amended 2026-11-22: nearest names come from `Searcher.nearest_names` (T-5.1) through `Library.nearest_names` (T-5.3), since tui cannot import search; the Recent list is tui state. Reason: Phase 0 review F-8.
- **D-032 R-11 mitigation without a LIKE fallback (2026-11-22).** Reason: S-3 finding 1 found FTS5 compiled into every SQLite on this Mac (3.45.1 to 3.54.0, Python 3.9 to 3.13), and no PLAN task builds a fallback. v1 has no LIKE search: a SQLite without FTS5 makes the build fail with IngestError (the `search_fts` DDL raises), and doctor's SQLite/FTS5 check names the cause. This changes the R-11 mitigation in ANALYSIS ("degradazione a LIKE").
- **D-033 Model invariant details (2026-11-22).** Reason: DITS §1 states the invariants only in outline, and T-1.1 had to fix them precisely. Errors live in the private `leva.model._errors` (re-exported from `leva.model`), not in `leva.model.errors` as DITS §0 writes, per D-002. `LevaError` does not validate its message. The Literal types are public aliases `ExampleSource`, `Verification`, `NoteKind`. The name rule (non-empty, no `str.isspace()` character) applies to `Entry.name`, `Entry.section`, `Example.id`, `Subcommand.name` and `Subcommand.entry_name` (the optional ones when set); `Entry.kind`/`origin` must be enum members; `Example.cmd` has no `\r`, does not end with a newline and puts `\` before every newline; `Example.danger` and `Subcommand.source` are non-blank when set. No other field is constrained.
  - Amended 2026-11-23: applied to plan: T-3.1 (validate the `Example.cmd` invariants before building an `Example`; a YAML `|` block ends with a newline) and T-4.4 (`Kind(value)`/`Origin(value)` when reading entries). Reason: Phase 1 review F-3; both tasks relied on the model accepting any non-empty cmd and any string kind.
- **D-034 Placeholder syntax details (2026-11-22).** Reason: DITS §2 leaves the edge cases open. A placeholder runs from `{{` to the first following `}}`; its inner text is kept as written (single braces and whitespace included). `\{{` is a literal `{{` and is the only escape; a lone `\` is literal. `}}` outside a placeholder is literal. An unclosed `{{` makes the rest of the command literal. `{{}}` stays literal text (segments are never empty), so the DITS §2 post-condition "delimiters removed" holds for every non-empty placeholder. `problems(cmd)` returns, in source order, `"empty placeholder"` for each closed placeholder with blank inner text and `"unclosed placeholder"` for an unclosed `{{`; T-3.1 prefixes them with `file:field: `.
- **D-035 Path resolution details (2026-11-22).** Reason: DITS §4 and ARCHITECTURE (`resolve(env)`) leave the edge cases open. `LevaPaths.resolve(env, home)` reads only `LEVA_HOME` from `env` and takes `home` as an argument (`HOME` in `env` is ignored); `home` must be absolute (ValueError). An empty `LEVA_HOME` is unset. `LEVA_HOME` is not `~`-expanded: a relative value (including `~/x`) raises `ConfigError("LEVA_HOME: not an absolute path: ...")` with a hint. `index_db` is `data_dir/index.db`. ARCHITECTURE's `LevaPaths.resolve(env)` signature gains `home`, as DITS §4 and T-1.3 state.
- **D-036 Clipboard details (2026-11-22).** Reason: DITS §3 leaves the limits and the fake open. The 64 KiB limit (`MAX_TEXT_BYTES = 65536`) counts UTF-8 bytes; empty or oversized text raises ValueError before any spawn, in `PbcopyClipboard` and `FakeClipboard` alike. `pbcopy` gets only `LANG` and `LC_CTYPE` (`en_US.UTF-8`) as its environment, stdout/stderr discarded; a spawn `OSError`, a timeout or a non-zero exit raise `ClipboardError("clipboard unavailable")` with no hint. `FakeClipboard(*, fail=False)` exposes `last` (None before the first copy), `history` (tuple, oldest first) and a mutable `fail` flag; a failed copy records nothing.
- **D-037 Config validation and digest (2026-11-22).** Reason: T-1.5 and D-003 name the keys but not the value rules. `load_config(path, home)`: a missing file gives the defaults; an unreadable file, invalid UTF-8 and invalid TOML raise `ConfigError("<file>: cannot read file" | "not valid UTF-8" | "invalid TOML at line N")` (N parsed from the tomllib message, the last line for "end of document"); every other error is `<file>:<key>[<i>]: <reason>` with the hint `edit <path> or delete it to use the defaults`. `sections` is a non-empty list of unique strings matching `^[a-z0-9]+$` (they name `man<sec>/` dirs). Path lists hold strings; only a leading `~` or `~/` is expanded, with the injected home (never the process env); the result must be absolute; duplicates are kept. `LevaConfig.digest()` is the sha256 hex of `json.dumps({"sections", "extra_man_paths", "extra_bin_dirs"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` with paths as strings, list order preserved.
- **D-038 Executable scan and system info details (2026-11-23).** Reason: DITS §5 orders executables by (name, path) while PLAN T-2.1 orders them by (name, dir index), and DITS leaves the edge cases open. The order is (name, dir index) over the directories deduplicated by `Path` equality (first occurrence kept); every same-named executable of several directories is yielded, the first in PATH order wins in ingest. Names failing the D-033 name rule (`is_entry_name`) are skipped. Symlinks are kept unresolved in `Executable.path` and followed only for the file and execute check, so directories, broken and circular symlinks are skipped; a missing or unreadable directory is skipped, not an error. `DEFAULT_BIN_DIRS` is `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`, `/bin`, `/usr/sbin`, `/sbin`. `origin_for` is pure and component-wise: HOMEBREW under `/opt/homebrew` or `/usr/local` (the prefixes themselves included), else MACOS. `SystemInfo.detect(*, sw_vers="/usr/bin/sw_vers", timeout=5.0, machine=platform.machine)` gains these keyword arguments over DITS §5; `sw_vers` runs with a read-only locale-only env (`LC_ALL`, `LANG`), stdout parsed at the first `:` of each line (first key wins, values stripped); a spawn error, timeout or non-zero exit raise `IngestError("cannot read macOS version: sw_vers failed")`, missing or blank `ProductVersion`/`BuildVersion` raise `IngestError("cannot read macOS version: unexpected sw_vers output")`, a blank architecture raises `IngestError("cannot read machine architecture")`; `timeout <= 0` is a `ValueError`.
- **D-039 Man rendering details (2026-11-23).** Reason: DITS §6 and D-007 leave the stub grammar, the emptiness rule and the subprocess setup open, and S-2 measured them on 2598 pages.
  - `stub_target(source)` scans lines in order, skipping blank lines, a lone `.` and roff comments (lines starting `.\"`, `'\"` or `.\#` after stripping). The first other line decides: it is a stub only when it splits into `.so` and one argument; the stripped argument is returned raw (no resolution against the man root, D-005). `.so` without argument, `.sox`, or any other first request give None.
  - `strip_overstrike(text)` removes every non-newline character followed by a backspace together with that backspace, left to right without overlap, then any remaining backspace (start of text or of a line); the result never contains `\x08`.
  - `read_man_source(path)` reads through `gzip` for a `.gz` suffix, decodes UTF-8 with replacement, and maps `OSError` (including `gzip.BadGzipFile`), `EOFError` (truncated gzip) and `zlib.error` to `ManRenderError("cannot read man page: <path>")` with the cause chained.
  - `MandocRenderer.render` runs `<binary> -T ascii -O width=<width> <path>` with stdin at DEVNULL, cwd = `path.parent.parent` (the man root, so `.so` resolves as for `man`) and the read-only env `LC_ALL`/`LANG=en_US.UTF-8`, `MANWIDTH=<width>`, `TZ=UTC` (never the process env). Messages (hint None): spawn `OSError` or non-zero exit `mandoc failed: <path>`; timeout `mandoc timed out: <path>`; output with fewer than three non-blank lines (header and footer only) `empty man page: <path>`, because mandoc exits 0 for empty, garbage or `.so`-broken input. The returned text is overstrike-free but otherwise untouched: header, footer and column positions stay for `parse_man`.
- **D-040 Man file discovery details (2026-11-23).** Reason: DITS §5 and D-004/D-005 leave the discovery edge cases open, and DITS gives `ManFile` without `name` and `dir_index`.
  - `discover_man_dirs(manpath_output, extra=())` is pure: the `manpath` entries, then `/opt/homebrew/share/man` and `/usr/local/share/man`, then `extra`; non-absolute paths from any source are dropped and duplicates removed by `Path` equality (first kept, so `/usr/share/man/` and `/usr/share/man` are one). Missing directories are not filtered; the locator ignores them.
  - `run_manpath(env, *, binary="/usr/bin/manpath", timeout=5.0)` passes the child only `PATH` and `MANPATH` from `env` (when present) plus `LC_ALL` and `LANG` = `en_US.UTF-8`, stdin and stderr at DEVNULL. It returns stdout decoded as UTF-8 with replacement, unmodified; blank output is not an error (the fallbacks still apply). A spawn `OSError`, a timeout or a non-zero exit raise `IngestError("cannot list man directories: manpath failed")`; `timeout <= 0` is a `ValueError`.
  - File-name rule: drop a `.gz` suffix, split at the last dot; the base must be a valid entry name (D-033) and the extension must start with the directory's section (`openssl-x509.1ssl` gives `openssl-x509`). Other files (`x.8` in `man1/`, `README.md`, `.bz2`, no extension) are skipped, as are directories and broken or circular symlinks. `ManFile.section` is the directory's section, not the extension's.
  - `ManFile(path, name, section, origin, mtime_ns, dir_index)` (DITS field order amended). `path` is `<dir>/man<section>/<file>` with symlinks left unresolved, `mtime_ns` follows symlinks, `origin` is `origin_for(dir)`. `locate()` rescans on every call and yields sorted by `(name, section position, dir_index, file name)`, so the first `ManFile` of each (name, section) is the D-005 winner and same-directory copies (`x.1`, `x.1.gz`, `x.1m`) are ordered by file name.
  - `ManPageLocator` validates `sections` (non-empty, each matching `^[a-z0-9]+$`) with `ValueError`; the directories are deduplicated keeping the first occurrence and `dir_index` is the position in that tuple.
