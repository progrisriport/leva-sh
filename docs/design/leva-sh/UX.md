# UX — Leva v1 screens and flow

Status: approved by the user on 2026-11-21 (web demo v2). Binding; recorded as D-028..D-031 in DECISIONS.md.
Inputs: user choices of 2026-11-21 (concept "launcher + card"; v1 originals: intent search, danger warnings), research in `docs/research/2026-11-21-competitors-and-tui-patterns.md`, ADR-0005, DITS §14, design system snapshot.

## 1. Principles
1. **Lookup first.** The #1 job is "I forgot how to X". From launch to an example in the clipboard takes at most: type query → `Enter` → (`↓` to an example) → `c`.
2. **Answer on one screen.** The card's first tab shows summary, the top examples, notes and related commands without scrolling at 100×30.
3. **Never execute.** Leva copies; the user pastes in their own shell.
4. **Honest about the Mac.** Every curated card says what is different on macOS (BSD userland, zsh default).
5. **Design system everywhere**: one amber accent, transparent background, box-drawing borders with the title in the top border, header + footer on every screen, bold only for the selected item, no emoji, badges as `[text]`.

## 2. Concept: launcher + card
- Wide (≥100 cols): left column = Search box + Results; right column = Card of the highlighted result (live preview while moving).
- Medium (60–99 cols): single-pane stack. Search screen → `Enter` → Card screen → `Esc` back.
- Narrow (<60 cols or <12 rows): "terminal too narrow (min 60×12)" with header and footer (unchanged from DITS §14).

## 3. Screens

### 3.1 Search (home)
Wide, empty query (home state):
```
┌─ Leva ───────────────────────────────────────────────────────── macOS 27.2 · 2598 entries ─┐
│ Less effort, more thought.                                                                  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
┌─ Search ──────────────────────────────┐┌─ Start here ──────────────────────────────────────┐
│ type a command or what you want to do ││ Try:  compress a folder · find text in files      │
└───────────────────────────────────────┘│       list running processes · copy to clipboard  │
┌─ Recent ──────────────────────────────┐│                                                   │
│   tar      create, list, extract      ││ Badges:  [curated] hand-written card               │
│   git      version control            ││          [macos]   macOS-only command              │
│                                       ││          [builtin] zsh builtin                     │
│                                       ││          (man)     from the local manual only      │
└───────────────────────────────────────┘└───────────────────────────────────────────────────┘
─────────────────────────────────────────────────────────────────────────────────────────────────
/ search   ↑↓ move   Enter open   ? help   a about   q quit
```
- Recent = cards opened in this session (in memory, no persistence in v1).
- "Try" lines are clickable and fill the query.

Wide, with a query (intent match):
```
┌─ Search ──────────────────────────────┐┌─ tar ─────────────────────────────── [curated] ─┐
│ compress a folder▏                    ││ Create, list and extract archives.               │
└───────────────────────────────────────┘│ ┌─ 1 Overview ─ 2 Examples ─ 3 Subcmds ─ 4 Related ─ 5 Manual ┐
┌─ Results  6 ──────────────────────────┐│ │ > 1 Compress a folder into .tar.gz              │ │
│ > tar      create, extract  [curated] ││ │     tar -czf <archive>.tar.gz <folder>          │ │
│            via: compress a folder     ││ │   2 Extract an archive here                     │ │
│   zip      package and compress       ││ │     tar -xzf <archive>.tar.gz                   │ │
│   ditto    copy, keep metadata [macos]││ │   3 List contents without extracting            │ │
│   gzip     compress single files      ││ │     tar -tzf <archive>.tar.gz                   │ │
│   hdiutil  disk images        [macos] ││ │ [bsd]  macOS tar is bsdtar: --exclude must come │ │
│   compress (man)                      ││ │        before the paths.                        │ │
└───────────────────────────────────────┘│ │ Related: zip · ditto · gzip · hdiutil           │ │
                                         │ └──────────────────────────────────────────────────┘ │
                                         └─────────────────────────────────────────────────────┘
copied: tar -czf archive.tar.gz folder
─────────────────────────────────────────────────────────────────────────────────────────────────
/ search   ↑↓ move   Enter open   Tab card   c copy   m manual   ? help   q quit
```
- Result row: name, summary (secondary), badges. When the match came from a curated intent or synonym, a second secondary line `via: <intent>` explains why (D-029).
- `(man)` = entry without curated card.
- Empty result: `No match for "xyz". Try fewer words, or a command name.` + 3 nearest names (fuzzy).

### 3.2 Card
Header breadcrumb shows the history: `search › tar` or `search › git › git commit`.
Tabs (`1`–`5`, `h/l`, `←/→`, click):
1. **Overview** — summary, explanation (2–6 sentences), top 3 examples, notes (`[bsd]`, `[zsh]`, `[macos]`, `[danger]`), related.
2. **Examples** — all examples (curated first, then tldr with `[tldr]` badge), each with description and command; placeholders `<name>` in amber.
3. **Subcommands** — list (name + summary); `Enter` opens the subcommand card.
4. **Related** — list; `Enter` opens.
5. **Manual** — rendered man page; `[`/`]` previous/next section; `/` inside = find in page.
Uncurated entries: Overview shows NAME/SYNOPSIS summary from the man page plus "No curated card yet — see Manual (5)."

### 3.3 Danger warnings (D-030)
Example with a `danger` reason (schema field, curated YAML):
```
│   4 Delete a folder and everything in it                       │
│     rm -rf <folder>                                            │
│     [danger] deletes permanently, no Trash, no undo            │
```
- `[danger]` line in amber (the accent = "needs attention"); the reason is mandatory and specific.
- Copy is allowed; the status line reads `copied (danger): rm -rf folder` in amber instead of green.
- Validation: any example whose command matches the D-016 destructive patterns must carry `danger` (content validation error otherwise).

### 3.4 First run / rebuild (IngestScreen)
```
┌─ Leva ─────────────────────────────────────────────────────────────┐
│ Building your local index (first run only)                         │
└────────────────────────────────────────────────────────────────────┘
┌─ Index ────────────────────────────────────────────────────────────┐
│ Reading man pages      1240 / 2598   ████████████░░░░░░░░░░  48%    │
│ Executables            1312 found                                   │
│ Curated cards          152 ready                                    │
│                                                                     │
│ Everything stays on this Mac. This takes ~5 s.                      │
└────────────────────────────────────────────────────────────────────┘
──────────────────────────────────────────────────────────────────────
Ctrl+C cancel
```
Progress uses the design system rule: progress bars rendered without colour backgrounds; the bar glyphs are text in accent/secondary.

### 3.5 Help overlay (`?`)
Grouped keys (Global / Search / Card / Manual), filterable by typing. `Esc` closes.

### 3.6 About (`a`, `leva --about`)
Version, index stats, licences (MIT code, CC BY 4.0 content), tldr-pages attribution.

### 3.7 `leva doctor`
Plain text (no TUI): one line per check `ok|fail  <check>  <detail>`, fix hint on fail; exit 0/1.

## 4. Main flow
```
leva [query] ──► index present? ──no──► IngestScreen ──┐
                      │yes                              │
                      ▼                                 ▼
             exact name match? ──yes──► Card(Overview) ◄┘
                      │no
                      ▼
             Search (query prefilled) ──Enter──► Card ──↓/click example──► c ──► "copied: …"
                      ▲                            │                                │
                      └────────── Esc ─────────────┘                    user pastes in shell (⌘V)
```

## 5. Key map (delta vs DITS §14)
| Context | Key | Action |
|---|---|---|
| search | `Tab` | move focus to the card (wide) |
| search | `Enter` on "Try" line | fill query |
| card | `↑/↓` | select example (Overview/Examples) |
| card | `c` or click | copy selected example |
| card | `m` | jump to Manual tab |
| manual | `/` | find in page; `n`/`N` next/previous |
All other bindings as DITS §14.

## 6. Decisions to record
- **D-028** Concept: launcher + card; wide = live preview of the highlighted result; Overview tab shows top 3 examples.
- **D-029** Intent search is a first-class ranking signal; results show `via: <intent>` when the match came from an intent/synonym.
- **D-030** Danger warnings: `Example.danger: str | None`; mandatory for destructive patterns; amber `[danger]` line and amber copy confirmation.
- **D-031** Home state: "Try" suggestions + session-only Recent list; empty-result message with nearest names.

## 7. Out of scope for v1 (moved to v1.x)
Fillable placeholders before copy; "explain this command"; persistent recents/favourites; recipes; tutorials.
