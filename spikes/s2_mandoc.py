"""Spike S-2: mandoc on sample macOS man pages and a full rendering benchmark.

Usage:
    uv run python spikes/s2_mandoc.py --quick    # samples + 200-page benchmark with 8 workers
    uv run python spikes/s2_mandoc.py            # samples + full benchmark, 1/2/4/6/8 workers x3
    uv run python spikes/s2_mandoc.py --json spikes/out/s2.json

The report is structural only (exit codes, counts, indents, timings, heading names). It
never prints man page prose, so its findings can be quoted in the S-2 doc.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import os
import platform
import re
import statistics
import subprocess
import tempfile
import time
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

MANDOC = Path("/usr/bin/mandoc")
COL = Path("/usr/bin/col")
MANPATH = Path("/usr/bin/manpath")
SW_VERS = Path("/usr/bin/sw_vers")
CLT_ROOT = Path("/Library/Developer/CommandLineTools")
EXTRA_MAN_DIRS = (Path("/opt/homebrew/share/man"), Path("/usr/local/share/man"))
USR_SHARE_MAN = Path("/usr/share/man")
CLT_SDK_MAN = CLT_ROOT / "SDKs/MacOSX.sdk/usr/share/man"
SECTIONS = ("1", "8")
WIDTH = 80
TIMEOUT_S = 10.0
QUICK_PAGES = 200
FULL_WORKERS = (1, 2, 4, 6, 8)
FULL_REPEAT = 3
QUICK_WORKERS = (8,)
TOP = 25
# The environment ADR-0002 §8 prescribes for every man subprocess, plus a fixed PATH.
ENV = MappingProxyType(
    {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LC_ALL": "en_US.UTF-8",
        "LANG": "en_US.UTF-8",
        "MANWIDTH": str(WIDTH),
        "TZ": "UTC",
    }
)
SAMPLES = (
    ("ls", "1"),
    ("tar", "1"),
    ("test", "1"),
    ("[", "1"),
    ("git", "1"),
    ("zshbuiltins", "1"),
    ("bash", "1"),
    ("builtin", "1"),
    ("find", "1"),
    ("grep", "1"),
    ("sed", "1"),
    ("launchctl", "1"),
    ("diskutil", "8"),
    ("defaults", "1"),
    ("brew", "1"),
    ("ssh", "1"),
    ("openssl", "1"),
)
# Samples whose every copy along the man path is reported, not only the winner.
ALL_COPIES = frozenset({"git", "openssl"})
# `-T ascii` transliterates dashes, so only ASCII separators can occur (non-ASCII is counted).
NAME_SEPARATORS = (" -- ", " - ")
COMMENT_PREFIXES = (b'.\\"', b"'\\\"", b".\\#")
DEFLIST_HEADING = re.compile(r"COMMANDS|VERBS|BUILTIN|OPTIONS")
D008_HEADING = re.compile(r"(SUB)?COMMANDS|VERBS")
OVERSTRIKE = re.compile(r".\x08")
INLINE_TERM = re.compile(r" *\S.*? {2,}\S")
UPPERCASE_HEADING = re.compile(r"[^a-z]*[A-Z][^a-z]*")
HEADER = re.compile(r"(?P<title>\S+)\((?P<sec>[^)]*)\)\s+(?P<vol>.*?)\s*(?P=title)\((?P=sec)\)")
INNER_SO = re.compile(rb"^\.so\s", re.MULTILINE)
FOOTER_LIKE = re.compile(r".*\S\([^)]*\)$")
# What `-T ascii` prints for a glyph it cannot transliterate.
UNKNOWN_GLYPH = "<?>"

Report = dict[str, object]


@dataclass(frozen=True, slots=True)
class Page:
    name: str
    section: str
    suffix: str
    path: Path
    dir_index: int

    @property
    def key(self) -> tuple[str, str]:
        return (self.name, self.section)

    @property
    def label(self) -> str:
        return f"{self.name}({self.suffix})"


@dataclass(frozen=True, slots=True)
class Source:
    digest: str
    size: int
    utf8: bool
    stub: str | None
    inner_so: bool


@dataclass(frozen=True, slots=True)
class Rendered:
    page: Page
    code: int | None
    out: bytes
    err: bytes
    seconds: float

    @property
    def failed(self) -> bool:
        """Non-zero exit, timeout, or nothing but the header and footer lines (D-007)."""
        return self.code != 0 or sum(1 for line in self.out.splitlines() if line.strip()) <= 2


@dataclass(frozen=True, slots=True)
class Layout:
    header: str
    footer: str
    sections: tuple[tuple[str, tuple[str, ...]], ...]
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NameLine:
    separator: str
    names: int
    lines: int
    indent: int


@dataclass(frozen=True, slots=True)
class PageStats:
    label: str
    seconds: float
    overstrike: bool
    residual_backspace: bool
    non_ascii: int
    tabs: int
    controls: int
    max_line: int
    long_lines: int
    unknown_glyphs: int
    footer_glyph: bool
    volume: str | None
    name: NameLine
    headings: tuple[str, ...]
    subsection_lines: int


# Discovery


def run_text(argv: Sequence[str], env: Mapping[str, str] | None) -> str:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=True,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=TIMEOUT_S,
    ).stdout


def manpath(env: Mapping[str, str] | None) -> list[Path]:
    return [Path(part) for part in run_text([str(MANPATH)], env).strip().split(":") if part]


def man_dirs(listed: Sequence[Path]) -> tuple[list[Path], list[Path]]:
    """Apply D-004: manpath order, then the extra dirs, deduplicated; missing dirs dropped."""
    ordered = list(dict.fromkeys([*listed, *EXTRA_MAN_DIRS]))
    return [d for d in ordered if d.is_dir()], [d for d in ordered if not d.is_dir()]


def parse_filename(filename: str, section: str) -> tuple[str, str] | None:
    stem = filename.removesuffix(".gz")
    name, dot, suffix = stem.rpartition(".")
    if not dot or not name or not suffix.startswith(section):
        return None
    return name, suffix


def locate(dirs: Sequence[Path]) -> tuple[list[Page], list[str]]:
    pages: list[Page] = []
    skipped: list[str] = []
    for index, root in enumerate(dirs):
        for section in SECTIONS:
            subdir = root / f"man{section}"
            if not subdir.is_dir():
                continue
            for path in sorted(subdir.iterdir()):
                parsed = parse_filename(path.name, section) if path.is_file() else None
                if parsed is None:
                    skipped.append(f"{subdir.name}/{path.name}")
                    continue
                pages.append(Page(parsed[0], section, parsed[1], path, index))
    return pages, skipped


def group_by_key(pages: Iterable[Page]) -> dict[tuple[str, str], list[Page]]:
    groups: dict[tuple[str, str], list[Page]] = defaultdict(list)
    for page in pages:
        groups[page.key].append(page)
    return groups


# Sources


def read_source(path: Path) -> bytes:
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as handle:
            return handle.read()
    return path.read_bytes()


def stub_target(source: bytes) -> str | None:
    """Return the `.so` target when the first roff request of the page is `.so`."""
    for raw in source.splitlines():
        line = raw.strip()
        if line in (b"", b".") or line.startswith(COMMENT_PREFIXES):
            continue
        parts = line.split(maxsplit=1)
        if parts[0] == b".so" and len(parts) == 2:
            return parts[1].decode("utf-8", "replace")
        return None
    return None


def is_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def scan_source(path: Path) -> Source | None:
    try:
        data = read_source(path)
    except (OSError, EOFError, zlib.error):
        return None
    stub = stub_target(data)
    return Source(
        digest=hashlib.sha256(data).hexdigest(),
        size=len(data),
        utf8=is_utf8(data),
        stub=stub,
        inner_so=stub is None and INNER_SO.search(data) is not None,
    )


def scan_sources(pages: Sequence[Page]) -> tuple[dict[Path, Source], list[Page], float]:
    start = time.perf_counter()
    sources: dict[Path, Source] = {}
    unreadable: list[Page] = []
    for page in pages:
        source = scan_source(page.path)
        if source is None:
            unreadable.append(page)
        else:
            sources[page.path] = source
    return sources, unreadable, time.perf_counter() - start


def man_root(page: Page) -> Path:
    """The directory holding `man<section>/`: what `man` uses as cwd, so `.so` resolves."""
    return page.path.parent.parent


def resolve_stub(page: Page, target: str) -> Path | None:
    for base in (man_root(page), page.path.parent):
        for candidate in (base / target, base / f"{target}.gz"):
            if candidate.is_file():
                return Path(os.path.normpath(candidate))
    return None


# Rendering


def render(page: Page, cwd: Path | None = None, device: str = "ascii") -> Rendered:
    argv = [str(MANDOC), "-T", device, "-O", f"width={WIDTH}", str(page.path)]
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            check=False,
            env=ENV,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return Rendered(page, None, b"", b"", time.perf_counter() - start)
    return Rendered(page, proc.returncode, proc.stdout, proc.stderr, time.perf_counter() - start)


def render_in_root(page: Page) -> Rendered:
    return render(page, cwd=man_root(page))


def render_all(pages: Sequence[Page], workers: int) -> tuple[float, list[Rendered]]:
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(render_in_root, pages))
    return time.perf_counter() - start, results


def strip_overstrike(text: str) -> str:
    return OVERSTRIKE.sub("", text)


def col_bx(raw: bytes) -> str:
    return subprocess.run(
        [str(COL), "-bx"],
        input=raw,
        capture_output=True,
        check=True,
        env=ENV,
        timeout=TIMEOUT_S,
    ).stdout.decode("utf-8", "replace")


def overstrike_agreement(raw: bytes) -> str:
    """Compare Python overstrike stripping with `col -bx` on one rendered page."""
    ours, theirs = strip_overstrike(raw.decode("utf-8", "replace")), col_bx(raw)
    if ours == theirs:
        return "identical"
    if [line.rstrip() for line in ours.splitlines()] == [
        line.rstrip() for line in theirs.splitlines()
    ]:
        return "trailing-whitespace-only"
    return "different"


# Structure of rendered text


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def split_sections(lines: Sequence[str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    found: list[tuple[str, list[str]]] = []
    for line in lines:
        if line and not line[0].isspace():
            found.append((line.rstrip(), []))
        elif found:
            found[-1][1].append(line)
    return tuple((heading, tuple(body)) for heading, body in found)


def layout(text: str) -> Layout:
    lines = text.splitlines()
    content = [i for i, line in enumerate(lines) if line.strip()]
    if len(content) < 2:
        return Layout("", "", (), tuple(lines))
    first, last = content[0], content[-1]
    inner = lines[first + 1 : last]
    return Layout(lines[first].strip(), lines[last].strip(), split_sections(inner), tuple(inner))


def analyze_name(lay: Layout) -> NameLine:
    body = next((body for heading, body in lay.sections if heading == "NAME"), None)
    if body is None:
        return NameLine("missing", 0, 0, -1)
    content = [line for line in body if line.strip()]
    if not content:
        return NameLine("empty", 0, 0, -1)
    joined = " ".join(line.strip() for line in content)
    found = sorted((joined.find(sep), sep) for sep in NAME_SEPARATORS if sep in joined)
    if not found:
        return NameLine("none", 1, len(content), indent_of(content[0]))
    position, separator = found[0]
    names = [name for name in joined[:position].split(",") if name.strip()]
    return NameLine(repr(separator), len(names), len(content), indent_of(content[0]))


def header_volume(header: str) -> str | None:
    match = HEADER.fullmatch(header)
    return match.group("vol") if match else None


def analyze(rendered: Rendered) -> PageStats:
    raw = rendered.out.decode("utf-8", "replace")
    text = strip_overstrike(raw)
    lay = layout(text)
    widths = [len(line) for line in text.splitlines()] or [0]
    return PageStats(
        label=rendered.page.label,
        seconds=rendered.seconds,
        overstrike="\b" in raw,
        residual_backspace="\b" in text,
        non_ascii=sum(1 for byte in rendered.out if byte > 0x7F),
        tabs=raw.count("\t"),
        controls=sum(1 for char in raw if ord(char) < 0x20 and char not in "\n\b\t"),
        max_line=max(widths),
        long_lines=sum(1 for width in widths if width > WIDTH),
        unknown_glyphs=sum(line.count(UNKNOWN_GLYPH) for line in lay.lines),
        footer_glyph=UNKNOWN_GLYPH in lay.footer,
        volume=header_volume(lay.header),
        name=analyze_name(lay),
        headings=tuple(heading for heading, _ in lay.sections),
        subsection_lines=sum(1 for line in lay.lines if re.match(r" {3}\S", line)),
    )


def definition_list(heading: str, body: Sequence[str]) -> Report | None:
    """Infer the term/body indents of a definition list from indent transitions."""
    rows = [(indent_of(line), line) for line in body if line.strip()]
    deeper = Counter((a[0], b[0]) for a, b in itertools.pairwise(rows) if b[0] > a[0])
    if not deeper:
        return None
    (term_indent, body_indent), transitions = deeper.most_common(1)[0]
    terms = [line for indent, line in rows if indent == term_indent]
    shallowest = min(indent for indent, _ in rows)
    shallow_terms = {
        a[1].split()[0] for a, b in itertools.pairwise(rows) if a[0] == shallowest < b[0]
    }
    return {
        "heading": heading,
        "d008_match": D008_HEADING.fullmatch(heading) is not None,
        "indents_top": {str(k): v for k, v in Counter(i for i, _ in rows).most_common(5)},
        "deeper_transitions_top": {f"{a}->{b}": n for (a, b), n in deeper.most_common(3)},
        "term_indent": term_indent,
        "body_indent": body_indent,
        "transitions": transitions,
        "lines_at_term_indent": len(terms),
        "inline_terms": sum(1 for line in terms if INLINE_TERM.match(line)),
        "distinct_first_tokens": len({line.split()[0] for line in terms}),
        "shallowest_indent": shallowest,
        "distinct_terms_at_shallowest_indent": len(shallow_terms),
    }


# Reports


def environment(listed_inherited: Sequence[Path], listed_minimal: Sequence[Path]) -> Report:
    pairs = (line.split(":", 1) for line in run_text([str(SW_VERS)], ENV).splitlines())
    info = {key.strip(): value.strip() for key, value in pairs}
    return {
        "macos": f"{info.get('ProductVersion', '?')} ({info.get('BuildVersion', '?')})",
        "arch": platform.machine(),
        "cpus": os.cpu_count(),
        "python": platform.python_version(),
        "mandoc": f"{MANDOC} {'present' if MANDOC.is_file() else 'MISSING'}",
        "col": f"{COL} {'present' if COL.is_file() else 'MISSING'}",
        "command_line_tools": CLT_ROOT.is_dir(),
        "manpath_inherited_env": [str(d) for d in listed_inherited],
        "manpath_minimal_env": [str(d) for d in listed_minimal],
    }


def clt_overlap(
    pages: Sequence[Page], dirs: Sequence[Path], sources: Mapping[Path, Source]
) -> Report:
    def keyed(root: Path) -> dict[tuple[str, str], Page]:
        found: dict[tuple[str, str], Page] = {}
        for page in pages:
            if dirs[page.dir_index] == root:
                found.setdefault(page.key, page)
        return found

    usr, sdk = keyed(USR_SHARE_MAN), keyed(CLT_SDK_MAN)
    both = usr.keys() & sdk.keys()
    only_sdk = sorted(f"{name}({section})" for name, section in sdk.keys() - usr.keys())
    identical = sum(
        1
        for key in both
        if usr[key].path in sources
        and sdk[key].path in sources
        and sources[usr[key].path].digest == sources[sdk[key].path].digest
    )
    return {
        "usr_share_man_keys": len(usr),
        "clt_sdk_keys": len(sdk),
        "in_both": len(both),
        "in_both_identical_source": identical,
        "only_in_sdk": len(only_sdk),
        "only_in_sdk_first": only_sdk[:TOP],
    }


def discovery(
    dirs: Sequence[Path],
    missing: Sequence[Path],
    pages: Sequence[Page],
    skipped: Sequence[str],
    sources: Mapping[Path, Source],
) -> Report:
    groups = group_by_key(pages)
    losers = [(copies[0], extra) for copies in groups.values() for extra in copies[1:]]
    return {
        "man_dirs": [f"[{i}] {d}" for i, d in enumerate(dirs)],
        "missing_dirs": [str(d) for d in missing],
        "files_per_dir": {
            str(dirs[i]): n for i, n in sorted(Counter(p.dir_index for p in pages).items())
        },
        "files_total": len(pages),
        "skipped_names": len(skipped),
        "skipped_first": skipped[:TOP],
        "unique_keys": len(groups),
        "shadowed_copies": len(losers),
        "shadowed_by_dir_pair": dict(
            Counter(f"[{w.dir_index}] beats [{lo.dir_index}]" for w, lo in losers).most_common(TOP)
        ),
        "same_dir_duplicates": [
            f"{w.label} vs {lo.label} in [{w.dir_index}]"
            for w, lo in losers
            if w.dir_index == lo.dir_index
        ][:TOP],
        "suffixes_other_than_section": dict(
            Counter(p.suffix for p in pages if p.suffix not in SECTIONS).most_common(TOP)
        ),
        "gz_files": sum(1 for p in pages if p.path.suffix == ".gz"),
        "usr_share_man_vs_clt_sdk": clt_overlap(pages, dirs, sources),
    }


def stub_outcome(page: Page, target: str, dirs: Sequence[Path], keys: set[tuple[str, str]]) -> str:
    """Classify what a winning stub can become under D-005."""
    resolved = resolve_stub(page, target)
    if resolved is None:
        return "target missing"
    if not any(resolved.is_relative_to(d) for d in dirs):
        return "target outside every man dir"
    section = resolved.parent.name.removeprefix("man")
    parsed = parse_filename(resolved.name, section)
    if parsed and (parsed[0], section) in keys:
        return "alias on an indexed page"
    return "target not an indexed page"


def stubs(
    pages: Sequence[Page],
    dirs: Sequence[Path],
    sources: Mapping[Path, Source],
    unreadable: Sequence[Page],
) -> Report:
    stub_pages = [
        (p, sources[p.path].stub or "") for p in pages if p.path in sources and sources[p.path].stub
    ]
    groups = group_by_key(p for p in pages if p.path in sources)
    shadowing = [
        f"{copies[0].label} [{copies[0].dir_index}] -> {sources[copies[0].path].stub}"
        for copies in groups.values()
        if sources[copies[0].path].stub and any(not sources[c.path].stub for c in copies[1:])
    ]
    unresolved = [(p, t) for p, t in stub_pages if resolve_stub(p, t) is None]
    winners = [
        (copies[0], sources[copies[0].path].stub or "")
        for copies in groups.values()
        if sources[copies[0].path].stub
    ]
    outcomes = [(p, stub_outcome(p, t, dirs, set(groups))) for p, t in winners]
    return {
        "unreadable_sources": [str(p.path) for p in unreadable],
        "non_utf8_sources": sum(1 for s in sources.values() if not s.utf8),
        "stubs": len(stub_pages),
        "stubs_per_dir": {
            str(k): v for k, v in sorted(Counter(p.dir_index for p, _ in stub_pages).items())
        },
        "stub_target_forms": dict(
            Counter("manN/file" if "/" in t else "bare file" for _, t in stub_pages).items()
        ),
        "stub_target_section_dirs": dict(
            Counter(f"man{p.section} -> {t.partition('/')[0]}" for p, t in stub_pages).most_common()
        ),
        "stub_targets_unresolved": len(unresolved),
        "stub_targets_unresolved_by_dir": {
            str(k): v for k, v in sorted(Counter(p.dir_index for p, _ in unresolved).items())
        },
        "stub_targets_unresolved_first": [
            f"{p.label} [{p.dir_index}] -> {t}" for p, t in unresolved
        ][:5],
        "winning_stubs": len(winners),
        "winning_stub_outcomes": dict(Counter(o for _, o in outcomes).most_common()),
        "winning_stub_not_alias_first": [
            f"{p.label} [{p.dir_index}]: {o}"
            for p, o in outcomes
            if o != "alias on an indexed page"
        ][:8],
        "stub_first_copy_shadows_real_page": shadowing[:TOP],
        "pages_with_so_after_first_request": [
            str(p.path) for p in pages if p.path in sources and sources[p.path].inner_so
        ],
    }


def render_summary(rendered: Rendered) -> Report:
    return {
        "exit": rendered.code,
        "stderr_first_line": rendered.err.decode("utf-8", "replace").partition("\n")[0][:120],
        "out_bytes": len(rendered.out),
        "ms": round(rendered.seconds * 1000, 1),
    }


def structure_summary(rendered: Rendered) -> Report:
    stats = analyze(rendered)
    lay = layout(strip_overstrike(rendered.out.decode("utf-8", "replace")))
    duplicates = [h for h, n in Counter(stats.headings).items() if n > 1]
    deflists = [
        definition_list(heading, body)
        for heading, body in lay.sections
        if DEFLIST_HEADING.search(heading)
    ]
    return {
        "header_volume": stats.volume,
        "footer": lay.footer,
        "name": f"sep={stats.name.separator} names={stats.name.names} "
        f"lines={stats.name.lines} indent={stats.name.indent}",
        "headings": list(stats.headings),
        "duplicate_headings": duplicates,
        "non_uppercase_headings": [h for h in stats.headings if not UPPERCASE_HEADING.fullmatch(h)],
        "subsection_lines_at_indent_3": stats.subsection_lines,
        "definition_lists": [d for d in deflists if d is not None],
        "overstrike": stats.overstrike,
        "python_vs_col_bx": overstrike_agreement(rendered.out),
        "non_ascii_bytes": stats.non_ascii,
        "tabs": stats.tabs,
        "max_line": stats.max_line,
    }


def stub_render(page: Page, target: str, neutral: Path) -> Report:
    resolved = resolve_stub(page, target)
    return {
        "so_target": target,
        "target_resolved": str(resolved) if resolved else None,
        "mandoc_cwd_neutral": render_summary(render(page, cwd=neutral)),
        "mandoc_cwd_man_root": render_summary(render(page, cwd=man_root(page))),
    }


def exit_code_probes(scratch: Path) -> Report:
    """Render synthetic edge-case inputs (written here, never third-party) to learn exit codes."""
    inputs = {
        "missing file": None,
        "empty file": b"",
        "plain text without macros": b"just text\n",
        "invalid UTF-8 bytes": b".TH X 1\n.SH NAME\nx \\- caf\xe9 \xff\n",
        "unknown macro": b".TH X 1\n.SH NAME\nx \\- y\n.ZZ bogus\n",
        ".so to a missing target": b".so man1/absent.1\n",
        "binary garbage": bytes(range(256)) * 4,
    }
    report: Report = {}
    for index, (label, data) in enumerate(inputs.items()):
        path = scratch / f"probe{index}.1"
        if data is not None:
            path.write_bytes(data)
        rendered = render(Page(f"probe{index}", "1", "1", path, -1), cwd=scratch)
        report[label] = render_summary(rendered) | {
            "non_ascii_out_bytes": sum(1 for byte in rendered.out if byte > 0x7F)
        }
    return report


def sample(page: Page, dirs: Sequence[Path], source: Source | None, neutral: Path) -> Report:
    entry: Report = {
        "page": page.label,
        "path": str(page.path),
        "dir": f"[{page.dir_index}] {dirs[page.dir_index]}",
        "gz": page.path.suffix == ".gz",
        "source_bytes": source.size if source else None,
        "source_utf8": source.utf8 if source else None,
    }
    if source and source.stub:
        return entry | stub_render(page, source.stub, neutral)
    rendered = render(page, cwd=neutral)
    entry |= render_summary(rendered)
    return entry | structure_summary(rendered) if not rendered.failed else entry


def pick_samples(pages: Sequence[Page], sources: Mapping[Path, Source]) -> list[tuple[str, Page]]:
    groups = group_by_key(pages)
    picked: list[tuple[str, Page]] = []
    for name, section in SAMPLES:
        copies = groups.get((name, section), [])
        chosen = copies if name in ALL_COPIES else copies[:1]
        picked.extend((name, page) for page in chosen)
    man1 = [p for p in pages if p.section == "1" and p.path in sources]
    if man1:
        picked.append(("largest man1", max(man1, key=lambda p: sources[p.path].size)))
    gz = next((p for p in pages if p.path.suffix == ".gz"), None)
    if gz:
        picked.append(("first .gz", gz))
    return picked


def missing_samples(pages: Sequence[Page]) -> list[str]:
    keys = {p.key for p in pages}
    return [f"{name}({section})" for name, section in SAMPLES if (name, section) not in keys]


def benchmark_set(pages: Sequence[Page], sources: Mapping[Path, Source]) -> list[Page]:
    """The pages ingest would render: the first copy per (name, section), unless it is a stub."""
    readable = (p for p in pages if p.path in sources)
    winners = (copies[0] for copies in group_by_key(readable).values())
    return sorted((p for p in winners if not sources[p.path].stub), key=lambda p: p.key)


def run_summary(workers: int, walls: Sequence[float], results: Sequence[Rendered]) -> Report:
    failures = [r for r in results if r.failed]
    best = min(walls)
    return {
        "workers": workers,
        "pages": len(results),
        "wall_s_each_repeat": [round(wall, 2) for wall in walls],
        "wall_s_median": round(statistics.median(walls), 2),
        "pages_per_s_best": round(len(results) / best, 1) if best else None,
        "failures": len(failures),
        "timeouts": sum(1 for r in results if r.code is None),
        "exit_codes": {
            str(k): v for k, v in sorted(Counter(r.code for r in results).items(), key=str)
        },
        "stderr_nonempty": sum(1 for r in results if r.err.strip()),
        "failed_first": [f"{r.page.label} exit={r.code} {r.page.path}" for r in failures][:TOP],
    }


def corpus(results: Sequence[Rendered]) -> Report:
    stats = [analyze(r) for r in results if not r.failed]
    return {"pages_analyzed": len(stats)} | corpus_text(stats) | corpus_structure(stats)


def corpus_text(stats: Sequence[PageStats]) -> Report:
    return {
        "overstrike_pages": sum(1 for s in stats if s.overstrike),
        "residual_backspace_after_strip": sum(1 for s in stats if s.residual_backspace),
        "non_ascii_output_pages": sum(1 for s in stats if s.non_ascii),
        "tab_pages": sum(1 for s in stats if s.tabs),
        "other_control_char_pages": sum(1 for s in stats if s.controls),
        "unknown_glyph_in_footer_pages": sum(1 for s in stats if s.footer_glyph),
        "unknown_glyph_in_body_pages": sum(1 for s in stats if s.unknown_glyphs),
        "unknown_glyph_in_body_first": [s.label for s in stats if s.unknown_glyphs][:TOP],
        "pages_with_lines_over_width": sum(1 for s in stats if s.long_lines),
        "widest_pages": {s.label: s.max_line for s in sorted(stats, key=lambda s: -s.max_line)[:8]},
        "slowest_ms": {
            s.label: round(s.seconds * 1000, 1) for s in sorted(stats, key=lambda s: -s.seconds)[:8]
        },
    }


def corpus_structure(stats: Sequence[PageStats]) -> Report:
    headings = Counter(h for s in stats for h in s.headings)
    duplicated = Counter(h for s in stats for h, n in Counter(s.headings).items() if n > 1)
    return {
        "header_matches_title_pattern": sum(1 for s in stats if s.volume is not None),
        "header_mismatch_first": [s.label for s in stats if s.volume is None][:TOP],
        "header_volumes": dict(Counter(s.volume for s in stats if s.volume).most_common(12)),
        "pages_without_headings": [s.label for s in stats if not s.headings][:TOP],
        "footer_like_headings_first": [
            f"{s.label}: {h}"
            for s in stats
            for h in s.headings
            if FOOTER_LIKE.fullmatch(h) or h.startswith(UNKNOWN_GLYPH)
        ][:8],
        "letterless_headings_first": [
            f"{s.label}: {h[:20]}..."
            for s in stats
            for h in s.headings
            if not any(c.isalpha() for c in h)
        ][:8],
        "name_separator": dict(Counter(s.name.separator for s in stats).most_common()),
        "name_separator_none_first": [s.label for s in stats if s.name.separator == "none"][:8],
        "name_missing": [
            f"{s.label}: first headings {list(s.headings[:3])}"
            for s in stats
            if s.name.separator in ("missing", "empty")
        ],
        "name_multiple_names": sum(1 for s in stats if s.name.names > 1),
        "name_multiline": sum(1 for s in stats if s.name.lines > 1),
        "name_indent": {str(k): v for k, v in Counter(s.name.indent for s in stats).most_common()},
        "headings_top": dict(headings.most_common(TOP)),
        "non_uppercase_headings": dict(
            Counter(
                h for s in stats for h in s.headings if not UPPERCASE_HEADING.fullmatch(h)
            ).most_common(12)
        ),
        "pages_with_duplicate_headings": sum(
            1 for s in stats if len(set(s.headings)) < len(s.headings)
        ),
        "duplicate_heading_names": dict(duplicated.most_common(12)),
        "d008_headings": dict(
            Counter(h for h in headings.elements() if D008_HEADING.fullmatch(h)).most_common(TOP)
        ),
        "headings_containing_commands_or_verbs": dict(
            Counter(h for h in headings.elements() if re.search(r"COMMANDS|VERBS", h)).most_common(
                TOP
            )
        ),
        "pages_with_subsection_lines": sum(1 for s in stats if s.subsection_lines),
    }


def overstrike_pass(results: Sequence[Rendered]) -> Report:
    ok = [r for r in results if not r.failed]
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        verdicts = list(pool.map(lambda r: overstrike_agreement(r.out), ok))
    col_seconds = time.perf_counter() - start
    start = time.perf_counter()
    for r in ok:
        strip_overstrike(r.out.decode("utf-8", "replace"))
    return {
        "pages": len(ok),
        "verdicts": dict(Counter(verdicts).most_common()),
        "different_first": [
            r.page.label for r, v in zip(ok, verdicts, strict=True) if v == "different"
        ][:TOP],
        "python_strip_total_s": round(time.perf_counter() - start, 3),
        "col_and_compare_total_s_8_workers": round(col_seconds, 2),
    }


def benchmark(
    pages: Sequence[Page], workers: Sequence[int], repeat: int, quick: bool
) -> tuple[Report, list[Rendered]]:
    chosen = (
        list(pages[:: max(1, len(pages) // QUICK_PAGES)][:QUICK_PAGES]) if quick else list(pages)
    )
    runs: list[Report] = []
    last: list[Rendered] = []
    for count in workers:
        walls: list[float] = []
        for _ in range(repeat):
            wall, last = render_all(chosen, count)
            walls.append(wall)
        runs.append(run_summary(count, walls, last))
    return {
        "set": "quick subset" if quick else "first copy per (name, section), stubs excluded",
        "cwd": "the page's man root (man semantics)",
        "runs": runs,
    }, last


def footer_glyph(pages: Sequence[Page]) -> str | None:
    """Render one Apple mdoc page as UTF-8 to name the glyph `-T ascii` shows as `<?>`."""
    page = next((p for p in pages if p.key == ("ls", "1")), None)
    if page is None:
        return None
    text = strip_overstrike(render(page, cwd=man_root(page), device="utf8").out.decode())
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first = lines[-1][0] if lines else ""
    return f"U+{ord(first):04X}" if first and ord(first) > 0x7F else None


# Output


def fmt(value: object) -> str:
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def emit(value: object, depth: int = 0) -> None:
    pad = "  " * depth
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, dict | list) and item:
                print(f"{pad}{key}:")
                emit(item, depth + 1)
            else:
                print(f"{pad}{key}: {fmt(item)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict | list):
                print(f"{pad}-")
                emit(item, depth + 1)
            else:
                print(f"{pad}- {fmt(item)}")


def build_report(quick: bool, repeat: int) -> Report:
    inherited, minimal = manpath(None), manpath(ENV)
    dirs, missing = man_dirs(inherited)
    pages, skipped = locate(dirs)
    sources, unreadable, scan_s = scan_sources(pages)
    report: Report = {
        "environment": environment(inherited, minimal) | {"footer_glyph": footer_glyph(pages)},
        "discovery": discovery(dirs, missing, pages, skipped, sources),
        "sources": stubs(pages, dirs, sources, unreadable)
        | {"scan_and_stub_detection_s": round(scan_s, 2)},
        "missing_samples": missing_samples(pages),
    }
    with tempfile.TemporaryDirectory(prefix="leva-s2-") as neutral:
        report["samples"] = [
            {"sample": label} | sample(page, dirs, sources.get(page.path), Path(neutral))
            for label, page in pick_samples(pages, sources)
        ]
    with tempfile.TemporaryDirectory(prefix="leva-s2-") as scratch:
        report["exit_code_probes"] = exit_code_probes(Path(scratch))
    bench, results = benchmark(
        benchmark_set(pages, sources), QUICK_WORKERS if quick else FULL_WORKERS, repeat, quick
    )
    report["benchmark"] = bench
    report["corpus"] = corpus(results)
    if not quick:
        report["overstrike_check"] = overstrike_pass(results)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="samples + a 200-page benchmark")
    parser.add_argument("--json", type=Path, help="also write the report as JSON to this path")
    parser.add_argument(
        "--repeat", type=int, default=None, help="runs per worker count (default: 1 quick, 3 full)"
    )
    args = parser.parse_args()
    if not MANDOC.is_file():
        print(f"mandoc not found at {MANDOC}")
        return 2
    repeat = args.repeat or (1 if args.quick else FULL_REPEAT)
    report = build_report(quick=args.quick, repeat=repeat)
    emit(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
