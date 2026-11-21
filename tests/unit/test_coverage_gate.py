"""Coverage gate (D-019): per-package branch coverage thresholds read from coverage JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.coverage_gate import (
    GateError,
    Tally,
    evaluate,
    main,
    package_of,
    tally_packages,
    threshold_for,
)

JsonObject = dict[str, object]


def summary(
    statements: int, covered: int, branches: int = 0, covered_branches: int = 0
) -> JsonObject:
    return {
        "summary": {
            "num_statements": statements,
            "covered_lines": covered,
            "num_branches": branches,
            "covered_branches": covered_branches,
        }
    }


def report(files: dict[str, JsonObject], *, branch: bool = True) -> JsonObject:
    return {"meta": {"format": 3, "branch_coverage": branch}, "files": files}


def write_report(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# packages and thresholds ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "package"),
    [
        ("src/leva/store/_writer.py", "store"),
        ("src/leva/store/__init__.py", "store"),
        ("src/leva/tui/screens/_card.py", "tui"),
        ("src/leva/__init__.py", "leva"),
        ("/abs/site-packages/leva/repo/__init__.py", "repo"),
    ],
)
def test_package_of_maps_a_file_to_its_d002_package(path: str, package: str) -> None:
    assert package_of(path) == package


def test_package_of_rejects_files_outside_leva() -> None:
    with pytest.raises(GateError, match="not inside the leva package"):
        package_of("tools/coverage_gate.py")


@pytest.mark.parametrize(
    ("package", "threshold"),
    [
        *[(p, 90) for p in ("placeholders", "content", "manparse", "store", "repo", "search")],
        ("ingest", 90),
        ("tui", 70),
        ("cli", 85),
        ("verify", 85),
        ("model", 85),
        ("leva", 85),
    ],
)
def test_threshold_for_follows_d019(package: str, threshold: int) -> None:
    assert threshold_for(package) == threshold


# tallies --------------------------------------------------------------------------------------


def test_tally_combines_statements_and_branches_like_coverage_py() -> None:
    tally = Tally(statements=10, covered_statements=8, branches=2, covered_branches=1)

    assert tally.percent_tenths == 750
    assert tally.meets(75)
    assert not tally.meets(76)


def test_tally_threshold_boundary_is_inclusive_and_exact() -> None:
    assert Tally(statements=10, covered_statements=9).meets(90)
    assert not Tally(statements=1000, covered_statements=899).meets(90)


def test_tally_percent_display_never_rounds_a_failure_up() -> None:
    assert Tally(statements=1000, covered_statements=899).percent_display == "89.9%"
    assert Tally(statements=3, covered_statements=2).percent_display == "66.6%"
    assert Tally(statements=4, covered_statements=4).percent_display == "100.0%"


def test_tally_packages_sums_files_per_package() -> None:
    tallies = tally_packages(
        report(
            {
                "src/leva/store/__init__.py": summary(4, 4),
                "src/leva/store/_writer.py": summary(6, 3, branches=4, covered_branches=2),
                "src/leva/tui/__init__.py": summary(2, 1),
            }
        )
    )

    assert tallies == {
        "store": Tally(statements=10, covered_statements=7, branches=4, covered_branches=2),
        "tui": Tally(statements=2, covered_statements=1),
    }


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "not a coverage JSON object"),
        ({"meta": {"branch_coverage": True}}, "no measured files"),
        (report({}), "no measured files"),
        (report({"src/leva/a.py": summary(1, 1)}, branch=False), "branch coverage"),
        ({"files": {"src/leva/a.py": summary(1, 1)}}, "branch coverage"),
        (report({"src/leva/a.py": {}}), "num_statements"),
        (report({"src/leva/a.py": {"summary": {"num_statements": "1"}}}), "num_statements"),
        (report({"src/leva/a.py": {"summary": {"num_statements": True}}}), "num_statements"),
        (report({"src/leva/a.py": summary(1, -1)}), "covered_lines"),
        (report({"src/leva/a.py": summary(1, 2)}), "covered_lines"),
        (report({"src/leva/a.py": summary(1, 1, branches=2, covered_branches=3)}), "branches"),
    ],
)
def test_tally_packages_rejects_malformed_reports(data: object, message: str) -> None:
    with pytest.raises(GateError, match=message):
        tally_packages(data)


# evaluation -----------------------------------------------------------------------------------


def test_evaluate_skips_packages_without_statements_and_adds_overall() -> None:
    tallies = {
        "cli": Tally(statements=0, covered_statements=0),
        "store": Tally(statements=10, covered_statements=9),
    }

    result = evaluate(tallies)

    assert [(row.name, row.threshold, row.passed) for row in result.rows] == [
        ("store", 90, True),
        ("overall", 85, True),
    ]
    assert result.skipped == ("cli",)
    assert result.passed


def test_evaluate_fails_a_package_below_its_threshold() -> None:
    result = evaluate({"store": Tally(statements=100, covered_statements=87)})

    assert not result.passed
    assert [(row.name, row.passed) for row in result.rows] == [("store", False), ("overall", True)]


def test_evaluate_fails_overall_even_when_every_package_passes() -> None:
    result = evaluate(
        {
            "tui": Tally(statements=100, covered_statements=70),
            "model": Tally(statements=10, covered_statements=10),
        }
    )

    assert [(row.name, row.passed) for row in result.rows] == [
        ("model", True),
        ("tui", True),
        ("overall", False),
    ]
    assert not result.passed


# command line ---------------------------------------------------------------------------------


def test_main_passes_and_prints_a_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_report(
        tmp_path,
        report({"src/leva/__init__.py": summary(4, 4), "src/leva/cli/__init__.py": summary(0, 0)}),
    )

    assert main([str(path)]) == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0].split() == ["package", "covered", "threshold", "status"]
    assert out[1].split() == ["leva", "100.0%", "85%", "ok"]
    assert out[2].split() == ["overall", "100.0%", "85%", "ok"]
    assert out[3] == "skipped (no statements): cli"
    assert out[4] == "coverage gate: passed"


def test_main_fails_with_exit_1_and_names_the_failing_packages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_report(
        tmp_path,
        report(
            {
                "src/leva/store/__init__.py": summary(10, 8),
                "src/leva/tui/__init__.py": summary(10, 7),
            }
        ),
    )

    assert main([str(path)]) == 1

    out = capsys.readouterr().out.splitlines()
    assert out[1].split() == ["store", "80.0%", "90%", "FAIL"]
    assert out[2].split() == ["tui", "70.0%", "70%", "ok"]
    assert out[3].split() == ["overall", "75.0%", "85%", "FAIL"]
    assert out[-1] == "coverage gate: failed (store, overall)"


def test_main_reads_coverage_json_in_the_working_directory_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_report(tmp_path, report({"src/leva/__init__.py": summary(1, 1)}))
    monkeypatch.chdir(tmp_path)

    assert main([]) == 0


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "cannot read"),
        ("{not json", "invalid JSON"),
        ("[]", "not a coverage JSON object"),
    ],
)
def test_main_exits_2_on_unusable_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str | None, message: str
) -> None:
    path = tmp_path / "coverage.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")

    assert main([str(path)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("coverage gate: ")
    assert message in captured.err
