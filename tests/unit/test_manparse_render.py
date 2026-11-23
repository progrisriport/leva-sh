"""Tests for `leva.manparse.MandocRenderer` against fake ``mandoc`` executables."""

from __future__ import annotations

from pathlib import Path

import pytest

from leva.manparse import MandocRenderer, ManRenderer
from leva.model import ManRenderError
from tests.support.fake_bin import fake_bin

PAGE_OVERSTRUCK = (
    "S\bSA\bAM\bMP\bPL\bLE\bE(1)    Manual    S\bSA\bAM\bMP\bPL\bLE\bE(1)\n"
    "\n"
    "N\bNA\bAM\bME\bE\n"
    "     _\bs_\bi_\bm_\bp_\bl_\be - a sample\n"
    "\n"
    "macOS 14                 January 1, 2026                macOS 14\n"
)
PAGE_PLAIN = (
    "SAMPLE(1)    Manual    SAMPLE(1)\n"
    "\n"
    "NAME\n"
    "     simple - a sample\n"
    "\n"
    "macOS 14                 January 1, 2026                macOS 14\n"
)


@pytest.fixture
def page(tmp_path: Path) -> Path:
    """A page path inside a ``man/man1`` tree."""
    path = tmp_path / "man" / "man1" / "x.1"
    path.parent.mkdir(parents=True)
    path.write_text(".TH X 1\n", encoding="utf-8")
    return path


def _printing(tmp_path: Path, text: str) -> Path:
    """A fake mandoc that prints `text`."""
    canned = tmp_path / "canned.txt"
    canned.write_text(text, encoding="utf-8")
    return fake_bin(tmp_path / "bin", "mandoc", f"exec /bin/cat {canned}")


def _recording(tmp_path: Path, command: str) -> Path:
    """A fake mandoc that runs `command`, then prints a minimal three-line page."""
    return fake_bin(tmp_path / "bin", "mandoc", f"{command}\n/bin/echo a; /bin/echo b; /bin/echo c")


def test_render_returns_stripped_text(tmp_path: Path, page: Path) -> None:
    binary = _printing(tmp_path, PAGE_OVERSTRUCK)
    assert MandocRenderer(binary=str(binary)).render(page) == PAGE_PLAIN


def test_render_passes_documented_argv(tmp_path: Path, page: Path) -> None:
    out = tmp_path / "argv.txt"
    binary = _recording(tmp_path, f'for a in "$@"; do /bin/echo "$a"; done > {out}')
    MandocRenderer(binary=str(binary)).render(page)
    assert out.read_text(encoding="utf-8").splitlines() == [
        "-T",
        "ascii",
        "-O",
        "width=80",
        str(page),
    ]


def test_render_uses_custom_width(tmp_path: Path, page: Path) -> None:
    out = tmp_path / "argv.txt"
    binary = _recording(tmp_path, f'for a in "$@"; do /bin/echo "$a"; done > {out}')
    MandocRenderer(binary=str(binary), width=100).render(page)
    assert "width=100" in out.read_text(encoding="utf-8").splitlines()


def test_render_runs_in_man_root(tmp_path: Path, page: Path) -> None:
    out = tmp_path / "cwd.txt"
    binary = _recording(tmp_path, f"/bin/pwd > {out}")
    MandocRenderer(binary=str(binary)).render(page)
    cwd = Path(out.read_text(encoding="utf-8").strip())
    assert cwd.resolve() == (tmp_path / "man").resolve()


def test_render_environment_is_explicit_and_minimal(
    tmp_path: Path, page: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEVA_SENTINEL", "1")
    out = tmp_path / "env.txt"
    binary = _recording(tmp_path, f"/usr/bin/env > {out}")
    MandocRenderer(binary=str(binary)).render(page)
    lines = set(out.read_text(encoding="utf-8").splitlines())
    assert {"LC_ALL=en_US.UTF-8", "LANG=en_US.UTF-8", "MANWIDTH=80", "TZ=UTC"} <= lines
    names = {line.partition("=")[0] for line in lines}
    assert names - {"PWD", "SHLVL", "_", "OLDPWD"} == {"LC_ALL", "LANG", "MANWIDTH", "TZ"}


def test_render_env_manwidth_follows_width(tmp_path: Path, page: Path) -> None:
    out = tmp_path / "env.txt"
    binary = _recording(tmp_path, f"/usr/bin/env > {out}")
    MandocRenderer(binary=str(binary), width=72).render(page)
    assert "MANWIDTH=72" in out.read_text(encoding="utf-8").splitlines()


def test_render_nonzero_exit_raises_failed(tmp_path: Path, page: Path) -> None:
    binary = fake_bin(tmp_path / "bin", "mandoc", "/bin/echo oops >&2\nexit 5")
    with pytest.raises(ManRenderError) as info:
        MandocRenderer(binary=str(binary)).render(page)
    assert info.value.message == f"mandoc failed: {page}"
    assert info.value.hint is None


def test_render_missing_binary_raises_failed_with_oserror_cause(tmp_path: Path, page: Path) -> None:
    with pytest.raises(ManRenderError) as info:
        MandocRenderer(binary=str(tmp_path / "no-such-mandoc")).render(page)
    assert info.value.message == f"mandoc failed: {page}"
    assert isinstance(info.value.__cause__, OSError)


def test_render_timeout_raises_timed_out(tmp_path: Path, page: Path) -> None:
    binary = fake_bin(tmp_path / "bin", "mandoc", "exec /bin/sleep 10")
    with pytest.raises(ManRenderError) as info:
        MandocRenderer(binary=str(binary), timeout=0.2).render(page)
    assert info.value.message == f"mandoc timed out: {page}"


@pytest.mark.parametrize(
    "output",
    ["", "\n\n", "HEADER(1)\n\n\nFOOTER\n", "HEADER(1)\nFOOTER\n"],
)
def test_render_output_without_body_raises_empty(tmp_path: Path, page: Path, output: str) -> None:
    binary = _printing(tmp_path, output)
    with pytest.raises(ManRenderError) as info:
        MandocRenderer(binary=str(binary)).render(page)
    assert info.value.message == f"empty man page: {page}"


def test_render_header_one_body_line_footer_is_returned(tmp_path: Path, page: Path) -> None:
    text = "HEADER(1)\n\n     body line\n\nFOOTER\n"
    binary = _printing(tmp_path, text)
    assert MandocRenderer(binary=str(binary)).render(page) == text


def test_render_does_not_normalise_whitespace(tmp_path: Path, page: Path) -> None:
    text = "  H(1)  \n\n     body  \n\n\n  F  \n"
    binary = _printing(tmp_path, text)
    assert MandocRenderer(binary=str(binary)).render(page) == text


@pytest.mark.parametrize("width", [0, -1])
def test_mandoc_renderer_rejects_non_positive_width(width: int) -> None:
    with pytest.raises(ValueError, match="width must be positive"):
        MandocRenderer(width=width)


@pytest.mark.parametrize("timeout", [0, -1.0])
def test_mandoc_renderer_rejects_non_positive_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout must be positive"):
        MandocRenderer(timeout=timeout)


def test_mandoc_renderer_satisfies_the_port() -> None:
    renderer: ManRenderer = MandocRenderer()
    assert renderer is not None
