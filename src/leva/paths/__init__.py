"""Resolve data, config and log locations from an injected env and home, without I/O."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from leva.model import ConfigError

__all__ = ["LEVA_HOME_VAR", "LevaPaths"]

LEVA_HOME_VAR: Final = "LEVA_HOME"
_CONFIG_FILE_NAME: Final = "config.toml"
_INDEX_DB_NAME: Final = "index.db"
_LOG_DIR_NAME: Final = "logs"


@dataclass(frozen=True, slots=True)
class LevaPaths:
    """Where Leva keeps its data, configuration and logs.

    Pure value object: building or resolving it never touches the file system.

    Attributes:
        data_dir: Directory holding the index and the config file.
        config_file: Location of ``config.toml``.
        log_dir: Directory for the rotating log.
    """

    data_dir: Path
    config_file: Path
    log_dir: Path

    @property
    def index_db(self) -> Path:
        """Location of the SQLite index, inside ``data_dir``."""
        return self.data_dir / _INDEX_DB_NAME

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
        return cls(data_dir, data_dir / _CONFIG_FILE_NAME, home / "Library" / "Logs" / "leva")


def _under_leva_home(value: str) -> LevaPaths:
    """Build the paths for an explicit ``LEVA_HOME`` value, which must be absolute."""
    root = Path(value)
    if not root.is_absolute():
        raise ConfigError(
            f"{LEVA_HOME_VAR}: not an absolute path: {value!r}",
            hint=f"set {LEVA_HOME_VAR} to an absolute directory, or unset it",
        )
    return LevaPaths(root, root / _CONFIG_FILE_NAME, root / _LOG_DIR_NAME)
