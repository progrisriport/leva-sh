"""leva.sources.SystemInfo: parsing sw_vers output over fake binaries, errors, child env."""

from __future__ import annotations

import dataclasses
import platform
from pathlib import Path

import pytest

from leva.model import IngestError
from leva.sources import SystemInfo
from tests.support.fake_bin import fake_bin

VALID = "ProductName:\t\tmacOS\nProductVersion:\t\t26.2\nBuildVersion:\t\t25C56\n"
FAILED = "cannot read macOS version: sw_vers failed"
UNEXPECTED = "cannot read macOS version: unexpected sw_vers output"


def arm64() -> str:
    return "arm64"


def sw_vers_printing(tmp_path: Path, output: str, *, tail: str = "") -> str:
    """Write a fake sw_vers that prints `output` verbatim (then runs `tail`); return its path."""
    data = tmp_path / "output.txt"
    data.write_text(output, encoding="utf-8")
    return str(fake_bin(tmp_path / "bin", "sw_vers", f'/bin/cat "{data}"\n{tail}'))


def test_detect_parses_version_and_build(tmp_path: Path) -> None:
    info = SystemInfo.detect(sw_vers=sw_vers_printing(tmp_path, VALID), machine=arm64)
    assert info == SystemInfo("26.2", "25C56", "arm64")


def test_detect_default_machine_is_platform_machine(tmp_path: Path) -> None:
    info = SystemInfo.detect(sw_vers=sw_vers_printing(tmp_path, VALID))
    assert info.arch == platform.machine()


def test_detect_strips_values_and_first_key_wins(tmp_path: Path) -> None:
    output = (
        "no colon here\nProductVersion:   27.0  \nProductVersion: 99.9\nBuildVersion:\t26A1:x\n"
    )
    info = SystemInfo.detect(sw_vers=sw_vers_printing(tmp_path, output), machine=arm64)
    assert (info.macos_version, info.macos_build) == ("27.0", "26A1:x")


@pytest.mark.parametrize(
    "output",
    [
        "ProductVersion: 26.2\n",
        "ProductVersion: 26.2\nBuildVersion:   \n",
        "BuildVersion: 25C56\nProductVersion:\n",
        "",
    ],
)
def test_detect_rejects_missing_or_blank_values(tmp_path: Path, output: str) -> None:
    with pytest.raises(IngestError) as excinfo:
        SystemInfo.detect(sw_vers=sw_vers_printing(tmp_path, output), machine=arm64)
    assert excinfo.value.message == UNEXPECTED
    assert excinfo.value.hint is None


def test_detect_nonzero_exit_fails_even_with_valid_output(tmp_path: Path) -> None:
    sw_vers = sw_vers_printing(tmp_path, VALID, tail="exit 3")
    with pytest.raises(IngestError) as excinfo:
        SystemInfo.detect(sw_vers=sw_vers, machine=arm64)
    assert excinfo.value.message == FAILED
    assert excinfo.value.hint is None


def test_detect_missing_binary_chains_oserror(tmp_path: Path) -> None:
    with pytest.raises(IngestError) as excinfo:
        SystemInfo.detect(sw_vers=str(tmp_path / "missing"), machine=arm64)
    assert excinfo.value.message == FAILED
    assert isinstance(excinfo.value.__cause__, OSError)


def test_detect_timeout_fails(tmp_path: Path) -> None:
    sw_vers = str(fake_bin(tmp_path / "bin", "sw_vers", "exec /bin/sleep 10"))
    with pytest.raises(IngestError) as excinfo:
        SystemInfo.detect(sw_vers=sw_vers, timeout=0.2, machine=arm64)
    assert excinfo.value.message == FAILED


def test_detect_child_env_is_locale_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEVA_SENTINEL", "1")
    env_dump = tmp_path / "env.txt"
    data = tmp_path / "output.txt"
    data.write_text(VALID, encoding="utf-8")
    sw_vers = str(
        fake_bin(tmp_path / "bin", "sw_vers", f'/usr/bin/env > "{env_dump}"\n/bin/cat "{data}"')
    )
    SystemInfo.detect(sw_vers=sw_vers, machine=arm64)
    lines = env_dump.read_text(encoding="utf-8").splitlines()
    env = dict(line.split("=", 1) for line in lines)
    for shell_added in ("PWD", "SHLVL", "_", "OLDPWD"):
        env.pop(shell_added, None)
    assert env == {"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}


def test_detect_blank_machine_fails(tmp_path: Path) -> None:
    with pytest.raises(IngestError) as excinfo:
        SystemInfo.detect(sw_vers=sw_vers_printing(tmp_path, VALID), machine=lambda: "  ")
    assert excinfo.value.message == "cannot read machine architecture"
    assert excinfo.value.hint is None


@pytest.mark.parametrize("timeout", [0, -1.0])
def test_detect_rejects_non_positive_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        SystemInfo.detect(timeout=timeout)


def test_system_info_is_frozen_and_slotted() -> None:
    info = SystemInfo("26.2", "25C56", "arm64")
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.arch = "x86_64"  # type: ignore[misc]  # frozen dataclass assignment under test
    assert not hasattr(info, "__dict__")
