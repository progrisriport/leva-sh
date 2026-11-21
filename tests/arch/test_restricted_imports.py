"""Stdlib and private-import restrictions on ``src/leva`` (D-002), and the AST checker itself."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.arch.rules import (
    RULES,
    PrivateImport,
    Restriction,
    SourceModule,
    Violation,
    find_violations,
    source_modules,
)

SRC = Path(__file__).resolve().parents[2] / "src"

D002_PACKAGES = (
    "model",
    "paths",
    "placeholders",
    "clipboard",
    "config",
    "sources",
    "manparse",
    "subcmd",
    "content",
    "store",
    "repo",
    "search",
    "library",
    "ingest",
    "tui",
    "cli",
    "verify",
)


def plant(root: Path, files: dict[str, str]) -> Path:
    """Write a synthetic source tree under ``root`` (``leva/__init__.py`` is always present)."""
    for relative, source in {"leva/__init__.py": "", **files}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        for parent in path.relative_to(root).parents:
            init = root / parent / "__init__.py"
            if parent != Path() and not init.exists():
                init.write_text("", encoding="utf-8")
        path.write_text(source, encoding="utf-8")
    return root


def rules_hit(root: Path) -> list[tuple[str, int, str]]:
    return [(v.path, v.line, v.rule) for v in find_violations(root, RULES)]


# the real tree --------------------------------------------------------------------------------


def test_src_has_no_restricted_uses() -> None:
    assert find_violations(SRC, RULES) == []


def test_scan_covers_every_d002_package() -> None:
    names = {module.name for module in source_modules(SRC)}

    assert {"leva", *(f"leva.{package}" for package in D002_PACKAGES)} <= names


# module discovery -----------------------------------------------------------------------------


def test_source_modules_names_packages_modules_and_main_in_sorted_order(tmp_path: Path) -> None:
    plant(
        tmp_path,
        {"leva/verify/__main__.py": "", "leva/store/_writer.py": "", "leva/store/notes.txt": ""},
    )

    modules = source_modules(tmp_path)

    assert modules == [
        SourceModule("leva", "leva/__init__.py", is_package=True),
        SourceModule("leva.store", "leva/store/__init__.py", is_package=True),
        SourceModule("leva.store._writer", "leva/store/_writer.py", is_package=False),
        SourceModule("leva.verify", "leva/verify/__init__.py", is_package=True),
        SourceModule("leva.verify.__main__", "leva/verify/__main__.py", is_package=False),
    ]


def test_source_module_package_is_itself_for_packages_and_parent_for_modules() -> None:
    assert SourceModule("leva.store", "leva/store/__init__.py", is_package=True).package == (
        "leva.store"
    )
    assert SourceModule("leva.store._w", "leva/store/_w.py", is_package=False).package == (
        "leva.store"
    )


# planted violations ---------------------------------------------------------------------------

PLANTED = [
    pytest.param(
        "leva/tui/__init__.py", "import subprocess\n", "subprocess", id="import-subprocess"
    ),
    pytest.param("leva/tui/_a.py", "import subprocess as sp\n", "subprocess", id="import-as"),
    pytest.param(
        "leva/search/_a.py", "from subprocess import run\n", "subprocess", id="from-import"
    ),
    pytest.param(
        "leva/tui/_a.py",
        "import asyncio\nasyncio.create_subprocess_exec\n",
        "subprocess",
        id="asyncio-attribute",
    ),
    pytest.param(
        "leva/tui/_a.py", "from asyncio import subprocess\n", "subprocess", id="asyncio-submodule"
    ),
    pytest.param("leva/search/_a.py", "import sqlite3\n", "sqlite3", id="sqlite3"),
    pytest.param("leva/storex/_a.py", "import sqlite3\n", "sqlite3", id="allowed-prefix-trap"),
    pytest.param("leva/config/_a.py", "import os\nos.environ['X']\n", "environment", id="environ"),
    pytest.param("leva/config/_a.py", "import os\nos.getenv('X')\n", "environment", id="getenv"),
    pytest.param(
        "leva/paths/_a.py", "import os as o\no.putenv('X', '1')\n", "environment", id="alias"
    ),
    pytest.param(
        "leva/paths/_a.py", "import os.path\nos.environ.get('X')\n", "environment", id="os-path"
    ),
    pytest.param("leva/paths/_a.py", "from os import environ\n", "environment", id="from-os"),
    pytest.param(
        "leva/paths/_a.py",
        "def f():\n    import os\n    return os.getenv('X')\n",
        "environment",
        id="nested",
    ),
    pytest.param("leva/cli/__init__.py", "import socket\n", "network", id="socket-even-in-cli"),
    pytest.param(
        "leva/sources/_a.py", "from urllib.request import urlopen\n", "network", id="urllib"
    ),
    pytest.param("leva/sources/_a.py", "import http.client\n", "network", id="http"),
    pytest.param("leva/sources/_a.py", "import ssl\n", "network", id="ssl"),
    pytest.param("leva/sources/_a.py", "import ftplib\n", "network", id="ftplib"),
    pytest.param("leva/sources/_a.py", "import smtplib\n", "network", id="smtplib"),
    pytest.param("leva/tui/_a.py", "print('x')\n", "print", id="print"),
    pytest.param(
        "leva/tui/_a.py", "import builtins\nbuiltins.print('x')\n", "print", id="builtins"
    ),
    pytest.param("leva/tui/_a.py", "show = print\n", "print", id="print-reference"),
    pytest.param("leva/verify/_runner.py", "print('x')\n", "print", id="print-outside-main"),
    pytest.param(
        "leva/repo/_a.py", "from leva.store._schema import X\n", "private-import", id="from"
    ),
    pytest.param(
        "leva/repo/_a.py", "from leva.store import _schema\n", "private-import", id="name"
    ),
    pytest.param("leva/repo/_a.py", "import leva.store._schema\n", "private-import", id="dotted"),
    pytest.param(
        "leva/repo/_a.py", "from ..store._schema import X\n", "private-import", id="relative"
    ),
    pytest.param(
        "leva/repo/__init__.py",
        "from ..store import _schema\n",
        "private-import",
        id="relative-pkg",
    ),
    pytest.param(
        "leva/repo/_a.py", "import leva.store\nleva.store._schema.X\n", "private-import", id="attr"
    ),
    pytest.param(
        "leva/repo/_a.py",
        "from leva.store import Store\nStore._cache\n",
        "private-import",
        id="private-attribute",
    ),
    pytest.param(
        "leva/store/_a.py",
        "from leva.storex._x import y\n",
        "private-import",
        id="owner-prefix-trap",
    ),
]


@pytest.mark.parametrize(("relative", "source", "rule"), PLANTED)
def test_planted_violation_is_reported(
    tmp_path: Path, relative: str, source: str, rule: str
) -> None:
    plant(tmp_path, {relative: source})

    assert [(path, name) for path, _, name in rules_hit(tmp_path)] == [(relative, rule)]


ALLOWED = [
    pytest.param("leva/clipboard/_pbcopy.py", "import subprocess\n", id="subprocess-clipboard"),
    pytest.param("leva/sources/_probe.py", "from subprocess import run\n", id="subprocess-sources"),
    pytest.param("leva/manparse/__init__.py", "import subprocess\n", id="subprocess-manparse"),
    pytest.param("leva/verify/_sandbox.py", "import subprocess\n", id="subprocess-verify"),
    pytest.param("leva/store/_writer.py", "import sqlite3\n", id="sqlite3-store"),
    pytest.param("leva/repo/_query.py", "import sqlite3\n", id="sqlite3-repo"),
    pytest.param("leva/cli/_main.py", "import sqlite3\n", id="sqlite3-cli"),
    pytest.param("leva/cli/_main.py", "import os\nos.environ.get('X')\n", id="environ-cli"),
    pytest.param("leva/cli/_main.py", "print('x')\n", id="print-cli"),
    pytest.param("leva/verify/__main__.py", "print('x')\n", id="print-verify-main"),
    pytest.param("leva/tui/_a.py", "import os\nos.path.join('a', 'b')\nos.sep\n", id="os-path"),
    pytest.param("leva/tui/_a.py", "import asyncio\nasyncio.sleep\n", id="asyncio"),
    pytest.param("leva/tui/_a.py", "import subprocessing\nimport sslx\n", id="target-prefix-trap"),
    pytest.param("leva/tui/_a.py", "from rich import print\nprint('x')\n", id="print-rebound"),
    pytest.param("leva/tui/_a.py", "obj.print('x')\nlen([])\n", id="print-method"),
    pytest.param("leva/store/__init__.py", "from ._schema import X\n", id="private-relative-own"),
    pytest.param("leva/store/_w.py", "from leva.store._schema import X\n", id="private-own"),
    pytest.param("leva/store/_w.py", "from . import _schema\n", id="private-own-sibling"),
    pytest.param("leva/tui/_a.py", "from leva.store import Store\n", id="public-root"),
    pytest.param("leva/tui/_a.py", "from leva import __version__\n", id="dunder"),
    pytest.param("leva/tui/_a.py", "from leva.verify import __main__\n", id="dunder-module"),
    pytest.param("leva/tui/_a.py", "from __future__ import annotations\n", id="future"),
]


@pytest.mark.parametrize(("relative", "source"), ALLOWED)
def test_allowed_use_is_not_reported(tmp_path: Path, relative: str, source: str) -> None:
    plant(tmp_path, {relative: source})

    assert rules_hit(tmp_path) == []


# reporting ------------------------------------------------------------------------------------


def test_violations_are_sorted_deduplicated_per_line_and_readable(tmp_path: Path) -> None:
    plant(
        tmp_path,
        {
            "leva/tui/_b.py": "import os\n\nx = os.environ['A'] + os.environ['B']\n",
            "leva/tui/_a.py": "from subprocess import PIPE, run\nprint(run)\n",
        },
    )

    violations = find_violations(tmp_path, RULES)

    assert [str(v) for v in violations] == [
        "leva/tui/_a.py:1: subprocess: subprocess.PIPE",
        "leva/tui/_a.py:2: print: builtins.print",
        "leva/tui/_b.py:3: environment: os.environ",
    ]


def test_find_violations_applies_only_the_given_rules(tmp_path: Path) -> None:
    plant(tmp_path, {"leva/tui/_a.py": "import sqlite3\nimport subprocess\n"})
    only_sqlite = [Restriction("sqlite3", frozenset({"sqlite3"}), frozenset())]

    assert find_violations(tmp_path, only_sqlite) == [
        Violation("leva/tui/_a.py", 1, "sqlite3", "sqlite3")
    ]


def test_private_import_rule_honours_its_root_package(tmp_path: Path) -> None:
    plant(tmp_path, {"other/__init__.py": "from leva.store import _schema\n"})

    assert find_violations(tmp_path, [PrivateImport(root="other")]) == []
    assert find_violations(tmp_path, [PrivateImport(root="leva")]) == [
        Violation("other/__init__.py", 1, "private-import", "leva.store._schema")
    ]


def test_relative_import_beyond_the_top_level_package_is_an_error(tmp_path: Path) -> None:
    plant(tmp_path, {"leva/tui/_a.py": "from ... import x\n"})

    with pytest.raises(ValueError, match="beyond the top-level package"):
        find_violations(tmp_path, RULES)
