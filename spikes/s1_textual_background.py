"""Spike S-1: does Textual keep the terminal's own background with only palette colours?

Usage:
    uv run python spikes/s1_textual_background.py --selftest
    uv run python spikes/s1_textual_background.py --variant transparent [--bare] [--seconds 1.0]
    uv run python spikes/s1_textual_background.py --variant surface [--bare] [--seconds 0]
    uv run python spikes/s1_textual_background.py --analyze [--json PATH] [--size 100x30]

`--seconds 0` keeps the demo open until `q` (manual checklist U-1). `--analyze` runs the demo
four times in a pty (transparent, surface, then both with `--bare`), parses the SGR sequences it
writes and gates the two recommended runs. `--selftest` checks the parser and the gate on
synthetic sequences.

Exit codes of --analyze: 0 every run captured and both recommended runs pass the gate; 1 a
recommended run violates the gate; 2 harness failure (pty error, timeout, child failure, or the
header text is missing from the capture). --selftest exits 0 or fails an assertion.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.theme import Theme
from textual.widgets import Input, OptionList, Static, TabbedContent, TabPane

SPIKE = Path(__file__).resolve()
RAW_DIR = SPIKE.parent / "out"
HARD_TIMEOUT_S = 20.0
DEFAULT_SIZE = (100, 30)
TAGLINE = "less effort, more thought"
HEADER = "Leva"
PALETTE = {
    "accent": "#E8B84B",
    "text": "#D4D4D4",
    "secondary": "#7A7A7A",
    "border": "#3A3A3A",
    "error": "#E85B4B",
    "success": "#4BE87A",
}
SURFACE = "#1A1A1A"
SURFACE_SOFT = "#202020"
SURFACE_HEXES = (SURFACE, SURFACE_SOFT)
PALETTE_HEXES = frozenset(PALETTE.values())
REQUIRED_GLYPHS = "┌┐└┘│─"
FORBIDDEN_GLYPHS = "╭╮╰╯┏┓┗┛━┃╸╺╔╗╚╝═║▊▎▔▁▀▄▌▐"
SGR_DEFAULT = "39"
BG_DEFAULT = "49"
BASIC_FG = frozenset([*map(str, range(30, 38)), *map(str, range(90, 98))])
BASIC_BG = frozenset([*map(str, range(40, 48)), *map(str, range(100, 108))])
EXTENDED_COLOUR_SELECTORS = {"38": "fg", "48": "bg"}
CSI = re.compile(r"\x1b\[([0-?]*)([ -/]*)([@-~])")
OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
OTHER_ESCAPE = re.compile(r"\x1b[()][0-9A-Za-z]|\x1b[=>78cDEHMNOZ]")
SYNTHETIC_FOOTER = "/ search   ↑↓ move   Enter open   q quit"
OPTIONS = ("ls", "cp", "mv", "tar", "grep", "find")
TAB_TITLES = ("Overview", "Examples", "Manual")


@dataclass(frozen=True, slots=True)
class SurfaceFallback:
    """A neutral surface hex a widget may use because it cannot be transparent."""

    hex: str
    reason: str


# widget -> fallback. Empty: S-1 found no widget in the recommended demo that needs one.
SURFACE_FALLBACKS: Mapping[str, SurfaceFallback] = {}


@dataclass(slots=True)
class SgrStats:
    """Colour codes and text attributes seen in a stream of SGR sequences."""

    fg: Counter[str] = field(default_factory=Counter)
    bg: Counter[str] = field(default_factory=Counter)
    bold: int = 0
    reverse: int = 0
    underline: int = 0
    resets: int = 0
    unparsed: list[str] = field(default_factory=list)


def _hex(red: str, green: str, blue: str) -> str | None:
    try:
        values = [int(part) for part in (red, green, blue)]
    except ValueError:
        return None
    if not all(0 <= v <= 255 for v in values):
        return None
    return "#{:02X}{:02X}{:02X}".format(*values)


def _extended_colour(params: Sequence[str]) -> str | None:
    """Colour key for the parameters after 38/48 (`2;r;g;b` or `5;n`), else None."""
    if params[:1] == ["2"] and len(params) >= 4:
        return _hex(*params[1:4])
    if params[:1] == ["5"] and len(params) >= 2 and params[1].isdigit():
        return f"5;{params[1]}"
    return None


def _colon_colour(token: str) -> tuple[str, str | None]:
    """Parse `38:2::r:g:b`, `38:2:r:g:b` or `38:5:n` into (selector, colour key)."""
    selector, _, rest = token.partition(":")
    parts = rest.split(":")
    if parts[:1] == ["2"] and len(parts) >= 5:  # colour-space id slot present
        parts = [parts[0], *parts[2:]]
    return selector, _extended_colour(parts)


def _record_colour(stats: SgrStats, selector: str, key: str | None, raw: str) -> None:
    if key is None:
        stats.unparsed.append(raw)
        return
    target = stats.fg if EXTENDED_COLOUR_SELECTORS[selector] == "fg" else stats.bg
    target[key] += 1


def _apply_simple(stats: SgrStats, code: str) -> None:
    if code in ("", "0"):
        stats.resets += 1
    elif code == "1":
        stats.bold += 1
    elif code == "7":
        stats.reverse += 1
    elif code == "4":
        stats.underline += 1
    elif code == SGR_DEFAULT or code in BASIC_FG:
        stats.fg[code] += 1
    elif code == BG_DEFAULT or code in BASIC_BG:
        stats.bg[code] += 1


def _apply_sgr(stats: SgrStats, params: str) -> None:
    tokens = params.split(";")
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if ":" in token:
            selector, key = _colon_colour(token)
            if selector in EXTENDED_COLOUR_SELECTORS:
                _record_colour(stats, selector, key, token)
            continue
        if token in EXTENDED_COLOUR_SELECTORS:
            width = 4 if tokens[index : index + 1] == ["2"] else 2
            raw = ";".join(tokens[index - 1 : index + width])
            _record_colour(stats, token, _extended_colour(tokens[index : index + width]), raw)
            index += width
        else:
            _apply_simple(stats, token)


def parse_sgr(data: str) -> SgrStats:
    """Collect colour codes and attributes from every SGR sequence in `data`.

    Colours are keyed `#RRGGBB` (truecolour), `5;n` (256-colour) or the plain code (`39`,
    `49`, `31`, `101`). Non-SGR CSI sequences are ignored; malformed colour parameters are
    recorded in `unparsed` and never raise.
    """
    stats = SgrStats()
    for match in CSI.finditer(data):
        params, intermediate, final = match.groups()
        if final == "m" and not intermediate and params[:1] not in ("<", "=", ">", "?"):
            _apply_sgr(stats, params)
    return stats


def strip_escapes(data: str) -> str:
    """Remove CSI, OSC and other escape sequences, leaving the drawn text."""
    return OTHER_ESCAPE.sub("", OSC.sub("", CSI.sub("", data)))


def check_colours(
    stats: SgrStats, variant: str, fallbacks: Mapping[str, SurfaceFallback] = SURFACE_FALLBACKS
) -> list[str]:
    """Return the gate violations of `stats` for a recommended `variant` run."""
    listed = {fallback.hex for fallback in fallbacks.values()} & set(SURFACE_HEXES)
    violations = [
        f"foreground {colour} is off-palette"
        for colour in sorted(stats.fg)
        if colour != SGR_DEFAULT and colour not in PALETTE_HEXES
    ]
    violations += [f"unparsed colour sequence {raw!r}" for raw in stats.unparsed]
    allowed_surfaces = set(SURFACE_HEXES) if variant == "surface" else listed
    for colour in sorted(stats.bg):
        if colour == BG_DEFAULT or colour in allowed_surfaces:
            continue
        reason = (
            "surface hex not listed in SURFACE_FALLBACKS"
            if colour in SURFACE_HEXES
            else "background is not 49 or a neutral surface"
        )
        violations.append(f"background {colour}: {reason}")
    return violations


def check_glyphs(text: str) -> list[str]:
    """Return violations for missing box glyphs and present forbidden glyphs."""
    violations = [f"missing box glyph {g}" for g in REQUIRED_GLYPHS if g not in text]
    violations += [f"forbidden glyph {g}" for g in FORBIDDEN_GLYPHS if g in text]
    return violations


def gate(
    stats: SgrStats,
    text: str,
    variant: str,
    fallbacks: Mapping[str, SurfaceFallback] = SURFACE_FALLBACKS,
) -> list[str]:
    """All gate violations of a recommended run (empty list = pass)."""
    return check_colours(stats, variant, fallbacks) + check_glyphs(text)


class SelftestError(Exception):
    """A selftest expectation failed."""


def expect(actual: object, expected: object, what: str) -> None:
    """Raise SelftestError unless `actual == expected`."""
    if actual != expected:
        raise SelftestError(f"{what}: expected {expected!r}, got {actual!r}")


def selftest_parser() -> None:
    """Parser expectations on synthetic sequences."""
    one = parse_sgr("\x1b[38;2;232;184;75;49mX")
    expect((dict(one.fg), dict(one.bg)), ({"#E8B84B": 1}, {"49": 1}), "fg+default bg")
    two = parse_sgr("\x1b[1;48;2;26;26;26mX")
    expect((two.bold, dict(two.bg), dict(two.fg)), (1, {"#1A1A1A": 1}, {}), "bold+truecolour bg")
    for reset in ("\x1b[0m", "\x1b[m"):
        stats = parse_sgr(reset)
        expect((stats.resets, dict(stats.fg), dict(stats.bg)), (1, {}, {}), f"reset {reset!r}")
    expect(dict(parse_sgr("\x1b[38;5;208mX").fg), {"5;208": 1}, "256-colour fg")
    expect(dict(parse_sgr("\x1b[41mX").bg), {"41": 1}, "basic bg 41")
    expect(dict(parse_sgr("\x1b[101mX").bg), {"101": 1}, "bright bg 101")
    default = parse_sgr("\x1b[39;49mX")
    expect((dict(default.fg), dict(default.bg)), ({"39": 1}, {"49": 1}), "default fg+bg")
    expect(dict(parse_sgr("\x1b[38:2::232:184:75mX").fg), {"#E8B84B": 1}, "colon form with id")
    expect(dict(parse_sgr("\x1b[38:2:232:184:75mX").fg), {"#E8B84B": 1}, "colon form")
    broken = parse_sgr("\x1b[38:2:1mX\x1b[38;2;1m")
    expect((dict(broken.fg), len(broken.unparsed)), ({}, 2), "malformed colours are unparsed")
    for ignored in ("\x1b[?2048$p", "\x1b[2J", "\x1b[10;5H", "\x1b[?1049h"):
        stats = parse_sgr(ignored)
        expect((dict(stats.fg), dict(stats.bg), stats.bold), ({}, {}, 0), f"ignored {ignored!r}")
    expect(strip_escapes("\x1b[1mLeva\x1b[0m\x1b]0;t\x07 ┌─┐"), "Leva ┌─┐", "strip_escapes")


def selftest_gate() -> None:
    """Gate expectations on synthetic stats."""
    off = parse_sgr("\x1b[38;2;1;2;3mX")
    expect(
        check_colours(off, "transparent"), ["foreground #010203 is off-palette"], "off-palette fg"
    )
    surface = parse_sgr("\x1b[48;2;26;26;26mX")
    expect(
        check_colours(surface, "transparent", {}),
        [f"background {SURFACE}: surface hex not listed in SURFACE_FALLBACKS"],
        "unlisted surface in transparent",
    )
    listed = {"toast": SurfaceFallback(SURFACE, "synthetic")}
    expect(check_colours(surface, "transparent", listed), [], "listed surface in transparent")
    expect(check_colours(surface, "surface", {}), [], "surface in surface variant")
    red = parse_sgr("\x1b[48;2;255;0;0mX")
    expect(
        check_colours(red, "transparent", {"x": SurfaceFallback("#FF0000", "synthetic")}),
        ["background #FF0000: background is not 49 or a neutral surface"],
        "listed non-surface hex is still a violation",
    )
    expect(
        check_colours(parse_sgr("\x1b[38;2;1mX"), "surface", {}),
        ["unparsed colour sequence '38;2;1'"],
        "unparsed colour",
    )
    expect(
        check_colours(parse_sgr("\x1b[41mX"), "surface", {}),
        ["background 41: background is not 49 or a neutral surface"],
        "basic bg",
    )
    expect(check_glyphs("┌┐└┘│─"), [], "all glyphs present")
    expect(check_glyphs("┌┐└┘│─╭"), ["forbidden glyph ╭"], "forbidden glyph")
    expect(check_glyphs("┌"), [f"missing box glyph {g}" for g in "┐└┘│─"], "missing glyphs")


def selftest() -> None:
    """Run every selftest expectation and print `selftest ok`."""
    selftest_parser()
    selftest_gate()
    print("selftest ok")


# Textual's Screen CSS reads these two even in fullscreen mode; an ansi theme must define them.
BASE_VARIABLES = {
    "ansi-background": "ansi_default",
    "ansi-foreground": "ansi_default",
}
CSS_VARIABLES = {
    "block-cursor-foreground": PALETTE["accent"],
    "block-cursor-background": "ansi_default",
    "block-cursor-text-style": "bold",
    "block-cursor-blurred-foreground": PALETTE["text"],
    "block-cursor-blurred-background": "ansi_default",
    "block-cursor-blurred-text-style": "none",
    "block-hover-background": "ansi_default",
    "border": PALETTE["border"],
    "border-blurred": PALETTE["border"],
    "input-cursor-background": "ansi_default",
    "input-cursor-foreground": PALETTE["accent"],
    "input-cursor-text-style": "reverse",
    "input-selection-background": PALETTE["border"],
    "input-selection-foreground": PALETTE["text"],
    "screen-selection-background": PALETTE["border"],
    "screen-selection-foreground": PALETTE["text"],
    "scrollbar": PALETTE["border"],
    "scrollbar-hover": PALETTE["secondary"],
    "scrollbar-active": PALETTE["accent"],
    "scrollbar-background": "ansi_default",
    "scrollbar-background-hover": "ansi_default",
    "scrollbar-background-active": "ansi_default",
    "scrollbar-corner-color": "ansi_default",
}


def build_theme(variant: str, bare: bool) -> Theme:
    """The palette theme: ansi=True, ansi_default backgrounds (surface variant: see CSS)."""
    return Theme(
        name=f"leva-{variant}{'-bare' if bare else ''}",
        primary=PALETTE["accent"],
        secondary=PALETTE["secondary"],
        accent=PALETTE["accent"],
        warning=PALETTE["accent"],
        error=PALETTE["error"],
        success=PALETTE["success"],
        foreground=PALETTE["text"],
        background="ansi_default",
        surface="ansi_default",
        panel="ansi_default",
        boost="ansi_default",
        dark=True,
        ansi=True,
        variables=BASE_VARIABLES if bare else BASE_VARIABLES | CSS_VARIABLES,
    )


def build_css(variant: str, bare: bool) -> str:
    """Leva's TCSS for the demo; `bare` leaves Textual's defaults on top of the theme."""
    fill = SURFACE if variant == "surface" else "ansi_default"
    boxes = f"""
    Screen {{ background: {fill}; color: {PALETTE["text"]}; }}
    #header, #search, #card {{ border: solid {PALETTE["border"]}; background: {fill};
        border-title-color: {PALETTE["accent"]}; border-title-style: none; }}
    #header {{ height: 3; padding: 0 1; border-title-style: bold; }}
    #body {{ height: 1fr; }}
    #search, #card {{ width: 1fr; }}
    #tagline {{ color: {PALETTE["secondary"]}; }}
    #status {{ height: 1; color: {PALETTE["success"]}; }}
    #rule {{ height: 1; color: {PALETTE["border"]}; }}
    #keys {{ height: 1; color: {PALETTE["secondary"]}; }}
    """
    if bare:
        return boxes
    return (
        boxes
        + f"""
    Input {{ border: solid {PALETTE["border"]}; background: {fill}; color: {PALETTE["text"]};
        &:focus {{ border: solid {PALETTE["accent"]}; background-tint: transparent; }}
        &>.input--placeholder {{ color: {PALETTE["secondary"]}; text-style: none; }}
        &>.input--cursor {{ background: ansi_default; color: {PALETTE["accent"]};
            text-style: reverse; }}
    }}
    OptionList {{ border: none; background: {fill}; background-tint: transparent;
        padding: 0;
        &:focus {{ background-tint: transparent; }}
        &>.option-list--option {{ color: {PALETTE["text"]}; }}
        &>.option-list--option-highlighted {{ color: {PALETTE["accent"]}; text-style: bold;
            background: {fill}; }}
        &>.option-list--option-hover {{ background: {fill}; }}
        &>.option-list--option-hover-highlighted {{ color: {PALETTE["accent"]};
            text-style: bold; background: {fill}; }}
        &>.option-list--separator {{ color: {PALETTE["border"]}; }}
    }}
    Tabs {{ background: {fill}; height: 1; }}
    Tabs Underline {{ display: none; }}
    Tab {{ background: {fill}; color: {PALETTE["secondary"]}; text-style: none;
        &.-active {{ color: {PALETTE["accent"]}; text-style: none; background: {fill}; }}
        &:hover {{ background: {fill}; }}
    }}
    TabbedContent, TabPane, ContentSwitcher {{ background: {fill}; }}
    VerticalScroll {{ background: {fill}; scrollbar-size-vertical: 1; }}
    Toast {{ background: {fill}; border: solid {PALETTE["border"]}; color: {PALETTE["text"]};
        border-title-color: {PALETTE["accent"]};
        &.-information {{ border-left: solid {PALETTE["border"]}; }}
    }}
    """
    )


class DemoApp(App[None]):
    """Header box, two body boxes, status line and footer, as Leva's wide layout."""

    # priority: the focused Input would otherwise consume `q` as text.
    BINDINGS: ClassVar[list[BindingType]] = [Binding("q", "quit", "quit", priority=True)]

    def __init__(self, variant: str, bare: bool, seconds: float) -> None:
        super().__init__()
        self._seconds = seconds
        self.CSS = build_css(variant, bare)
        theme = build_theme(variant, bare)
        self.register_theme(theme)
        self.theme = theme.name

    def compose(self) -> ComposeResult:
        with Vertical(id="header"):
            yield Static(TAGLINE, id="tagline")
        with Horizontal(id="body"):
            with Vertical(id="search"):
                yield Input(placeholder="search commands", id="query")
                yield OptionList(*OPTIONS, id="results")
            with Vertical(id="card"), TabbedContent(*TAB_TITLES):
                for title in TAB_TITLES:
                    with TabPane(title), VerticalScroll():
                        yield Static("\n".join(f"{title} line {n}" for n in range(60)))
        yield Static("copied: ls -la", id="status")
        yield Static("─" * 200, id="rule")
        yield Static(SYNTHETIC_FOOTER, id="keys")

    def on_mount(self) -> None:
        self.query_one("#header").border_title = HEADER
        self.query_one("#search").border_title = "Search"
        self.query_one("#card").border_title = "Card"
        self.query_one("#results", OptionList).highlighted = 1
        self.notify("toast probe")
        if self._seconds > 0:
            # Input focused first (cursor on the placeholder), then the list (focused cursor row).
            self.set_timer(self._seconds / 2, self.query_one("#results").focus)
            self.set_timer(self._seconds, self.exit)


def run_app(variant: str, bare: bool, seconds: float) -> int:
    """Run the demo app until the timer fires or `q` is pressed; return its exit code."""
    app = DemoApp(variant, bare, seconds)
    app.run()
    return app.return_code or 0


@dataclass(frozen=True, slots=True)
class RunSpec:
    """One analyzed run."""

    variant: str
    bare: bool

    @property
    def label(self) -> str:
        return f"{self.variant}{' --bare' if self.bare else ''}"

    @property
    def gated(self) -> bool:
        return not self.bare


RUNS = (
    RunSpec("transparent", False),
    RunSpec("surface", False),
    RunSpec("transparent", True),
    RunSpec("surface", True),
)


class HarnessError(Exception):
    """The pty run itself failed (exit code 2)."""


def child_env(home: str, size: tuple[int, int]) -> dict[str, str]:
    """Explicit environment for the pty child: truecolour, no colour-changing variables."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": home,
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
        "COLUMNS": str(size[0]),
        "LINES": str(size[1]),
    }


def _read_all(master: int, proc: subprocess.Popen[bytes]) -> bytes:
    chunks: list[bytes] = []
    deadline = time.monotonic() + HARD_TIMEOUT_S
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            os.killpg(proc.pid, signal.SIGKILL)
            raise HarnessError(f"child timeout after {HARD_TIMEOUT_S:.0f} s")
        ready, _, _ = select.select([master], [], [], min(remaining, 0.5))
        if not ready:
            continue
        try:
            chunk = os.read(master, 65536)
        except OSError:  # EIO on macOS once the child closed the slave
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def capture(spec: RunSpec, size: tuple[int, int], seconds: float) -> str:
    """Run the demo in a pty of `size` (cols, rows) and return everything it wrote."""
    try:
        master, slave = pty.openpty()
    except OSError as exc:
        raise HarnessError(f"pty unavailable: {exc}") from exc
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", size[1], size[0], 0, 0))
    argv = [sys.executable, str(SPIKE), "--variant", spec.variant, "--seconds", str(seconds)]
    argv += ["--bare"] if spec.bare else []
    with tempfile.TemporaryDirectory() as home:
        proc = subprocess.Popen(
            argv,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=child_env(home, size),
            start_new_session=True,
        )
        os.close(slave)
        try:
            data = _read_all(master, proc)
        finally:
            os.close(master)
        code = proc.wait()
    if code != 0:
        raise HarnessError(f"child exited {code}")
    text = data.decode("utf-8", errors="replace")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / f"s1-{spec.label.replace(' ', '')}.raw").write_text(text, encoding="utf-8")
    return text


@dataclass(slots=True)
class RunReport:
    """Parsed result of one run."""

    spec: RunSpec
    stats: SgrStats
    glyphs_present: str
    forbidden_present: str
    violations: list[str]


def analyze_run(spec: RunSpec, size: tuple[int, int], seconds: float) -> RunReport:
    """Capture one run and apply the gate (violations are empty for `--bare`)."""
    data = capture(spec, size, seconds)
    text = strip_escapes(data)
    for needed in (HEADER, TAGLINE):
        if needed not in text:
            raise HarnessError(f"{spec.label}: capture does not contain {needed!r}")
    stats = parse_sgr(data)
    return RunReport(
        spec=spec,
        stats=stats,
        glyphs_present="".join(g for g in REQUIRED_GLYPHS if g in text),
        forbidden_present="".join(g for g in FORBIDDEN_GLYPHS if g in text),
        violations=gate(stats, text, spec.variant) if spec.gated else [],
    )


def _counts(counter: Counter[str]) -> str:
    return ", ".join(f"{key} x{count}" for key, count in sorted(counter.items())) or "-"


def format_report(report: RunReport) -> str:
    """One report block for a run."""
    stats = report.stats
    off = sorted(c for c in stats.fg if c != SGR_DEFAULT and c not in PALETTE_HEXES)
    lines = [
        f"== {report.spec.label} ({'gated' if report.spec.gated else 'informational'})",
        f"  background codes : {_counts(stats.bg)}",
        f"  foreground       : {_counts(stats.fg)}",
        f"  off-palette fg   : {', '.join(off) or '-'}",
        f"  box glyphs       : {report.glyphs_present or '-'}",
        f"  forbidden glyphs : {report.forbidden_present or '-'}",
        f"  bold / reverse / underline : {stats.bold} / {stats.reverse} / {stats.underline}",
        f"  unparsed         : {len(stats.unparsed)}",
    ]
    if report.spec.gated:
        lines.append("  gate             : " + ("PASS" if not report.violations else "FAIL"))
        lines += [f"    - {violation}" for violation in report.violations]
    return "\n".join(lines)


def to_json(report: RunReport) -> dict[str, object]:
    """Structured form of a run report."""
    stats = report.stats
    return {
        "run": report.spec.label,
        "gated": report.spec.gated,
        "bg": dict(sorted(stats.bg.items())),
        "fg": dict(sorted(stats.fg.items())),
        "bold": stats.bold,
        "reverse": stats.reverse,
        "underline": stats.underline,
        "unparsed": stats.unparsed,
        "glyphs": report.glyphs_present,
        "forbidden": report.forbidden_present,
        "violations": report.violations,
    }


def analyze(size: tuple[int, int], json_path: Path | None, seconds: float) -> int:
    """Run every spec, print the reports and summary, return the exit code."""
    reports: list[RunReport] = []
    try:
        for spec in sorted(RUNS, key=lambda s: (s.bare, s.variant != "transparent")):
            reports.append(analyze_run(spec, size, seconds))
    except HarnessError as exc:
        print(f"harness failure: {exc}", file=sys.stderr)
        return 2
    for report in reports:
        print(format_report(report))
    failed = [r.spec.label for r in reports if r.violations]
    print(
        f"\nsummary: {len(reports)} runs at {size[0]}x{size[1]}; gate failures: "
        f"{', '.join(failed) or 'none'}"
    )
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps([to_json(r) for r in reports], indent=2) + "\n")
    return 1 if failed else 0


def parse_size(value: str) -> tuple[int, int]:
    """Parse `COLSxROWS`."""
    match = re.fullmatch(r"(\d+)x(\d+)", value)
    if match is None:
        raise argparse.ArgumentTypeError(f"expected COLSxROWS, got {value!r}")
    return int(match[1]), int(match[2])


def build_parser() -> argparse.ArgumentParser:
    """Command line of the spike."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--variant", choices=("transparent", "surface"), default="transparent")
    parser.add_argument("--bare", action="store_true", help="Textual defaults, no Leva overrides")
    parser.add_argument("--seconds", type=float, default=1.0, help="auto-exit; 0 = until q")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--size", type=parse_size, default=DEFAULT_SIZE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    if args.analyze:
        return analyze(args.size, args.json, args.seconds)
    return run_app(args.variant, args.bare, args.seconds)


if __name__ == "__main__":
    sys.exit(main())
