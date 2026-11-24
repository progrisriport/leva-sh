"""leva.clipboard: PbcopyClipboard over fake binaries, FakeClipboard, shared preconditions."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from leva.clipboard import MAX_TEXT_BYTES, Clipboard, FakeClipboard, PbcopyClipboard
from leva.model import ClipboardError
from tests.support.fake_bin import fake_bin

UNAVAILABLE = "clipboard unavailable"


def capture_to_file(tmp_path: Path, tool: str) -> tuple[PbcopyClipboard, Path]:
    """Build a clipboard over a fake pbcopy that runs ``tool`` with its stdout in a file."""
    out = tmp_path / "captured"
    binary = fake_bin(tmp_path / "bin", "pbcopy", f'{tool} > "{out}"')
    return PbcopyClipboard(binary=str(binary), timeout=10.0), out


def failing(tmp_path: Path, script: str, *, timeout: float = 2.0) -> PbcopyClipboard:
    binary = fake_bin(tmp_path / "bin", "pbcopy", script)
    return PbcopyClipboard(binary=str(binary), timeout=timeout)


def missing(tmp_path: Path) -> PbcopyClipboard:
    return PbcopyClipboard(binary=str(tmp_path / "missing"))


# PbcopyClipboard: stdin and env ---------------------------------------------------------------


def test_copy_writes_text_to_stdin(tmp_path: Path) -> None:
    clip, out = capture_to_file(tmp_path, "/bin/cat")

    clip.copy("ls -la")

    assert out.read_bytes() == b"ls -la"


def test_copy_sends_unicode_as_utf8(tmp_path: Path) -> None:
    clip, out = capture_to_file(tmp_path, "/bin/cat")

    clip.copy("café ✓ 日本")

    assert out.read_bytes() == "café ✓ 日本".encode()


def test_copy_keeps_newlines_and_trailing_spaces_byte_identical(tmp_path: Path) -> None:
    clip, out = capture_to_file(tmp_path, "/bin/cat")
    text = "echo a \necho b  "

    clip.copy(text)

    assert out.read_bytes() == text.encode()


def test_copy_allows_whitespace_only_text(tmp_path: Path) -> None:
    clip, out = capture_to_file(tmp_path, "/bin/cat")

    clip.copy("  ")

    assert out.read_bytes() == b"  "


def test_copy_passes_only_a_utf8_locale_env(tmp_path: Path) -> None:
    clip, out = capture_to_file(tmp_path, "/usr/bin/env")

    clip.copy("x")

    lines = out.read_text(encoding="utf-8").splitlines()
    assert "LANG=en_US.UTF-8" in lines
    assert "LC_CTYPE=en_US.UTF-8" in lines
    assert not any(line.startswith(("LEVA_HOME=", "HOME=", "TZ=", "LC_ALL=")) for line in lines)


# PbcopyClipboard: failures --------------------------------------------------------------------


def test_nonzero_exit_raises_clipboard_unavailable(tmp_path: Path) -> None:
    clip = failing(tmp_path, "exit 1")

    with pytest.raises(ClipboardError) as info:
        clip.copy("x")

    assert info.value.message == UNAVAILABLE
    assert info.value.hint is None


def test_timeout_raises_clipboard_unavailable_from_timeout_expired(tmp_path: Path) -> None:
    clip = failing(tmp_path, "exec /bin/sleep 5", timeout=0.2)

    with pytest.raises(ClipboardError) as info:
        clip.copy("x")

    assert info.value.message == UNAVAILABLE
    assert isinstance(info.value.__cause__, subprocess.TimeoutExpired)


def test_missing_binary_raises_clipboard_unavailable_from_oserror(tmp_path: Path) -> None:
    with pytest.raises(ClipboardError) as info:
        missing(tmp_path).copy("x")

    assert info.value.message == UNAVAILABLE
    assert isinstance(info.value.__cause__, OSError)


def test_non_executable_file_raises_clipboard_unavailable(tmp_path: Path) -> None:
    plain = tmp_path / "pbcopy"
    plain.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    plain.chmod(0o644)

    with pytest.raises(ClipboardError) as info:
        PbcopyClipboard(binary=str(plain)).copy("x")

    assert info.value.message == UNAVAILABLE


def test_directory_binary_raises_clipboard_unavailable(tmp_path: Path) -> None:
    with pytest.raises(ClipboardError) as info:
        PbcopyClipboard(binary=str(tmp_path)).copy("x")

    assert info.value.message == UNAVAILABLE


# Preconditions --------------------------------------------------------------------------------


def test_empty_text_raises_value_error_before_spawning(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        missing(tmp_path).copy("")


def test_text_of_exactly_max_bytes_is_accepted(tmp_path: Path) -> None:
    clip, out = capture_to_file(tmp_path, "/bin/cat")

    clip.copy("a" * MAX_TEXT_BYTES)

    assert len(out.read_bytes()) == 65_536


def test_text_over_max_bytes_raises_value_error_before_spawning(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exceeds 64 KiB"):
        missing(tmp_path).copy("a" * (MAX_TEXT_BYTES + 1))


def test_limit_counts_utf8_bytes_not_characters(tmp_path: Path) -> None:
    text = "é" * 32_769  # 32 769 characters, 65 538 bytes

    with pytest.raises(ValueError, match="exceeds 64 KiB"):
        missing(tmp_path).copy(text)


@pytest.mark.parametrize("timeout", [0, -1, -0.5])
def test_non_positive_timeout_raises_value_error(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        PbcopyClipboard(timeout=timeout)


def test_default_construction_succeeds() -> None:
    assert PbcopyClipboard() is not None


# FakeClipboard --------------------------------------------------------------------------------


def test_fake_starts_empty() -> None:
    fake = FakeClipboard()

    assert fake.last is None
    assert fake.history == ()


def test_fake_records_copies_oldest_first() -> None:
    fake = FakeClipboard()

    fake.copy("a")
    fake.copy("b")

    assert fake.last == "b"
    assert fake.history == ("a", "b")
    assert isinstance(fake.history, tuple)


def test_fake_history_is_a_snapshot() -> None:
    fake = FakeClipboard()
    fake.copy("a")
    before = fake.history

    fake.copy("b")

    assert before == ("a",)


def test_fake_fail_raises_and_records_nothing() -> None:
    fake = FakeClipboard()
    fake.copy("a")
    fake.fail = True

    with pytest.raises(ClipboardError) as info:
        fake.copy("b")

    assert info.value.message == UNAVAILABLE
    assert info.value.hint is None
    assert fake.last == "a"
    assert fake.history == ("a",)


def test_fake_constructed_failing_recovers_when_flag_is_cleared() -> None:
    fake = FakeClipboard(fail=True)
    with pytest.raises(ClipboardError):
        fake.copy("a")

    fake.fail = False
    fake.copy("a")

    assert fake.history == ("a",)


def test_fake_enforces_the_same_preconditions() -> None:
    fake = FakeClipboard()

    with pytest.raises(ValueError, match="must not be empty"):
        fake.copy("")
    with pytest.raises(ValueError, match="exceeds 64 KiB"):
        fake.copy("é" * 32_769)

    assert fake.history == ()


def test_fake_checks_preconditions_before_the_fail_flag() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        FakeClipboard(fail=True).copy("")


# Port -----------------------------------------------------------------------------------------


def use(clip: Clipboard, text: str) -> None:
    clip.copy(text)


def test_both_classes_satisfy_the_clipboard_port(tmp_path: Path) -> None:
    fake = FakeClipboard()
    pbcopy, out = capture_to_file(tmp_path, "/bin/cat")

    use(fake, "one")
    use(pbcopy, "two")

    assert fake.last == "one"
    assert out.read_bytes() == b"two"
