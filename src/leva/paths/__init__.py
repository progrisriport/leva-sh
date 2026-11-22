"""Resolve data, config and log locations from an injected env and home, without I/O."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from leva.model import ConfigError

LEVA_HOME_VAR = "LEVA_HOME"
CONFIG_FILE_NAME = "config.toml"
INDEX_DB_NAME = "index.db"
LOG_DIR_NAME = "logs"

__all__ = ["LEVA_HOME_VAR", "LevaPaths"]


@dataclass(frozen=True, slots=True)
class LevaPaths:
    """Where Leva keeps its data, configuration and logs.

    Pure value object: building or resolving it never touches the file system.
    """

    data_dir: Path
    config_file: Path
    log_dir: Path

    @property
    def index_db(self) -> Path:
        """Location of the SQLite index, inside ``data_dir``."""
        return self.data_dir / INDEX_DB_NAME

    @classmethod
    def resolve(cls, env: Mapping[str, str], home: Path) -> LevaPaths:
        """Resolve the locations from an injected environment and home directory.

        With a non-empty ``LEVA_HOME`` in ``env`` every path lives under it; otherwise
        the macOS standard locations under ``home`` are used. Only ``LEVA_HOME`` is
        read from ``env``; no directory is created or inspected.

        Args:
            env: Environment mapping; only ``LEVA_HOME`` is consulted.
            home: Absolute home directory of the user.

        Returns:
            The resolved paths.

        Raises:
            ConfigError: ``LEVA_HOME`` is set to a relative path (``~`` is not expanded).
            ValueError: ``home`` is not absolute (programmer error).
        """
        if not home.is_absolute():
            raise ValueError(f"home must be an absolute path: {str(home)!r}")
        leva_home = env.get(LEVA_HOME_VAR, "")
        if leva_home:
            return _under_leva_home(leva_home)
        data_dir = home / "Library" / "Application Support" / "leva"
        return cls(data_dir, data_dir / CONFIG_FILE_NAME, home / "Library" / "Logs" / "leva")


def _under_leva_home(value: str) -> LevaPaths:
    """Build the paths for an explicit ``LEVA_HOME`` value, which must be absolute."""
    root = Path(value)
    if not root.is_absolute():
        raise ConfigError(
            f"{LEVA_HOME_VAR}: not an absolute path: {value!r}",
            hint=f"set {LEVA_HOME_VAR} to an absolute directory, or unset it",
        )
    return LevaPaths(root, root / CONFIG_FILE_NAME, root / LOG_DIR_NAME)
