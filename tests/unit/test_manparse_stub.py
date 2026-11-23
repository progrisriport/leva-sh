"""Tests for `leva.manparse.stub_target` and `leva.manparse.read_man_source`."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from leva.manparse import read_man_source, stub_target
from leva.model import ManRenderError


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (".so man1/x.1\n", "man1/x.1"),
        (".so\tman1/x.1\n", "man1/x.1"),
        (".so ../../a/b.1\n", "../../a/b.1"),
        ("  .so   man1/x.1   \n", "man1/x.1"),
        (".so man1/x.1", "man1/x.1"),
        (".so\n", None),
        (".so   \n", None),
        (".sox a\n", None),
        (".TH X 1\n.so y\n", None),
        ("plain text\n.so y\n", None),
        ("", None),
        ("\n\n  \n", None),
        (".\n", None),
        ('.\\" only a comment\n', None),
    ],
)
def test_stub_target_cases(source: str, expected: str | None) -> None:
    assert stub_target(source) == expected


@pytest.mark.parametrize("comment", ['.\\" note', "'\\\" note", ".\\# note"])
def test_stub_target_skips_comment_lines_before_so(comment: str) -> None:
    assert stub_target(f"{comment}\n.so man1/x.1\n") == "man1/x.1"


def test_stub_target_skips_blank_and_dot_lines_before_so() -> None:
    assert stub_target('\n.\n   \n.\\" c\n.so man1/x.1\n') == "man1/x.1"


def test_stub_target_returns_raw_argument_unresolved() -> None:
    assert stub_target(".so man1/../man1/x.1\n") == "man1/../man1/x.1"


def test_read_man_source_plain_file(tmp_path: Path) -> None:
    path = tmp_path / "x.1"
    path.write_text(".TH X 1\n", encoding="utf-8")
    assert read_man_source(path) == ".TH X 1\n"


def test_read_man_source_gz_file(tmp_path: Path) -> None:
    path = tmp_path / "x.1.gz"
    with gzip.open(path, "wb") as handle:
        handle.write(b".so man1/y.1\n")
    assert read_man_source(path) == ".so man1/y.1\n"


def test_read_man_source_invalid_utf8_is_replaced(tmp_path: Path) -> None:
    path = tmp_path / "x.1"
    path.write_bytes(b"caf\xe9\n")
    assert read_man_source(path) == "caf�\n"


def test_read_man_source_missing_file_raises_with_oserror_cause(tmp_path: Path) -> None:
    path = tmp_path / "missing.1"
    with pytest.raises(ManRenderError) as info:
        read_man_source(path)
    assert info.value.message == f"cannot read man page: {path}"
    assert isinstance(info.value.__cause__, OSError)


def test_read_man_source_non_gzip_bytes_in_gz_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "x.1.gz"
    path.write_bytes(b"this is not gzip data at all")
    with pytest.raises(ManRenderError, match="cannot read man page"):
        read_man_source(path)


def test_read_man_source_truncated_gzip_raises(tmp_path: Path) -> None:
    full = tmp_path / "full.1.gz"
    with gzip.open(full, "wb") as handle:
        handle.write(b".TH X 1\n" * 2000)
    data = full.read_bytes()
    truncated = tmp_path / "cut.1.gz"
    truncated.write_bytes(data[: len(data) // 2])
    with pytest.raises(ManRenderError, match="cannot read man page"):
        read_man_source(truncated)


def test_read_man_source_corrupt_deflate_stream_raises(tmp_path: Path) -> None:
    full = tmp_path / "full.1.gz"
    with gzip.open(full, "wb") as handle:
        handle.write(b".TH X 1\n" * 2000)
    path = tmp_path / "bad.1.gz"
    path.write_bytes(full.read_bytes()[:10] + b"\xff" * 64)
    with pytest.raises(ManRenderError, match="cannot read man page"):
        read_man_source(path)


def test_read_man_source_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(ManRenderError):
        read_man_source(tmp_path)
