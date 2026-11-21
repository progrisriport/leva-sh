"""Enforce the D-019 branch-coverage thresholds per Leva package from a coverage JSON report.

Usage: ``python tools/coverage_gate.py [coverage.json]``. Exit status 0 when every package and
the overall total meet their threshold, 1 when any is below (a table names them), 2 when the
report cannot be used. Packages without statements are skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

STRICT_PACKAGES: Final = frozenset(
    {"placeholders", "content", "manparse", "store", "repo", "search", "ingest"}
)
STRICT_THRESHOLD: Final = 90
TUI_THRESHOLD: Final = 70
DEFAULT_THRESHOLD: Final = 85
OVERALL: Final = "overall"
ROOT_PACKAGE: Final = "leva"


class GateError(Exception):
    """The coverage report is missing, unreadable or not what this gate expects."""


@dataclass(frozen=True, slots=True)
class Tally:
    """Covered and total statements and branches; the percentage combines both (coverage.py)."""

    statements: int
    covered_statements: int
    branches: int = 0
    covered_branches: int = 0

    def __add__(self, other: Tally) -> Tally:
        return Tally(
            self.statements + other.statements,
            self.covered_statements + other.covered_statements,
            self.branches + other.branches,
            self.covered_branches + other.covered_branches,
        )

    @property
    def total(self) -> int:
        return self.statements + self.branches

    @property
    def covered(self) -> int:
        return self.covered_statements + self.covered_branches

    @property
    def percent_tenths(self) -> int:
        """Coverage in tenths of a percent, rounded down. Pre: ``total > 0``."""
        return 1000 * self.covered // self.total

    @property
    def percent_display(self) -> str:
        """Coverage such as ``89.9%``; rounded down, so a failing value never shows as passing."""
        tenths = self.percent_tenths
        return f"{tenths // 10}.{tenths % 10}%"

    def meets(self, threshold: int) -> bool:
        """Return whether coverage is at least ``threshold`` percent (exact, no rounding)."""
        return 100 * self.covered >= threshold * self.total


@dataclass(frozen=True, slots=True)
class Row:
    """One gated line of the report: a package or the overall total."""

    name: str
    tally: Tally
    threshold: int

    @property
    def passed(self) -> bool:
        return self.tally.meets(self.threshold)


@dataclass(frozen=True, slots=True)
class GateResult:
    """Rows sorted by package name with the overall row last, and the skipped packages."""

    rows: tuple[Row, ...]
    skipped: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return all(row.passed for row in self.rows)


def threshold_for(package: str) -> int:
    """Return the D-019 threshold, in percent, for a top-level package name."""
    if package in STRICT_PACKAGES:
        return STRICT_THRESHOLD
    if package == "tui":
        return TUI_THRESHOLD
    return DEFAULT_THRESHOLD


def package_of(path: str) -> str:
    """Return the top-level package of a measured file (``leva`` for the root ``__init__``).

    Raises:
        GateError: If the path has no ``leva`` directory component.
    """
    parts = PurePosixPath(path).parts
    directories = parts[:-1]
    if ROOT_PACKAGE not in directories:
        raise GateError(f"{path}: not inside the leva package")
    last = len(directories) - 1 - directories[::-1].index(ROOT_PACKAGE)
    below = parts[last + 1 :]
    return below[0] if len(below) > 1 else ROOT_PACKAGE


def tally_packages(report: object) -> dict[str, Tally]:
    """Sum the per-file summaries of a coverage JSON report by top-level package.

    Raises:
        GateError: If the report lacks branch data, has no files or a malformed summary.
    """
    if not isinstance(report, Mapping):
        raise GateError("not a coverage JSON object")
    meta = report.get("meta")
    if not isinstance(meta, Mapping) or meta.get("branch_coverage") is not True:
        raise GateError("report lacks branch coverage data (run coverage with branch = true)")
    files = report.get("files")
    if not isinstance(files, Mapping) or not files:
        raise GateError("report has no measured files")
    tallies: dict[str, Tally] = {}
    for path, entry in files.items():
        package = package_of(str(path))
        tally = file_tally(str(path), entry)
        tallies[package] = tallies.get(package, Tally(0, 0)) + tally
    return tallies


def file_tally(path: str, entry: object) -> Tally:
    """Read one file's ``summary`` into a Tally, checking every count."""
    summary = entry.get("summary") if isinstance(entry, Mapping) else None
    fields = summary if isinstance(summary, Mapping) else {}
    statements = count(path, fields, "num_statements")
    branches = count(path, fields, "num_branches")
    return Tally(
        statements,
        count(path, fields, "covered_lines", at_most=statements),
        branches,
        count(path, fields, "covered_branches", at_most=branches),
    )


def count(path: str, fields: Mapping[object, object], key: str, at_most: int | None = None) -> int:
    """Return a non-negative integer summary field, not above ``at_most`` when given."""
    value = fields.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GateError(f"{path}: summary.{key} is not a non-negative integer")
    if at_most is not None and value > at_most:
        raise GateError(f"{path}: summary.{key} exceeds its total ({value} > {at_most})")
    return value


def evaluate(tallies: Mapping[str, Tally]) -> GateResult:
    """Gate every package with statements, then the overall total of all packages."""
    measured = {name: tally for name, tally in tallies.items() if tally.statements > 0}
    rows = [Row(name, measured[name], threshold_for(name)) for name in sorted(measured)]
    overall = sum(measured.values(), Tally(0, 0))
    if overall.statements > 0:
        rows.append(Row(OVERALL, overall, DEFAULT_THRESHOLD))
    skipped = tuple(sorted(name for name in tallies if name not in measured))
    return GateResult(tuple(rows), skipped)


def render(result: GateResult) -> str:
    """Render the result as an aligned table plus skipped packages and a verdict line."""
    width = max(len("package"), *(len(row.name) for row in result.rows))
    lines = [f"{'package':<{width}}  {'covered':>8}  {'threshold':>9}  status"]
    lines.extend(
        f"{row.name:<{width}}  {row.tally.percent_display:>8}  {row.threshold:>8}%  "
        f"{'ok' if row.passed else 'FAIL'}"
        for row in result.rows
    )
    if result.skipped:
        lines.append(f"skipped (no statements): {', '.join(result.skipped)}")
    failed = [row.name for row in result.rows if not row.passed]
    lines.append(
        f"coverage gate: failed ({', '.join(failed)})" if failed else "coverage gate: passed"
    )
    return "\n".join(lines)


def load_report(path: Path) -> object:
    """Read and decode the coverage JSON file.

    Raises:
        GateError: If the file cannot be read or is not valid JSON.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateError(f"cannot read {path}: {exc.strerror}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GateError(f"{path}: invalid JSON ({exc.msg})") from exc


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate on a coverage JSON file and print the table; return the exit status."""
    parser = argparse.ArgumentParser(description="Enforce D-019 coverage thresholds.")
    parser.add_argument("report", nargs="?", default="coverage.json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(tally_packages(load_report(args.report)))
    except GateError as exc:
        print(f"coverage gate: {exc}", file=sys.stderr)
        return 2
    print(render(result))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
