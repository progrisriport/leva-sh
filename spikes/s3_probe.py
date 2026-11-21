"""Spike S-3 probe: which SQLite features does this Python interpreter have?

Usage:
    <interpreter> -I spikes/s3_probe.py <scratch_dir>

Prints one JSON object on stdout. Failed checks are data, so the exit code is 0; a bad
argument exits 2. The file is stdlib-only and must run on Python 3.9 (the system interpreter),
so it avoids 3.10+ syntax and stdlib APIs at runtime.
"""

from __future__ import annotations

import functools
import json
import platform
import sqlite3
import sys
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

TOKENIZE = "unicode61 remove_diacritics 2"
DDL_PLAIN = f"CREATE VIRTUAL TABLE t USING fts5(a, tokenize='{TOKENIZE}')"
DDL_CONTENTLESS = (
    "CREATE VIRTUAL TABLE t USING fts5(name, intents, summary, body, content='', "
    f"tokenize='{TOKENIZE}')"
)
DDL_TRIGRAM = "CREATE VIRTUAL TABLE t USING fts5(a, tokenize='trigram')"
DDL_CONTENTLESS_DELETE = (
    f"CREATE VIRTUAL TABLE t USING fts5(a, content='', contentless_delete=1, tokenize='{TOKENIZE}')"
)
INSERT_CONTENTLESS = "INSERT INTO t(rowid, name, intents, summary, body) VALUES (?, ?, ?, ?, ?)"
SELECT_MATCH = "SELECT rowid FROM t WHERE t MATCH ?"
SELECT_RANKED = "SELECT rowid FROM t WHERE t MATCH ? ORDER BY bm25(t, 10.0, 5.0, 2.0, 1.0)"
DDL_ENTRY = "CREATE TABLE entry(id INTEGER PRIMARY KEY, name TEXT, section TEXT, origin TEXT)"
INSERT_ENTRY = "INSERT INTO entry(name, section, origin) VALUES (?, ?, ?)"
RAW_QUERIES = ("git-commit", "NEAR(x", "NEAR", "AND", "name:x")
QUOTED_QUERIES = ('"git-commit"', '"near(x"', '"near"', '"and"', '"name:x"', '"x*"', '"a ""b"""')
RO_DIR = "Application Support #1 50%"
GARBAGE = b"this is not a sqlite database\n" * 200

Result = dict[str, object]
Check = Callable[[Path], Result]
CHECKS: dict[str, Check] = {}

REQUIRED = (
    "fts5",
    "contentless",
    "bm25_weights",
    "optimize",
    "quoting",
    "ifnull_unique",
    "ro_uri",
    "ro_missing",
    "ro_garbage",
)


def result(ok: bool, detail: str) -> Result:
    return {"ok": ok, "detail": detail}


def check(func: Check) -> Check:
    """Register `func` under its name minus the `check_` prefix; turn SQLite errors into data."""

    @functools.wraps(func)
    def wrapper(scratch: Path) -> Result:
        try:
            return func(scratch)
        except (sqlite3.Error, OSError) as exc:
            return result(False, f"{type(exc).__name__}: {exc}")

    CHECKS[func.__name__.replace("check_", "", 1)] = wrapper
    return wrapper


def memory() -> closing[sqlite3.Connection]:
    return closing(sqlite3.connect(":memory:"))


def rowids(con: sqlite3.Connection, sql: str, query: str) -> list[int]:
    return [row[0] for row in con.execute(sql, (query,))]


def error_of(con: sqlite3.Connection, sql: str, param: str) -> str | None:
    """Return `Type: message` if running `sql` raises, else None."""
    try:
        con.execute(sql, (param,)).fetchall()
    except sqlite3.Error as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def make_db(path: Path) -> None:
    """Create a one-row database at `path`, creating the directory too."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with closing(sqlite3.connect(path)) as con:
        con.execute("CREATE TABLE t(a)")
        con.execute("INSERT INTO t VALUES (1)")
        con.commit()


def ro_uri(path: Path) -> str:
    return path.as_uri() + "?mode=ro"


# Required checks


@check
def check_fts5(_scratch: Path) -> Result:
    with memory() as con:
        con.execute(DDL_PLAIN)
        con.execute("INSERT INTO t(rowid, a) VALUES (1, 'café résumé')")
        cafe, resume = rowids(con, SELECT_MATCH, "cafe"), rowids(con, SELECT_MATCH, "resume")
    return result(cafe == [1] and resume == [1], f"cafe -> {cafe}, resume -> {resume}")


@check
def check_contentless(_scratch: Path) -> Result:
    with memory() as con:
        con.execute(DDL_CONTENTLESS)
        con.execute(INSERT_CONTENTLESS, (7, "alpha", "", "beta", "gamma"))
        hits = rowids(con, SELECT_MATCH, "beta")
        stored = con.execute("SELECT name FROM t WHERE t MATCH 'beta'").fetchall()
    return result(hits == [7], f"MATCH -> rowids {hits}; SELECT name -> {stored}")


@check
def check_bm25_weights(_scratch: Path) -> Result:
    rows = [
        (1, "plain", "", "plain words", "zebra"),
        (2, "plain", "", "zebra", "plain words"),
        (3, "zebra", "", "plain words", "plain words"),
        (4, "alpha", "", "beta gamma", "delta epsilon"),
        (5, "beta", "", "gamma delta", "epsilon alpha"),
        (6, "gamma", "", "delta epsilon", "alpha beta"),
        (7, "delta", "", "epsilon alpha", "beta gamma"),
    ]
    with memory() as con:
        con.execute(DDL_CONTENTLESS)
        con.executemany(INSERT_CONTENTLESS, rows)
        order = rowids(con, SELECT_RANKED, "zebra")
    return result(order == [3, 2, 1], f"rowids by bm25: {order} (name row 3, summary 2, body 1)")


@check
def check_optimize(_scratch: Path) -> Result:
    with memory() as con:
        con.execute(DDL_CONTENTLESS)
        con.execute(INSERT_CONTENTLESS, (1, "alpha", "", "beta", "gamma"))
        con.execute("INSERT INTO t(t) VALUES('optimize')")
    return result(True, "INSERT INTO t(t) VALUES('optimize') accepted")


@check
def check_quoting(_scratch: Path) -> Result:
    with memory() as con:
        con.execute(DDL_CONTENTLESS)
        con.execute(INSERT_CONTENTLESS, (1, "git-commit", "", "near", "x"))
        raw = {q: error_of(con, SELECT_MATCH, q) for q in RAW_QUERIES}
        quoted = {q: error_of(con, SELECT_MATCH, q) for q in QUOTED_QUERIES}
    # A bare `NEAR` is an ordinary term and `name:x` a valid column filter: only the hyphen,
    # `NEAR(` and a bare `AND` must raise. Every quoted form, `:` `*` and `""` included, must not.
    ok = bool(raw["git-commit"] and raw["NEAR(x"] and raw["AND"]) and not any(quoted.values())
    detail = "; ".join(f"{q} -> {err or 'no error'}" for q, err in {**raw, **quoted}.items())
    return result(ok, detail)


@check
def check_ifnull_unique(_scratch: Path) -> Result:
    with memory() as con:
        con.execute(DDL_ENTRY)
        con.execute("CREATE UNIQUE INDEX k ON entry(name, IFNULL(section, ''), origin)")
        con.execute(INSERT_ENTRY, ("ls", None, "macos"))
        try:
            con.execute(INSERT_ENTRY, ("ls", None, "macos"))
        except sqlite3.IntegrityError as exc:
            duplicate = f"IntegrityError: {exc}"
        else:
            duplicate = None
        con.execute(INSERT_ENTRY, ("ls", "1", "macos"))
    return result(
        duplicate is not None, f"second NULL section -> {duplicate or 'accepted'}; section '1' ok"
    )


@check
def check_ro_uri(scratch: Path) -> Result:
    path = scratch / RO_DIR / "index.db"
    make_db(path)
    with closing(sqlite3.connect(ro_uri(path), uri=True)) as con:
        value = con.execute("SELECT a FROM t").fetchone()
        try:
            con.execute("INSERT INTO t VALUES (2)")
        except sqlite3.OperationalError as exc:
            return result(value == (1,), f"read -> {value}; write -> OperationalError: {exc}")
    return result(False, f"read -> {value}; write unexpectedly accepted")


@check
def check_ro_missing(scratch: Path) -> Result:
    path = scratch / RO_DIR / "absent.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        con = sqlite3.connect(ro_uri(path), uri=True)
    except sqlite3.OperationalError as exc:
        return result(True, f"at connect -> OperationalError: {exc}")
    with closing(con):
        try:
            con.execute("PRAGMA user_version").fetchone()
        except sqlite3.OperationalError as exc:
            return result(True, f"at first query -> OperationalError: {exc}")
    return result(False, "no error for a missing file")


@check
def check_ro_garbage(scratch: Path) -> Result:
    path = scratch / RO_DIR / "garbage.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(GARBAGE)
    with closing(sqlite3.connect(ro_uri(path), uri=True)) as con:
        try:
            con.execute("PRAGMA user_version").fetchone()
        except sqlite3.DatabaseError as exc:
            return result(True, f"connect ok; first query -> {type(exc).__name__}: {exc}")
    return result(False, "connect and first query both succeeded on garbage bytes")


# Informational checks


@check
def check_plain_unique_nulls(_scratch: Path) -> Result:
    with memory() as con:
        con.execute(
            "CREATE TABLE entry(id INTEGER PRIMARY KEY, name TEXT, section TEXT, origin TEXT, "
            "UNIQUE(name, section, origin))"
        )
        con.execute(INSERT_ENTRY, ("ls", None, "macos"))
        con.execute(INSERT_ENTRY, ("ls", None, "macos"))
        count = con.execute("SELECT count(*) FROM entry").fetchone()[0]
    return result(count == 2, f"plain UNIQUE accepted {count} rows with a NULL section")


@check
def check_rebuild_contentless(_scratch: Path) -> Result:
    with memory() as con:
        con.execute(DDL_CONTENTLESS)
        con.execute(INSERT_CONTENTLESS, (1, "alpha", "", "beta", "gamma"))
        error = error_of(con, "INSERT INTO t(t) VALUES(?)", "rebuild")
    return result(error is not None, f"'rebuild' -> {error or 'accepted'}")


@check
def check_naive_uri(scratch: Path) -> Result:
    path = scratch / "naive" / RO_DIR / "index.db"
    make_db(path)
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as con:
            value = con.execute("SELECT a FROM t").fetchone()
    except sqlite3.Error as exc:
        return result(True, f"naive f'file:{{path}}?mode=ro' fails -> {type(exc).__name__}: {exc}")
    return result(value != (1,), f"naive URI opened a database and read {value}")


def feature(ddl: str) -> Result:
    with memory() as con:
        con.execute(ddl)
    return result(True, "accepted")


@check
def check_trigram(_scratch: Path) -> Result:
    return feature(DDL_TRIGRAM)


@check
def check_contentless_delete(_scratch: Path) -> Result:
    return feature(DDL_CONTENTLESS_DELETE)


@check
def check_json1(_scratch: Path) -> Result:
    with memory() as con:
        value = con.execute("SELECT json_valid('{}')").fetchone()[0]
    return result(value == 1, f"json_valid('{{}}') -> {value}")


@check
def check_dbstat(_scratch: Path) -> Result:
    with memory() as con:
        count = con.execute("SELECT count(*) FROM dbstat").fetchone()[0]
    return result(True, f"count(*) over dbstat -> {count}")


def describe() -> Result:
    with memory() as con:
        options = [row[0] for row in con.execute("PRAGMA compile_options")]
    return {
        "python": platform.python_version(),
        "executable": sys.executable,
        "machine": platform.machine(),
        "sqlite": sqlite3.sqlite_version,
        "threadsafety": sqlite3.threadsafety,
        "compile_options": options,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not Path(argv[1]).is_dir():
        print("usage: s3_probe.py <scratch_dir>", file=sys.stderr)
        return 2
    scratch = Path(argv[1]).resolve()
    report = describe()
    report["checks"] = {name: func(scratch) for name, func in CHECKS.items()}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
