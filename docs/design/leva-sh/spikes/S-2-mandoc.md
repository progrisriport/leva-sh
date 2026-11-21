# S-2 — mandoc on sample pages and full rendering benchmark

- Project: Leva (`leva-sh`) · Date: 2026-11-21 · Task: T-0.4 · Status: done
- Related: [ADR-0002](../ADR/ADR-0002-ingest-man-mandoc.md) · [ANALYSIS §9](../ANALYSIS.md) · [DECISIONS](../DECISIONS.md) (D-004, D-005, D-007, D-008, D-027)
- Code: [`spikes/s2_mandoc.py`](../../../../spikes/s2_mandoc.py)

Verdict: `mandoc -T ascii -O width=80` renders every section 1/8 page on this Mac in about
4 s with 8 workers (2598 pages, 0 failures). That is well under the 20 s threshold, so plan B
(lazy rendering, U-S2) is not needed. D-007 is confirmed, with amendments on the working
directory and on detecting empty output. D-004, D-005 and D-008 get clarifications, and D-027
records the layout of rendered pages that the parsers rely on.

## Method

`spikes/s2_mandoc.py` (run with `uv run python spikes/s2_mandoc.py`; `--quick` renders a
200-page subset, `--json PATH` dumps the raw report into gitignored `spikes/out/`):

1. **Discovery per D-004.** It runs `/usr/bin/manpath` twice: once with the inherited
   environment and once with the minimal ADR-0002 §8 environment. It then appends
   `/opt/homebrew/share/man` and `/usr/local/share/man`, deduplicates, and scans
   `man1/` and `man8/`. A file name parses as `<name>.<ext>[.gz]`, where `<ext>` must start
   with the directory's section. The key is `(name, dir section)`.
2. **Sources.** It reads every roff source (gz-aware), hashes it, checks UTF-8, and detects
   stubs: the first request that is not a comment is `.so`. It resolves stub targets
   against the man root and against the page directory.
3. **Samples.** It renders the PLAN sample list and records structure only: header volume,
   footer, NAME form, headings, duplicate and non-uppercase headings, and definition-list
   indents (from transitions between indents in COMMANDS/VERBS/BUILTIN/OPTIONS sections).
   It also compares Python overstrike stripping with `col -bx`, and records non-ASCII
   bytes, tabs and the widest line.
4. **Exit codes.** It renders synthetic inputs written by the spike: a missing file, an empty
   file, plain text, invalid UTF-8, an unknown macro, `.so` to a missing target, and binary
   garbage.
5. **Benchmark.** It renders the ingest set (the first copy per key, minus stubs; see D-005
   below) in a `ThreadPoolExecutor` with 1, 2, 4, 6 and 8 workers, 3 runs each. mandoc runs
   with `cwd` = the page's man root and the ADR-0002 §8 environment (`LC_ALL`/`LANG`
   `en_US.UTF-8`, `MANWIDTH=80`, `TZ=UTC`). It then runs a corpus-wide structure analysis and
   a corpus-wide Python-vs-`col -bx` check.

The report holds only counts, codes, indents, heading names and timings. No man page prose
is committed here or in the code.

## Environment

| Item | Value |
|---|---|
| macOS | 27.2.1 (26B131), arm64, 10 CPUs |
| Python | 3.13.12 (uv project env) |
| mandoc | `/usr/bin/mandoc` (system); `col` at `/usr/bin/col` |
| Command Line Tools | installed (SDK and `usr/share/man`) |
| Page cache | warm (sources were read during discovery, as ingest also does) |

Man dirs in D-004 order (inherited environment), with their section 1/8 files:

| # | Dir | Files |
|---|---|---|
| 0 | `/opt/homebrew/opt/postgresql@18/share/man` | 37 |
| 1 | `/opt/homebrew/share/man` | 587 |
| 2 | `/usr/local/share/man` | 3 |
| 3 | `/System/Cryptexes/App/usr/share/man` | 10 |
| 4 | `/usr/share/man` | 2024 |
| 5 | `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/share/man` | 1971 |
| 6 | `/Library/Developer/CommandLineTools/usr/share/man` | 244 |

The totals are 4876 files and 2788 unique `(name, section)` keys, with 2088 shadowed copies:
`[4]` beats `[5]` 1933 times, `[1]` beats `[6]` 154 times and `[4]` beats `[6]` once. There are
no same-directory duplicates. Non-plain suffixes are `1m` (90) and `1tcl` (8). There are 9 `.gz`
files. 12 files are skipped because their extension does not match their directory (for
example a `.8` page inside `man1/`, or a `README.md`).

**`/usr/share/man` vs the CLT SDK.** The two dirs share 1933 keys. 1661 of them have
byte-identical sources and 272 differ. 38 keys exist only in the SDK, mostly Apple daemons and
agents. Because the SDK comes after `/usr/share/man` in `manpath` order, its copy always loses
(D-005).

## Samples

All samples exit 0 with empty stderr. For each one, Python overstrike stripping and `col -bx`
produce identical text. Times are single renders.

| Sample | Dir | ms | NAME | Structure worth knowing |
|---|---|---|---|---|
| ls(1) | 4 | 6.1 | ` - `, 1 name | options live in DESCRIPTION; 1 subsection line at indent 3 |
| tar(1) | 4 | 4.1 | ` - `, 1 name | OPTIONS: terms at 5, descriptions at 13, 14 inline terms |
| test(1) | 4 | 2.7 | ` - `, 2 names (`test, [`) | plain |
| `[`(1) | 4 | 1.9 / 2.6 | stub | `.so man1/test.1`; with a neutral cwd: exit 0, header and footer only (192 B), no diagnostic; with cwd = man root: renders test(1) in full |
| git(1) | 1 | 4.6 | ` - `, 1 name | Homebrew Git 2.56.0 beats the CLT copy (`[6]`, Git 2.39.0); `GIT COMMANDS`, `HIGH-LEVEL COMMANDS (PORCELAIN)`, `LOW-LEVEL COMMANDS (PLUMBING)`: terms at 5, descriptions at 9 |
| zshbuiltins(1) | 4 | 6.8 | ` - `, 1 name | headings `NAME`, `SHELL BUILTIN COMMANDS` only; terms at 5, descriptions at 12, about 87 term groups (consecutive synopsis lines share one description); nested option lists 12 → 19 |
| bash(1) | 4 | 11.4 | ` - `, 1 name | GNU Bash 3.2, 37 headings; `SHELL BUILTIN COMMANDS`: terms at 5, descriptions at 12, 53 term groups; nested lists 12 → 19/20 |
| builtin(1) | 4 | 3.0 | ` - `, **109 names over 11 lines** | the list of builtins is the NAME line itself |
| find(1) | 4 | 3.6 | ` - `, 1 name | `PRIMARIES`, `OPERATORS` instead of OPTIONS |
| grep(1) | 4 | 2.8 | ` - `, 10 names over 2 lines | plain |
| sed(1) | 4 | 3.1 | ` - `, 1 name | **non-uppercase headings** `Sed Addresses`, `Sed Regular Expressions`, `Sed Functions`; widest line 96 |
| launchctl(1) | 4 | 3.2 | ` - `, 1 name | **`SUBCOMMANDS` twice** (a short overview, then the full list) plus `LEGACY SUBCOMMANDS`; terms at 5, descriptions at 14; footer `Darwin` |
| diskutil(8) | 4 | 6.7 | ` - `, 1 name | `VERBS`: verbs at 5, descriptions at 16, nested lists at 27; about 35 verb groups |
| defaults(1) | 4 | 2.7 | ` - `, 1 name | OPTIONS: terms at 5, descriptions at 17; widest line 124 |
| brew(1) | 1 | 7.4 | ` - `, 1 name | `ESSENTIAL COMMANDS`, `COMMANDS` (terms at 5, descriptions at 12), `DEVELOPER COMMANDS`, `CUSTOM EXTERNAL COMMANDS`; 122 subsection lines |
| ssh(1) | 4 | 4.5 | ` - `, 1 name | plain |
| openssl(1) | — | — | — | **not installed**: no openssl page in man1 of any dir and no `.1ssl` file on this Mac; the `1ssl` case stays covered by synthetic tests (T-2.2) |
| perltoc(1), largest man1 | 4 | 50 | ` - `, 1 name | 1.3 MB source, 797 KB output; 771 subsection lines |
| less(1), first `.gz` | 4 | 5.4 | ` - `, 1 name | mandoc reads gzip itself; `COMMANDS` and `OPTIONS` lists |

## Benchmark

There are 2598 pages to render (first copy per key, stubs excluded) and 0 failures in every
run. A failure here is a non-zero exit, a timeout, or header/footer-only output. Every exit
code is 0, there are no timeouts, and stderr is always empty.

| Workers | Runs (s) | Median (s) | Best pages/s |
|---|---|---|---|
| 1 | 6.75, 7.29, 7.94 | 7.29 | 385 |
| 2 | 4.60, 4.63, 4.67 | 4.63 | 564 |
| 4 | 4.12, 4.09, 4.13 | 4.12 | 635 |
| 6 | 4.13, 4.14, 4.22 | 4.14 | 628 |
| **8** | **4.17, 4.18, 4.18** | **4.18** | 623 |

**8-worker full render: 4.18 s median (best 4.17 s)**, against the 20 s threshold. An earlier
full run measured 4.06 s. Throughput stops growing at about 4 workers. The limit is most
likely process spawning (one fork/exec per page), not mandoc itself. Other costs:

- the source scan with stub detection over all 4876 files takes 0.45 s;
- Python overstrike stripping over the whole corpus takes 0.19 s;
- `col -bx` would cost 4.78 s with 8 workers.

The slowest single pages are perltoc 89 ms, perlapi 81 ms, zshall 67 ms (it pulls in every
zsh page through `.so` once cwd is the man root), perluniprops 48 ms and bash 40 ms.

## Findings

1. **Exit status says almost nothing.** mandoc exits 0, with no diagnostic, for an empty
   file, plain text, invalid UTF-8, unknown macros, binary garbage and a `.so` to a missing
   target. In each case the output is only the header and footer lines (163–197 B). Only a
   missing file gives a non-zero status (5, with a diagnostic on stderr). An empty render must
   therefore be detected from the text.
2. **`.so` resolves against the working directory**, not against the page. If cwd is not the
   man root, a stub renders as an empty page with exit 0. 370 stub files exist (190 of them
   win their key), and all have the form `manN/<file>` or a relative path through `..`. 117
   stubs use a `..` path; the ones listed point to the Xsan pages under
   `/System/Library/Filesystems/acfs.fs/Contents/man/`. From `/usr/share/man`, 58 winning stubs
   resolve to files **outside every man dir**. From the SDK, the 59 copies resolve nowhere. Of the 190 winning stubs, 131 point at an indexed page (alias), 58 point outside
   the man dirs and 1 points at a missing file. zshall(1) has `.so` after its first request.
   It includes every zsh page and renders fully only with cwd = man root.
3. **A stub can shadow a real page.** `/usr/share/man/man1/rsync.1` is a stub to
   `openrsync.1`, while the CLT SDK has an unrelated real `rsync.1`. `man rsync` shows
   openrsync. If stubs were removed before choosing the winner, the SDK page would win
   instead.
4. **Overstrike is everywhere and Python stripping is exact.** All 2598 pages contain
   backspace sequences. Removing `.\b` in Python gives text identical to `col -bx` on 2598 of
   2598 pages, with no residual backspaces, and it is about 25 times cheaper. There are no
   tabs and no other control characters.
5. **`-T ascii` output is pure ASCII.** No output byte is above 0x7F, and every source is
   valid UTF-8. A glyph mandoc cannot transliterate becomes the literal `<?>`. This happens in
   the footer of 488 Apple mdoc pages, where it is the Apple logo U+F8FF (seen with
   `-T utf8`), and in the body of 21 pages.
6. **Width 80 is a target, not a limit.** 375 pages have lines longer than 80 columns (literal
   tokens, URLs, tables); the widest is 512 (gnutls-serv). This is consistent with D-012
   (manual view without soft wrap, with horizontal scroll). Parsers must not assume
   `len(line) <= 80`.
7. **Header and footer** are the first and last non-blank lines. 2557 of 2598 headers match
   `TITLE(SEC) volume TITLE(SEC)`. The other 41, mostly Apple agent and daemon pages, do not,
   so the parser must not depend on that pattern. Two Apple pages print an extra footer-like
   line in the middle of the page, where it looks like a heading.
8. **Headings** sit at column 0; everything else is indented. Section bodies are at indent
   5 in both mdoc and man(7) pages, and subsection headings are at indent 3 (439 pages).
   Points the parser must handle:
   - headings are not always uppercase: perl pages (`Incompatible Changes`, 59), sed, and
     `Name`/`Syntax`/`Description` in dc, nano and pico;
   - column-0 lines with no letters are rule lines, not headings (`____...` in tcl/tk pages);
   - 16 pages repeat a heading: launchctl `SUBCOMMANDS`, `NOTES`, `AUTHORS`, and `NAME` and
     `DESCRIPTION` once zshall's `.so` includes resolve.
9. **NAME.** It is at indent 5 on every page that has it. Separators: ` - ` 2534, ` -- ` 15,
   none 44 (only the name, no summary), NAME missing 5 (`Name` in title case in dc, nano
   and pico; kernelmanagerd and kmutil have no NAME at all). 110 pages list several names;
   NAME spans more than one line on 282 pages (up to 11). If the parser matches NAME without
   regard to case, about 98% of man-backed entries get a summary (PRD target ≥95%,
   T-6.6).
10. **Definition lists** have per-page indents. First-level terms are at 5. Descriptions are
    at 9 (git), 12 (brew, less, zsh, bash), 13 (tar), 14 (launchctl), 16 (diskutil) or 17
    (defaults). Nested lists go deeper, for example 12 → 19 and 16 → 27. Short terms often
    share their line with the start of the description, separated by two or more spaces
    ("inline terms": 14 in tar, 46 in less COMMANDS). Several consecutive term lines can
    share one description (zsh synopsis variants).
11. **Subcommand headings** in the corpus, by full match of `(SUB)?COMMANDS|VERBS`:
    `COMMANDS` 61, `SUBCOMMANDS` 13, `VERBS` 10. A substring search would also hit
    `OPTIONS INHERITED FROM PARENT COMMANDS` (88 gh pages), `SHELL BUILTIN COMMANDS` and
    `MACH-O ONLY OPTIONS AND COMMANDS`. Qualified headings such as `AVAILABLE COMMANDS` (27),
    `DEVELOPER COMMANDS` and git's `HIGH-LEVEL COMMANDS (PORCELAIN)` do not fully match. git
    still gets its subcommands from its hyphen pages and the `git help -a` probe; brew from
    `COMMANDS` and its probe.
12. **`manpath` depends on PATH.** With the inherited environment it lists the Homebrew dirs
    first, plus a dir derived from a PATH entry (`/opt/homebrew/opt/postgresql@18/share/man`).
    With the minimal ADR-0002 §8 PATH, it lists only `/usr/share/man`, the two CLT dirs and
    `/usr/local/share/man`. The D-004 extras would then put Homebrew last, and the CLT
    `git(1)` (2.39) would beat the Homebrew `git(1)` (2.56), whose binary wins the bin-dir
    order.

## Decisions

- **D-007 confirmed and amended.** The pipeline is: stub detection from the gz-aware source,
  then overstrike stripping in Python (no `col`), then `-T ascii -O width=80`. New: mandoc runs
  with `cwd` = the page's man root. An output with no text between the header and footer
  lines counts as a failed render, just like a non-zero exit or a timeout.
- **D-004 amended.** `manpath` runs with the user's `PATH` and `MANPATH`, injected from
  `leva.cli`, so the man-dir order matches what `man` shows the user.
- **D-005 amended.** The winner per key is chosen over all copies, stubs included. A winning
  stub becomes an alias when its target is an indexed page; otherwise it is rendered as itself
  from the man root, so mandoc follows the `.so`. A stub whose target is missing is skipped.
- **D-008 clarified.** The heading regex is a full match on the heading text, and repeated
  headings are all scanned.
- **D-027 (new).** The layout of rendered text that `manparse` relies on (findings 6–10).
- **Workers.** Keep 8 (ADR-0002 §3): the plateau from 4 to 8 workers costs nothing and leaves
  headroom on slower Macs.
- **U-S2 not inserted.** The 8-worker full render takes 4.18 s, far under 20 s.

## Impact on plan

Applied in this commit, per R10 (each change is backed by a DECISIONS entry):

- **T-2.2**: `run_manpath` takes the injected `env` (user `PATH`/`MANPATH`) (D-004).
- **T-2.4**: `stub_target` returns the raw `.so` path (`manN/x.N` or a `..` path); resolution
  happens against the man root. `MandocRenderer` runs with cwd = man root and rejects
  header/footer-only output (D-005, D-007).
- **T-2.5**: headings are column-0 lines with at least one letter, of any case. NAME is
  matched without regard to case. Header and footer are the first and last non-blank lines
  (D-027).
- **T-2.6**: `definition_items` handles inline terms and per-page indents (D-027).
- **T-6.3**: the catalog tests also cover a stub that shadows a later real page (rsync), a stub
  whose target is outside the man dirs (Xsan), and a stub with a missing target (D-005).
- No U-S2 task. T-2.R's live smoke criterion (≤2% render failures) is consistent with 0 of
  2598 failures here, provided empty renders are counted as failures.
