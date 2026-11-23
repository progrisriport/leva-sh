"""Tests for `leva.manparse.MandocRenderer` against the real ``/usr/bin/mandoc``."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

import pytest

from leva.manparse import MandocRenderer, read_man_source, stub_target
from leva.model import ManRenderError

pytestmark = pytest.mark.skipif(not Path("/usr/bin/mandoc").exists(), reason="mandoc not installed")

SRC = Path(__file__).resolve().parent.parent / "fixtures" / "man" / "src"


@pytest.fixture
def man1(tmp_path: Path) -> Path:
    """Directory ``<tmp>/man/man1`` holding copies of every fixture page."""
    target = tmp_path / "man" / "man1"
    target.mkdir(parents=True)
    for source in SRC.glob("*.1"):
        shutil.copy(source, target / source.name)
    return target


def test_render_mdoc_page_has_name_heading_and_description(man1: Path) -> None:
    text = MandocRenderer().render(man1 / "leva-sample.1")
    lines = text.splitlines()
    assert "NAME" in lines
    assert "tidy a synthetic collection of widgets" in text
    assert "\x08" not in text


def test_render_mdoc_page_respects_width(man1: Path) -> None:
    text = MandocRenderer().render(man1 / "leva-sample.1")
    assert max(len(line) for line in text.splitlines()) <= 80


def test_render_man7_page(man1: Path) -> None:
    text = MandocRenderer().render(man1 / "leva-legacy.1")
    assert "NAME" in text.splitlines()
    assert "polish an invented gadget" in text


def test_render_stub_follows_so_from_man_root(man1: Path) -> None:
    stub = man1 / "leva-stub.1"
    assert stub_target(read_man_source(stub)) == "man1/leva-target.1"
    text = MandocRenderer().render(stub)
    assert "destination page of an include stub" in text


def test_render_empty_file_raises_empty(man1: Path) -> None:
    empty = man1 / "empty.1"
    empty.write_bytes(b"")
    with pytest.raises(ManRenderError, match="empty man page"):
        MandocRenderer().render(empty)


def test_render_binary_garbage_raises(man1: Path) -> None:
    garbage = man1 / "garbage.1"
    garbage.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(ManRenderError):
        MandocRenderer().render(garbage)


def test_render_missing_file_raises_failed(man1: Path) -> None:
    with pytest.raises(ManRenderError, match="mandoc failed"):
        MandocRenderer().render(man1 / "absent.1")


def test_render_gz_copy_matches_plain(man1: Path) -> None:
    plain = man1 / "leva-sample.1"
    packed = man1 / "leva-sample-gz.1.gz"
    with gzip.open(packed, "wb") as handle:
        handle.write(plain.read_bytes())
    renderer = MandocRenderer()
    assert renderer.render(packed) == renderer.render(plain)
