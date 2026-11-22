# S-1 — Textual transparent background

- Project: Leva (`leva-sh`) · Date: 2026-11-22 · Task: T-0.6 (automated part) · Status: automated part done, U-1 manual checks pending
- Related: [ADR-0005](../ADR/ADR-0005-tui-textual-design-system.md) · [DECISIONS](../DECISIONS.md) (D-012, D-024) · [design system snapshot](../../design-system-snapshot.md)
- Code: [`spikes/s1_textual_background.py`](../../../../spikes/s1_textual_background.py)

Verdict: a Textual 8.2.8 theme with `ansi=True`, `ansi_default` for background/surface/panel/boost
and palette hex for everything else keeps the app on the terminal's own background, provided
that the stylesheet overrides six Textual defaults (listed below). In the recommended run the
only background code written is SGR `49` (default); no truecolour background appears, every
foreground is a palette hex, and the frame glyphs are exactly `┌ ┐ └ ┘ │ ─`. The `surface`
variant (`#1A1A1A` fill) passes the same gate and stays documented as the fallback. No widget in
the demo needs the fallback, so `SURFACE_FALLBACKS` is empty. Without the overrides (`--bare`)
Textual injects ANSI-palette colours, 8-colour backgrounds and non-box block glyphs.

## Method

`spikes/s1_textual_background.py` is a demo app plus a pty analyzer:

1. **Demo app** (`--variant transparent|surface [--bare] [--seconds S]`, default 1 s, `0` = until
   `q`). Header box (`Leva` as `border_title`, tagline inside), two body boxes (`Search` with an
   `Input` and an `OptionList` with a highlighted row, `Card` with `TabbedContent` of three tabs
   and 60-line scroll areas), a green status line, a custom footer (`─` rule + `key desc`
   pairs) and one `notify("toast probe")`. Textual's `Header`/`Footer` are not used. The Input
   has focus for the first half of the run and the OptionList for the second half, so both
   cursor states are captured. All colours come from one `PALETTE` mapping, used by the Theme,
   the CSS string and the gate.
2. **`--analyze`** spawns the app four times in a pty of 100x30 (`transparent`, `surface`,
   `transparent --bare`, `surface --bare`) with an explicit environment (`TERM=xterm-256color`,
   `COLORTERM=truecolor`, no `NO_COLOR`/`FORCE_COLOR`/`TEXTUAL_*`, a temporary `HOME`), reads
   every byte, parses the SGR sequences (`parse_sgr`) and prints one report per run and a
   summary. `--json PATH` also writes the structured report; raw captures go to the gitignored
   `spikes/out/`.
3. **Gate** (recommended runs only; `--bare` is informational): foreground ⊆ palette hex ∪
   {`39`}; background ⊆ {`49`} ∪ the surface hexes (transparent: only hexes listed in
   `SURFACE_FALLBACKS`); no unparsed colour sequence; all of `┌┐└┘│─` present; none of
   `╭╮╰╯ ┏┓┗┛━┃╸╺ ╔╗╚╝═║ ▊▎▔▁▀▄▌▐`. A demo exit code other than 0 is a harness failure.
   Exit codes: 0 pass, 1 gate violation, 2 harness failure.
4. **`--selftest`** checks `parse_sgr`, `strip_escapes` and the gate on synthetic sequences
   (truecolour, 256-colour, basic codes, resets, the colon form, malformed colours and non-SGR
   CSI such as `\x1b[?2048$p`). It ran green before the pty work and is run again by the
   acceptance commands.

## Environment

| Item | Value |
|---|---|
| Python | 3.13.12 (project interpreter, `uv run`) |
| Textual / Rich | 8.2.8 / 15.0.0 |
| Child environment | `TERM=xterm-256color`, `COLORTERM=truecolor`, `LANG=LC_ALL=en_US.UTF-8`, `COLUMNS=100`, `LINES=30`, temporary `HOME` |
| pty | `pty.openpty()`, window size set with `TIOCSWINSZ` to 100 columns x 30 rows |
| Hard limits | 20 s per run, process group killed on timeout |
| Platform | macOS (Darwin 27.2.0); the real terminal emulators are checked in U-1 |

## Default background injectors

What Textual's default CSS does in an `ansi=True` palette theme and what the capture of
`transparent --bare` showed (SGR codes are the ones seen in that run). The override column is what
the recommended CSS/theme does.

| Widget | Default rule / variable | Seen in `--bare` | Override |
|---|---|---|---|
| `Input` border | `border: tall $border-blurred` (and `tall $border` on focus) | `▊ ▎ ▔ ▁` glyphs, fg `30`/`35` (ANSI black/magenta) | `border: solid #3A3A3A`; on focus `solid #E8B84B`; theme `border`, `border-blurred` = border hex |
| `Input` cursor | `Input:ansi > .input--cursor { background: ansi_white; color: ansi_black }` (hard-coded, beats the `input-cursor-*` variables) | `2;7;30;47` on the first placeholder character | CSS rule `Input > .input--cursor { background: ansi_default; color: #E8B84B; text-style: reverse }` (reverse video, bg stays `49`) |
| `Input` placeholder | `Input:ansi > .input--placeholder { color: ansi_default; text-style: dim }` | dim `#6A6A6A` (`ansi_default 50%` blend) | `color: #7A7A7A; text-style: none` |
| `Input` background tint | `&:focus { background-tint: $foreground 5% }` | not isolated in the capture | `background-tint: transparent` (precaution: a tint over `ansi_default` has nothing to blend with) |
| `OptionList` highlight | `$block-cursor-background` (`ansi_magenta` in the generated ansi variables), `background-tint: $foreground 5%` | `1;39;45` on the highlighted row (bg `45`) | theme `block-cursor-*` variables + `.option-list--option-highlighted` / `-hover*` rules: accent fg, bold, `background: ansi_default` |
| `Tabs` underline | `Underline` widget draws `━ ╸ ╺` | `━ ╸ ╺` glyphs, fg `30`/`35` | `Tabs Underline { display: none }`, `Tabs { height: 1 }`; the active tab is shown by colour |
| `Tab` (inactive) | text `$text-disabled` (`ansi_default 50%`) | dim `#6A6A6A` (`2;38;2;106;106;106;49`) | `color: #7A7A7A; text-style: none`; active: `#E8B84B` |
| Scrollbar track | `scrollbar-background: ansi_black` in the generated ansi variables (the `.-ansi-scrollbar` reset applies only to widgets carrying that class) | bg `40` on 52 blank cells, thumb `7;34` (ANSI blue) | theme `scrollbar*` variables: track `ansi_default`, thumb `#3A3A3A`, hover `#7A7A7A`, active `#E8B84B`; the thumb is drawn as reverse video on `49` |
| `Toast` | `border-left: outer $success` | `▌` in green | `border: solid #3A3A3A`, `border-left` solid too; Leva uses the status line, not toasts, so this is only a safety net |
| `Screen` (inline-mode borders) | `border-top: tall $ansi-background` | stylesheet error without the variable | theme variables `ansi-background` and `ansi-foreground` = `ansi_default` (required even in fullscreen mode) |
| Text selection | `screen-selection-*`, `input-selection-*` | not drawn in this capture | theme variables set to border/text hex to keep selections inside the palette |

## Analysis

100x30 pty, one run per row (counts are occurrences of the SGR parameter in the capture).

| Run | Background codes | Foreground colours | Off-palette fg | Box glyphs | Forbidden glyphs | Bold / reverse / underline | Gate |
|---|---|---|---|---|---|---|---|
| `transparent` | `49` x1053 | `#3A3A3A` x531, `#4BE87A` x4, `#7A7A7A` x21, `#D4D4D4` x209, `#E8B84B` x53 | none | `┌┐└┘│─` | none | 14 / 35 / 0 | PASS |
| `surface` | `#1A1A1A` x994, `49` x59 | same set as `transparent` | none | `┌┐└┘│─` | none | 14 / 35 / 0 | PASS |
| `transparent --bare` | `40` x56, `45` x2, `47` x3, `49` x1108 | palette hex plus `#6A6A6A` x8, `30` x93, `34` x28, `35` x44, `39` x10 | `#6A6A6A`, `30`, `34`, `35` | `┌┐└┘│─` | `━ ╸ ╺ ▊ ▎ ▔ ▁ ▌` | 10 / 83 / 0 | not gated |
| `surface --bare` | `#1A1A1A` x1040, `40` x56, `45` x2, `47` x3, `49` x68 | palette hex plus `#777777` x8, `30`, `34`, `35`, `39` | `#777777`, `30`, `34`, `35` | `┌┐└┘│─` | `━ ╸ ╺ ▊ ▎ ▔ ▁ ▌` | 10 / 83 / 0 | not gated |

Where the non-default sequences of the recommended runs come from:

- Bold (14): the header title `Leva`, the highlighted option row. Reverse (35): the Input cursor
  and the scrollbar thumbs (the thumb is a reverse-video cell of the border colour over `49`).
  No underline.
- `surface`: the `#1A1A1A` fill covers header, boxes, input, options, tabs and scroll areas; the
  52 scrollbar-track cells stay `49`, so the terminal background shows through the track
  inside a surface-filled box. That is invisible with a dark profile and only matters if the
  fallback is ever adopted.

## Findings

1. **Recommended theme passes the gate.** `ansi=True`, `ansi_default` for
   background/surface/panel/boost and palette hex for the rest give background `49` only (1053
   occurrences), foregrounds all in the palette, box glyphs `┌┐└┘│─` and no forbidden glyph.
2. **No widget needs the surface fallback.** `SURFACE_FALLBACKS` is empty. `#1A1A1A`/`#202020`
   stay documented as the neutral fallback (design system: approved Textual extension) for a
   widget that a terminal check (U-1) shows cannot be transparent; adopting it means adding the
   widget and a reason to the list and to T-8.1's palette test.
3. **Textual derives off-palette colours when nothing is overridden.** The `--bare` run writes
   ANSI black/blue/magenta/white (`30 34 35 47 40 45`) and the dim `ansi_default 50%` blend of
   the placeholder and inactive tabs (`#6A6A6A`; `#777777` over the `#1A1A1A` fill). The explicit
   variables and CSS of the recommended run remove all of them; the gate is not widened.
4. **An ansi theme must define `ansi-background` and `ansi-foreground`.** `Screen`'s default CSS
   reads `$ansi-background` even in fullscreen mode; without it the app prints a stylesheet
   error and exits.
5. **`Input:ansi` rules beat the `input-cursor-*` and placeholder variables.** The cursor
   (`ansi_white` on `ansi_black`) and the dim placeholder are hard-coded in `Input`'s
   `&:ansi` block, so theme variables alone leave `47`/`30` in the output. Only an app CSS rule
   on `Input > .input--cursor` / `.input--placeholder` overrides them. The cursor works as
   reverse video: `background: ansi_default; color: <accent>; text-style: reverse` emits
   `7;38;2;…;49`, no bg colour.
6. **`Input` and `Tabs` default borders and underline use forbidden glyphs.** `Input` is `tall`
   (`▊ ▎ ▔ ▁`) and the `Underline` bar draws `━ ╸ ╺`. Fix: `border: solid` and hide the underline
   (the active tab is the accent-coloured one). The `Toast` accent bar `▌` (the `outer` border)
   needs `border: solid`, or no toast.
7. **Scrollbars can be transparent.** With `scrollbar-background*: ansi_default` the track is
   `49`, and the thumb is drawn in reverse video of `scrollbar` (`#3A3A3A`, hover `#7A7A7A`,
   active `#E8B84B`): no background colour is written, so no fallback is needed. The default
   `scrollbar-background` of the ansi variables is `ansi_black` (`40`).
8. **`OptionList` selected row works without a background.** Accent foreground + bold + `49`,
   via `.option-list--option-highlighted` and the hover variants; `block-cursor-background`
   and `block-hover-background` must be `ansi_default` and `background-tint: transparent`, or a
   magenta (`45`) or tinted row appears in the focused list. Bold is the only bold besides the
   header title.
9. **Component classes are the lever, not `$surface`.** Setting `surface`/`panel`/`boost` to
   `ansi_default` in the Theme already makes the generated variables `transparent`, but widgets
   that hard-code `ansi_*` rules (`Input:ansi`, `Underline`, scrollbars) only change through the
   CSS above.
10. **Colour output needs `COLORTERM=truecolor`.** Without it Rich downgrades palette hex to
    256-colour (`38;5;n`), which the gate counts as a violation. The analyzer sets it in the
    child environment; on a real terminal without truecolour the palette degrades.
11. **Header title as `border_title`.** `border-title-color: #E8B84B; border-title-style: bold`
    on the header only, `border-title-style: none` for the other boxes, so bold stays reserved
    for the header and the selected item. The border-title background never injects a colour.
12. **Not verified here.** The captures show what Textual writes. Whether Terminal.app, iTerm2
    and Ghostty render `49` as the profile background and reverse video as expected is U-1.

## Recommended theme/CSS

Copy into `src/leva/tui/theme.py` (colour constants from one palette mapping) and
`src/leva/tui/leva.tcss` (T-8.1). This is exactly what the `transparent` run of
`spikes/s1_textual_background.py` uses, minus the demo's layout-only `#body` and
`#search, #card` sizing rules.

```python
THEME = Theme(
    name="leva",
    primary="#E8B84B",
    secondary="#7A7A7A",
    accent="#E8B84B",
    warning="#E8B84B",
    error="#E85B4B",
    success="#4BE87A",
    foreground="#D4D4D4",
    background="ansi_default",
    surface="ansi_default",
    panel="ansi_default",
    boost="ansi_default",
    dark=True,
    ansi=True,
    variables={
        "ansi-background": "ansi_default",
        "ansi-foreground": "ansi_default",
        "block-cursor-foreground": "#E8B84B",
        "block-cursor-background": "ansi_default",
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-foreground": "#D4D4D4",
        "block-cursor-blurred-background": "ansi_default",
        "block-cursor-blurred-text-style": "none",
        "block-hover-background": "ansi_default",
        "border": "#3A3A3A",
        "border-blurred": "#3A3A3A",
        "input-cursor-background": "ansi_default",
        "input-cursor-foreground": "#E8B84B",
        "input-cursor-text-style": "reverse",
        "input-selection-background": "#3A3A3A",
        "input-selection-foreground": "#D4D4D4",
        "screen-selection-background": "#3A3A3A",
        "screen-selection-foreground": "#D4D4D4",
        "scrollbar": "#3A3A3A",
        "scrollbar-hover": "#7A7A7A",
        "scrollbar-active": "#E8B84B",
        "scrollbar-background": "ansi_default",
        "scrollbar-background-hover": "ansi_default",
        "scrollbar-background-active": "ansi_default",
        "scrollbar-corner-color": "ansi_default",
    },
)
```

Register it with `App.register_theme(THEME)` and set `self.theme = "leva"` in `__init__`.

```css
Screen { background: ansi_default; color: #D4D4D4; }
#header, #search, #card { border: solid #3A3A3A; background: ansi_default;
    border-title-color: #E8B84B; border-title-style: none; }
#header { height: 3; padding: 0 1; border-title-style: bold; }
#tagline { color: #7A7A7A; }
#status { height: 1; color: #4BE87A; }
#rule { height: 1; color: #3A3A3A; }
#keys { height: 1; color: #7A7A7A; }

Input { border: solid #3A3A3A; background: ansi_default; color: #D4D4D4;
    &:focus { border: solid #E8B84B; background-tint: transparent; }
    &>.input--placeholder { color: #7A7A7A; text-style: none; }
    &>.input--cursor { background: ansi_default; color: #E8B84B; text-style: reverse; }
}
OptionList { border: none; background: ansi_default; background-tint: transparent; padding: 0;
    &:focus { background-tint: transparent; }
    &>.option-list--option { color: #D4D4D4; }
    &>.option-list--option-highlighted { color: #E8B84B; text-style: bold;
        background: ansi_default; }
    &>.option-list--option-hover { background: ansi_default; }
    &>.option-list--option-hover-highlighted { color: #E8B84B; text-style: bold;
        background: ansi_default; }
    &>.option-list--separator { color: #3A3A3A; }
}
Tabs { background: ansi_default; height: 1; }
Tabs Underline { display: none; }
Tab { background: ansi_default; color: #7A7A7A; text-style: none;
    &.-active { color: #E8B84B; text-style: none; background: ansi_default; }
    &:hover { background: ansi_default; }
}
TabbedContent, TabPane, ContentSwitcher { background: ansi_default; }
VerticalScroll { background: ansi_default; scrollbar-size-vertical: 1; }
Toast { background: ansi_default; border: solid #3A3A3A; color: #D4D4D4;
    border-title-color: #E8B84B;
    &.-information { border-left: solid #3A3A3A; }
}
```

Rules for T-8.1 that follow from the findings:

- The only `background:` value in the stylesheet is `ansi_default` (a reset, not a colour).
  Every other widget Leva adds (`DataTable`, `RichLog`, `Markdown`, `Select`, …) must be run
  through `--analyze`-style capture before it ships.
- Variables `ansi-background` and `ansi-foreground` are mandatory in the Theme.
- Not covered by the demo: `Input`'s `.input--suggestion` (dim `ansi_default` under `:ansi`)
  and the `-invalid` state (`border: tall ansi_red`). Leva's search input uses neither; if
  T-8.x adds a suggester or validator, override both (secondary colour, `solid` error border).
- Palette test: every colour literal in `theme.py`/`leva.tcss` ∈ palette ∪ {`ansi_default`,
  `transparent`}; no `tall`, `wide`, `outer`, `round`, `heavy`, `double` border.
- Surface fallback (not used): replace `ansi_default` with `#1A1A1A` in the `background:` of the
  affected widget, add it to the T-8.1 allowance and note it in D-012.

## Manual verification checklist

Task U-1 (the user fills the table; automated results above do not replace it). For each of
Terminal.app, iTerm2 and Ghostty:

1. Create or pick a profile with a **non-black solid background** (for example a solid blue or
   beige) and select it.
2. Run, from the repository root:

   ```
   uv run python spikes/s1_textual_background.py --variant transparent --seconds 0
   ```

   The demo stays open until `q` (a priority binding, so it also quits while the input has
   focus). The toast probe is shown for Textual's default 5 s after start: check it first.
   Move with Tab to switch focus between the search input and
   the list, `↑`/`↓` in the list, `←`/`→` on the tabs, and scroll a tab's content.
3. Check every row of the table below and fill the cell (`ok`, `fail` plus a note).
4. Optional: repeat with `--variant surface --seconds 0` and note whether the `#1A1A1A`
   rectangles are acceptable on that profile.
5. Quit with `q`.

What to look for: the profile colour shows everywhere (no dark rectangles behind boxes, options,
input, tabs, scroll areas or the status/footer lines); borders are `┌ ┐ └ ┘ │ ─` in one grey;
box titles are accent-coloured and the header title is bold; the selected option row is bold
accent without a filled background; the input cursor is visible (reverse video) and the
placeholder is secondary grey; the scrollbar thumb is visible and the track is transparent;
the toast probe is a plain box with no coloured side bar.

| Check | Terminal.app | iTerm2 | Ghostty |
|---|---|---|---|
| No dark rectangle behind header and body boxes | TBD | TBD | TBD |
| No dark rectangle behind the options and the selected row | TBD | TBD | TBD |
| No dark rectangle behind the input; cursor visible | TBD | TBD | TBD |
| No dark rectangle behind tabs and the tab content | TBD | TBD | TBD |
| Borders are `┌ ┐ └ ┘ │ ─` with no gaps | TBD | TBD | TBD |
| Box titles accent, header title bold | TBD | TBD | TBD |
| Selected row bold accent | TBD | TBD | TBD |
| Scrollbar thumb visible, track transparent | TBD | TBD | TBD |
| Status line green, footer rule and keys readable | TBD | TBD | TBD |
| Toast probe has no coloured side bar | TBD | TBD | TBD |

## Decisions

- D-012 is amended (see DECISIONS): the theme needs the `ansi-background`/`ansi-foreground`
  variables, the cursor/placeholder/underline/scrollbar overrides above, and no `background:`
  other than `ansi_default`.
- The surface fallback stays documented and unused (finding 2).
- No new decision entry: the findings refine D-012 and the T-8.1 steps only.

## Impact on plan

T-8.1 (and nothing else) changes. Its steps now name the S-1 recommendation: the mandatory theme
variables, the `Input`/`Tabs`/`OptionList`/scrollbar/`Toast` overrides, the glyph restriction
(no `tall`/`outer` borders, hidden `Tabs` underline) and the palette test's allowed values
(`ansi_default`, `transparent`). The edit is recorded under D-012 in DECISIONS (R10). U-1 stays
open and non-blocking: if its results differ, T-8.1 adjusts.
