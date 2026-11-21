"""Spike S-3: FTS5 availability across Python interpreters, prototype index size and latency.

Usage:
    uv run python spikes/s3_fts5.py --quick    # probes + prototype from a 200-page subset
    uv run python spikes/s3_fts5.py            # probes + prototype from every rendered page
    uv run python spikes/s3_fts5.py --json spikes/out/s3-full.json

Exit codes: 0 report produced and every required check ok under the project interpreter;
1 a required check failed under the project interpreter; 2 environment problem.

The report is structural only (counts, sizes, timings, command names). It never prints man
page prose, so its findings can be quoted in the S-3 doc.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from s2_mandoc import (
    MANDOC,
    NAME_SEPARATORS,
    QUICK_PAGES,
    Layout,
    Rendered,
    Report,
    benchmark_set,
    emit,
    layout,
    locate,
    man_dirs,
    manpath,
    render_all,
    scan_sources,
    strip_overstrike,
)
from s3_probe import REQUIRED

SPIKES = Path(__file__).resolve().parent
OUT = SPIKES / "out"
PROBE = SPIKES / "s3_probe.py"
PROBE_TIMEOUT_S = 60
PROBE_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}
PYTHON_DIRS = (Path("/usr/local/bin"), Path("/opt/homebrew/bin"))
SYSTEM_PYTHON = Path("/usr/bin/python3")
PYTHON_NAME = re.compile(r"python3(\.\d+)?")
HOMEBREW_PREFIXES = (Path("/opt/homebrew"), Path("/usr/local"))
RENDER_WORKERS = 8
MB = 1_000_000
TOP = 3
REPEAT = 10
SEARCH_SQL = (
    "SELECT rowid, bm25(search_fts, 10.0, 5.0, 2.0, 1.0) AS score FROM search_fts "
    "WHERE search_fts MATCH ? ORDER BY score LIMIT 50"
)
NAME_SQL = "SELECT name, section FROM entry WHERE id = ?"
ID_SQL = "SELECT id FROM entry WHERE name = ?"
QUERIES = (
    "ls",
    "tar",
    "copy file",
    "compress folder",
    "extract archive",
    "disk usage",
    "list processes",
    "kill process",
    "file permissions",
    "symbolic link",
    "search text",
    "regular expression",
    "environment variable",
    "ssh key",
    "git commit",
    "checksum",
    "network interface",
    "compr*",
    "perm*",
    "netw*",
)
NAME_QUERIES = ("ls", "tar")
SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE entry(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, section TEXT, kind TEXT NOT NULL,
    origin TEXT NOT NULL, summary TEXT NOT NULL, path TEXT, has_man INT NOT NULL,
    curated INT NOT NULL, explain TEXT, rank INT NOT NULL
);
CREATE UNIQUE INDEX entry_key ON entry(name, IFNULL(section, ''), origin);
CREATE TABLE alias(entry_id INT NOT NULL, alias TEXT NOT NULL);
CREATE INDEX alias_alias ON alias(alias);
CREATE TABLE doc_section(
    entry_id INT NOT NULL, ord INT NOT NULL, heading TEXT NOT NULL, body TEXT NOT NULL
);
CREATE VIRTUAL TABLE search_fts USING fts5(
    name, intents, summary, body, content='', tokenize='unicode61 remove_diacritics 2'
);
"""
INSERT_ENTRY = (
    "INSERT INTO entry(id, name, section, kind, origin, summary, path, has_man, curated, rank) "
    "VALUES (?, ?, ?, 'manpage', ?, ?, ?, 1, 0, 0)"
)
INSERT_SECTION = "INSERT INTO doc_section(entry_id, ord, heading, body) VALUES (?, ?, ?, ?)"
INSERT_FTS = "INSERT INTO search_fts(rowid, name, intents, summary, body) VALUES (?, ?, '', ?, ?)"
COUNT_SQL = {
    "entry": "SELECT count(*) FROM entry",
    "alias": "SELECT count(*) FROM alias",
    "doc_section": "SELECT count(*) FROM doc_section",
    "search_fts (docsize)": "SELECT count(*) FROM search_fts_docsize",
}
DBSTAT_SQL = "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name"
FTS_LABEL = "search_fts* (all FTS5 tables)"


@dataclass(frozen=True, slots=True)
class Candidate:
    label: str
    path: Path | None


@dataclass(frozen=True, slots=True)
class Row:
    name: str
    section: str
    origin: str
    path: str
    summary: str
    sections: tuple[tuple[str, str], ...]

    @property
    def body(self) -> str:
        return "\n".join(body for _, body in self.sections)


# Interpreters


def candidates() -> list[Candidate]:
    """The interpreters to probe, in order; a glob with no match becomes a `not present` row."""
    found = [Candidate("project (sys.executable)", Path(sys.executable))]
    for directory in PYTHON_DIRS:
        matches = [p for p in sorted(directory.glob("python3*")) if PYTHON_NAME.fullmatch(p.name)]
        found += [Candidate(str(p), p) for p in matches] or [
            Candidate(f"{directory}/python3*", None)
        ]
    found.append(Candidate(str(SYSTEM_PYTHON), SYSTEM_PYTHON if SYSTEM_PYTHON.exists() else None))
    return found


def unique(listed: Sequence[Candidate]) -> list[Candidate]:
    """Drop candidates that resolve to an interpreter already listed (first label wins)."""
    seen: set[Path] = set()
    kept: list[Candidate] = []
    for item in listed:
        real = item.path.resolve() if item.path else None
        if real is not None and real in seen:
            continue
        if real is not None:
            seen.add(real)
        kept.append(item)
    return kept


def first_line(text: str) -> str:
    return text.strip().partition("\n")[0][:200]


def run_probe(interpreter: Path) -> Report:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUT, prefix="s3-probe-") as scratch:
        argv = [str(interpreter), "-I", str(PROBE), scratch]
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                env=PROBE_ENV,
                stdin=subprocess.DEVNULL,
                timeout=PROBE_TIMEOUT_S,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        return {"error": f"exit {proc.returncode}: {first_line(proc.stderr)}"}
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"error": f"output is not JSON: {exc}"}
    return parsed if isinstance(parsed, dict) else {"error": "output is not a JSON object"}


def describe_probe(item: Candidate, probe: Report) -> Report:
    """Flatten one probe result into a report row (the raw compile options stay out)."""
    row: Report = {"label": item.label, "path": str(item.path) if item.path else "not present"}
    if item.path is None:
        return row | {"status": "not present"}
    if "error" in probe:
        return row | {"status": f"error: {probe['error']}"}
    checks = probe["checks"]
    options = probe["compile_options"]
    assert isinstance(checks, dict)  # noqa: S101 - the probe always emits a checks mapping
    assert isinstance(options, list)  # noqa: S101 - and a compile options list
    return row | {
        "status": "probed",
        "python": probe["python"],
        "sqlite": probe["sqlite"],
        "machine": probe["machine"],
        "threadsafety": probe["threadsafety"],
        "enable_fts5": "ENABLE_FTS5" in options,
        "enable_dbstat_vtab": "ENABLE_DBSTAT_VTAB" in options,
        "required_ok": required_ok(probe),
        "checks": {
            name: f"{'ok' if c['ok'] else 'FAIL'}: {c['detail']}" for name, c in checks.items()
        },
    }


def required_ok(probe: Report) -> bool:
    checks = probe.get("checks")
    if not isinstance(checks, dict):
        return False
    return all(isinstance(checks.get(n), dict) and checks[n].get("ok") is True for n in REQUIRED)


def probe_all() -> tuple[list[Report], bool | None]:
    """Probe every interpreter; the second value is the project interpreter's verdict.

    None means the project interpreter produced no probe result (an environment problem).
    """
    rows: list[Report] = []
    verdict: bool | None = None
    for index, item in enumerate(unique(candidates())):
        probe = run_probe(item.path) if item.path else {}
        rows.append(describe_probe(item, probe))
        if index == 0 and "error" not in probe:
            verdict = required_ok(probe)
    return rows, verdict


# Pages and rows


def summary_of(lay: Layout) -> str:
    """Text after the first NAME separator (D-027); empty when there is none."""
    body = next((b for heading, b in lay.sections if heading.strip().upper() == "NAME"), None)
    if body is None:
        return ""
    joined = " ".join(line.strip() for line in body if line.strip())
    found = sorted((joined.find(sep), sep) for sep in NAME_SEPARATORS if sep in joined)
    if not found:
        return ""
    position, separator = found[0]
    return joined[position + len(separator) :].strip()


def origin_of(path: Path) -> str:
    return "homebrew" if any(path.is_relative_to(p) for p in HOMEBREW_PREFIXES) else "macos"


def to_row(rendered: Rendered) -> Row:
    lay = layout(strip_overstrike(rendered.out.decode("utf-8", "replace")))
    page = rendered.page
    return Row(
        name=page.name,
        section=page.section,
        origin=origin_of(page.path),
        path=str(page.path),
        summary=summary_of(lay),
        sections=tuple((heading, "\n".join(body)) for heading, body in lay.sections),
    )


@contextmanager
def timed(timings: dict[str, float], label: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        timings[label] = round(time.perf_counter() - start, 3)


def collect_rows(quick: bool) -> tuple[list[Row], Report]:
    dirs, _ = man_dirs(manpath(None))
    pages, _ = locate(dirs)
    sources, _, _ = scan_sources(pages)
    chosen = benchmark_set(pages, sources)
    if quick:
        chosen = chosen[:: max(1, len(chosen) // QUICK_PAGES)][:QUICK_PAGES]
    wall, results = render_all(chosen, RENDER_WORKERS)
    kept = [r for r in results if not r.failed]
    start = time.perf_counter()
    rows = [to_row(r) for r in kept]
    parse_s = time.perf_counter() - start
    return rows, {
        "candidates": len(chosen),
        "rendered": len(kept),
        "failed": len(results) - len(kept),
        "render_wall_s": round(wall, 2),
        "parse_wall_s": round(parse_s, 3),
        "with_summary": sum(1 for r in rows if r.summary),
        "homebrew_origin": sum(1 for r in rows if r.origin == "homebrew"),
    }


# Prototype index


def file_size(path: Path) -> Report:
    size = path.stat().st_size
    return {"bytes": size, "mb": round(size / MB, 2)}


def fill_index(con: sqlite3.Connection, rows: Sequence[Row], timings: dict[str, float]) -> None:
    with timed(timings, "insert_entries_and_sections_s"):
        for entry_id, row in enumerate(rows, start=1):
            args = (entry_id, row.name, row.section, row.origin, row.summary, row.path)
            con.execute(INSERT_ENTRY, args)
            con.executemany(
                INSERT_SECTION,
                [(entry_id, i, h, b) for i, (h, b) in enumerate(row.sections)],
            )
    with timed(timings, "fts_fill_s"):
        con.executemany(
            INSERT_FTS,
            [(i, r.name, r.summary, r.body) for i, r in enumerate(rows, start=1)],
        )


def breakdown(con: sqlite3.Connection) -> dict[str, int] | str:
    try:
        raw = con.execute(DBSTAT_SQL).fetchall()
    except sqlite3.Error as exc:
        return f"unavailable: {exc}"
    totals: dict[str, int] = {}
    for name, size in raw:
        label = FTS_LABEL if name.startswith("search_fts") else name
        totals[label] = totals.get(label, 0) + size
    return dict(sorted(totals.items(), key=lambda item: -item[1]))


def build_index(rows: Sequence[Row], db_path: Path) -> Report:
    timings: dict[str, float] = {}
    sizes: dict[str, Report] = {}
    with closing(sqlite3.connect(db_path)) as con:
        con.executescript(SCHEMA)
        with con:
            fill_index(con, rows, timings)
        sizes["after_commit"] = file_size(db_path)
        with timed(timings, "optimize_s"), con:
            con.execute("INSERT INTO search_fts(search_fts) VALUES('optimize')")
        with timed(timings, "analyze_s"):
            con.execute("ANALYZE")
            con.commit()
        sizes["after_optimize_analyze"] = file_size(db_path)
        counts = {label: con.execute(sql).fetchone()[0] for label, sql in COUNT_SQL.items()}
        stats = breakdown(con)
        integrity = con.execute("PRAGMA integrity_check").fetchall()
        with timed(timings, "vacuum_s"):
            con.execute("VACUUM")
        sizes["after_vacuum"] = file_size(db_path)
    return {
        "rows": counts,
        "size": sizes,
        "size_breakdown_bytes_after_optimize_analyze": stats,
        "integrity_check": [r[0] for r in integrity],
        "timings_s": timings,
    }


# Latency


def match_expression(query: str) -> str:
    """Quote every token like T-4.4 will; a trailing `*` becomes a prefix query."""
    terms = []
    for token in query.split():
        word = token.rstrip("*").replace('"', '""')
        terms.append(f'"{word}"' + ("*" if token.endswith("*") else ""))
    return " ".join(terms)


def percentile(values: Sequence[float], q: int) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q / 100 * len(ordered)) - 1)]


def run_query(con: sqlite3.Connection, expression: str) -> tuple[float, list[int]]:
    start = time.perf_counter()
    hits = [row[0] for row in con.execute(SEARCH_SQL, (expression,)).fetchall()]
    return (time.perf_counter() - start) * 1000, hits


def top_names(con: sqlite3.Connection, hits: Sequence[int]) -> list[str]:
    names = [con.execute(NAME_SQL, (rowid,)).fetchone() for rowid in hits[:TOP]]
    return [f"{name}({section})" for name, section in names]


def measure_latency(db_path: Path, repeat: int) -> Report:
    uri = db_path.as_uri() + "?mode=ro"
    start = time.perf_counter()
    con = sqlite3.connect(uri, uri=True)
    with closing(con):
        run_query(con, match_expression(QUERIES[0]))
        open_first_ms = (time.perf_counter() - start) * 1000
        expressions = {q: match_expression(q) for q in QUERIES}
        for expression in expressions.values():
            run_query(con, expression)
        samples: dict[str, list[float]] = {q: [] for q in QUERIES}
        for _ in range(repeat):
            for query, expression in expressions.items():
                samples[query].append(run_query(con, expression)[0])
        per_query = {q: query_row(con, expressions[q], samples[q]) for q in QUERIES}
        name_ranks = {q: exact_name_rank(con, q) for q in NAME_QUERIES}
    everything = [ms for values in samples.values() for ms in values]
    return {
        "open_first_query_ms": round(open_first_ms, 2),
        "executions": len(everything),
        "p50_ms": round(percentile(everything, 50), 3),
        "p95_ms": round(percentile(everything, 95), 3),
        "max_ms": round(max(everything), 3),
        "exact_name_rank_in_top50": name_ranks,
        "queries": per_query,
    }


def exact_name_rank(con: sqlite3.Connection, name: str) -> int | None:
    """1-based position of the entry called `name` among the hits for that query, if any."""
    hits = run_query(con, match_expression(name))[1]
    wanted = {row[0] for row in con.execute(ID_SQL, (name,))}
    return next((i for i, rowid in enumerate(hits, start=1) if rowid in wanted), None)


def query_row(con: sqlite3.Connection, expression: str, samples: Sequence[float]) -> Report:
    hits = run_query(con, expression)[1]
    return {
        "median_ms": round(statistics.median(samples), 3),
        "hits": len(hits),
        "top3": top_names(con, hits),
    }


# Report


def environment() -> Report:
    return {
        "macos": platform.mac_ver()[0],
        "machine": platform.machine(),
        "cpus": os.cpu_count(),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "size_unit": "1 MB = 1,000,000 bytes",
    }


def build_report(quick: bool, repeat: int) -> tuple[Report, bool | None]:
    interpreters, verdict = probe_all()
    report: Report = {"environment": environment(), "interpreters": interpreters}
    if verdict is None:
        return report, None
    rows, pages = collect_rows(quick)
    report["pages"] = pages
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUT, prefix="s3-") as scratch:
        db_path = Path(scratch) / "index.db"
        report["index"] = build_index(rows, db_path)
        report["latency"] = measure_latency(db_path, repeat)
    return report, verdict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="prototype from a 200-page subset")
    parser.add_argument("--json", type=Path, help="also write the report as JSON to this path")
    parser.add_argument("--repeat", type=int, default=REPEAT, help="query passes (default 10)")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    if not MANDOC.is_file():
        print(f"mandoc not found at {MANDOC}")
        return 2
    report, verdict = build_report(args.quick, args.repeat)
    emit(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    if verdict is None:
        print("the project interpreter produced no probe result")
        return 2
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
