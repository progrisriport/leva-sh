"""Run allowlisted help probes in a throw-away sandbox directory."""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final

from leva.model import IngestError

_BASE_ENV: Final = MappingProxyType(
    {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LC_ALL": "en_US.UTF-8",
        "LANG": "en_US.UTF-8",
        "LANGUAGE": "en",
        "NO_COLOR": "1",
        "TERM": "dumb",
        "HOMEBREW_NO_AUTO_UPDATE": "1",
        "HOMEBREW_NO_ANALYTICS": "1",
        "HOMEBREW_NO_ENV_HINTS": "1",
    }
)

_log = logging.getLogger("leva.sources")


def _read_capped(path: Path, max_bytes: int) -> str:
    """Return at most `max_bytes` bytes of `path`, decoded as UTF-8 with replacement."""
    with path.open("rb") as stream:
        return stream.read(max_bytes).decode("utf-8", errors="replace")


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    """Kill the child's whole process group and reap the child."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


class ProbeRunner:
    """Run help probes, and only those named in the allowlist.

    A probe runs without a shell, with a minimal fixed environment, a fresh temporary
    directory as cwd and ``HOME``, a timeout and a cap on the captured output (D-009).
    """

    def __init__(
        self,
        allowlist: Mapping[str, tuple[str, ...]],
        *,
        timeout: float = 5.0,
        max_bytes: int = 262_144,
    ) -> None:
        """Create a runner.

        Args:
            allowlist: Probe name to full argv; ``argv[0]`` is the absolute binary path.
            timeout: Seconds a probe may run before it is killed.
            max_bytes: Bytes kept from each of stdout and stderr.

        Pre: `timeout` and `max_bytes` are positive; every argv is non-empty and starts
            with an absolute path.
        Post: later changes to `allowlist` do not affect the runner.

        Raises:
            ValueError: A precondition is violated.
        """
        if timeout <= 0:
            raise ValueError(f"probe timeout must be positive, got {timeout}")
        if max_bytes <= 0:
            raise ValueError(f"probe max_bytes must be positive, got {max_bytes}")
        for name, argv in allowlist.items():
            if not argv or not Path(argv[0]).is_absolute():
                raise ValueError(f"probe {name!r}: argv[0] must be an absolute path, got {argv!r}")
        self._allowlist: Mapping[str, tuple[str, ...]] = MappingProxyType(dict(allowlist))
        self._timeout = timeout
        self._max_bytes = max_bytes

    def run(self, command: str) -> str:
        """Run the allowlisted probe `command` and return its help text.

        Pre: `command` is a key of the allowlist.
        Post: the text is stdout, or stderr when stdout is blank, cut at `max_bytes` per
            stream and not stripped; the exit status is ignored; the temporary directory
            is gone and no child of the probe is left running on timeout.

        Raises:
            IngestError: `command` is not allowed (nothing is spawned), the probe cannot
                be spawned or its temporary files cannot be used, times out or prints
                nothing but whitespace.
        """
        argv = self._allowlist.get(command)
        if argv is None:
            raise IngestError(f"probe not allowed: {command}")
        try:
            out, err = self._capture(command, argv)
        except OSError as exc:
            _log.debug("probe %s cannot use its temporary directory: %s", command, exc)
            raise IngestError(f"probe failed: {command}") from exc
        text = out if out.strip() else err
        if not text.strip():
            raise IngestError(f"probe output empty: {command}")
        return text

    def _capture(self, command: str, argv: tuple[str, ...]) -> tuple[str, str]:
        """Run `argv` in a throw-away directory and return the capped stdout and stderr."""
        with tempfile.TemporaryDirectory(prefix="leva-probe-", ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            self._execute(command, argv, home, root / "stdout", root / "stderr")
            out = _read_capped(root / "stdout", self._max_bytes)
            err = _read_capped(root / "stderr", self._max_bytes)
        return out, err

    def _execute(
        self, command: str, argv: tuple[str, ...], home: Path, stdout: Path, stderr: Path
    ) -> None:
        """Run `argv` in `home`, capturing the streams into the given files."""
        env = {**_BASE_ENV, "HOME": str(home)}
        with stdout.open("wb") as out_file, stderr.open("wb") as err_file:
            try:
                proc = subprocess.Popen(
                    list(argv),
                    stdin=subprocess.DEVNULL,
                    stdout=out_file,
                    stderr=err_file,
                    cwd=home,
                    env=env,
                    start_new_session=True,
                    shell=False,
                )
            except OSError as exc:
                _log.debug("probe %s cannot start: %s", command, exc)
                raise IngestError(f"probe failed: {command}") from exc
            try:
                status = proc.wait(timeout=self._timeout)
            except subprocess.TimeoutExpired as exc:
                _kill_group(proc)
                raise IngestError(f"probe timed out: {command}") from exc
        _log.debug("probe %s exited with status %d", command, status)
