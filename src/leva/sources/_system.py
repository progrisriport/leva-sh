"""Detect the macOS version, build and CPU architecture."""

from __future__ import annotations

import logging
import platform
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from leva.model import IngestError

_SW_VERS_ENV: Final = MappingProxyType({"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"})
_SW_VERS_FAILED: Final = "cannot read macOS version: sw_vers failed"
_SW_VERS_UNEXPECTED: Final = "cannot read macOS version: unexpected sw_vers output"
_NO_ARCH: Final = "cannot read machine architecture"

_log = logging.getLogger("leva.sources")


def _run_sw_vers(sw_vers: str, timeout: float) -> str:
    """Run `sw_vers` and return its stdout; any failure raises `IngestError`."""
    try:
        result = subprocess.run(
            [sw_vers],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_SW_VERS_ENV,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _log.debug("sw_vers failed: %s", exc)
        raise IngestError(_SW_VERS_FAILED) from exc
    if result.returncode != 0:
        _log.debug("sw_vers exited with status %d", result.returncode)
        raise IngestError(_SW_VERS_FAILED)
    return result.stdout.decode("utf-8", errors="replace")


def _parse_fields(output: str) -> dict[str, str]:
    """Split ``key: value`` lines at the first colon; the first occurrence of a key wins."""
    fields: dict[str, str] = {}
    for line in output.splitlines():
        key, colon, value = line.partition(":")
        if colon:
            fields.setdefault(key.strip(), value.strip())
    return fields


@dataclass(frozen=True, slots=True)
class SystemInfo:
    """The system the index is built on.

    Attributes:
        macos_version: ``ProductVersion`` of ``sw_vers``, e.g. ``26.2``.
        macos_build: ``BuildVersion`` of ``sw_vers``, e.g. ``25C56``.
        arch: CPU architecture from ``platform.machine()``, e.g. ``arm64``.
    """

    macos_version: str
    macos_build: str
    arch: str

    @classmethod
    def detect(
        cls,
        *,
        sw_vers: str = "/usr/bin/sw_vers",
        timeout: float = 5.0,
        machine: Callable[[], str] = platform.machine,
    ) -> SystemInfo:
        """Read the system information; the only place that runs ``sw_vers``.

        Args:
            sw_vers: Path of the ``sw_vers`` executable.
            timeout: Seconds to wait for it to finish.
            machine: Source of the architecture name.

        Pre: `timeout` is positive.
        Post: the values are stripped and otherwise kept as given.

        Raises:
            ValueError: `timeout` is not positive.
            IngestError: ``sw_vers`` cannot run, times out, exits non-zero or lacks
                ``ProductVersion``/``BuildVersion``; the architecture is blank.
        """
        if timeout <= 0:
            raise ValueError(f"sw_vers timeout must be positive, got {timeout}")
        fields = _parse_fields(_run_sw_vers(sw_vers, timeout))
        version = fields.get("ProductVersion", "")
        build = fields.get("BuildVersion", "")
        if not version or not build:
            raise IngestError(_SW_VERS_UNEXPECTED)
        arch = machine().strip()
        if not arch:
            raise IngestError(_NO_ARCH)
        return cls(version, build, arch)
