"""Load and validate ``config.toml`` and provide its digest."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from leva.model import ConfigError

__all__ = ["DEFAULT_SECTIONS", "LevaConfig", "load_config"]

DEFAULT_SECTIONS: Final = ("1", "8")

_KEYS: Final = ("extra_bin_dirs", "extra_man_paths", "sections")
_SECTION_RE: Final = re.compile(r"[a-z0-9]+")
_TOML_LINE_RE: Final = re.compile(r"at line (\d+)")


@dataclass(frozen=True, slots=True)
class LevaConfig:
    """Validated user configuration.

    Attributes:
        sections: Man sections to index; each names a ``man<section>/`` directory.
        extra_man_paths: Additional absolute man directories, in search order.
        extra_bin_dirs: Additional absolute executable directories, in search order.

    Raises:
        ValueError: ``sections`` is empty, has a duplicate or a name not matching
            ``[a-z0-9]+``, or an extra path is not absolute.
    """

    sections: tuple[str, ...] = DEFAULT_SECTIONS
    extra_man_paths: tuple[Path, ...] = ()
    extra_bin_dirs: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if not self.sections:
            raise ValueError("sections must not be empty")
        if len(set(self.sections)) != len(self.sections):
            raise ValueError(f"duplicate section in {self.sections!r}")
        for section in self.sections:
            if not _SECTION_RE.fullmatch(section):
                raise ValueError(f"invalid section: {section!r}")
        for path in (*self.extra_man_paths, *self.extra_bin_dirs):
            if not path.is_absolute():
                raise ValueError(f"not an absolute path: {path}")

    def digest(self) -> str:
        """Return the sha256 of the canonical JSON form as 64 lowercase hex chars.

        List order is part of the digest: it is the search order.
        """
        canonical = json.dumps(
            {
                "sections": list(self.sections),
                "extra_man_paths": [str(p) for p in self.extra_man_paths],
                "extra_bin_dirs": [str(p) for p in self.extra_bin_dirs],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_config(path: Path, home: Path) -> LevaConfig:
    """Load and validate the config file at ``path``.

    Args:
        path: Location of ``config.toml``.
        home: Absolute home directory used to expand a leading ``~``.

    Returns:
        The validated config; the defaults when ``path`` does not exist.

    Raises:
        ValueError: ``home`` is not absolute.
        ConfigError: The file is unreadable, not UTF-8, not valid TOML, or holds an
            unknown key or an invalid value.
    """
    if not home.is_absolute():
        raise ValueError(f"home must be absolute: {home}")
    name = path.name
    hint = f"edit {path} or delete it to use the defaults"
    text = _read_text(path, name, hint)
    if text is None:
        return LevaConfig()
    data = _parse_toml(text, name, hint)
    _check_keys(data, name, hint)
    return LevaConfig(
        sections=_sections(data.get("sections", list(DEFAULT_SECTIONS)), name, hint),
        extra_man_paths=_path_list(
            data.get("extra_man_paths", []), "extra_man_paths", home, name, hint
        ),
        extra_bin_dirs=_path_list(
            data.get("extra_bin_dirs", []), "extra_bin_dirs", home, name, hint
        ),
    )


def _read_text(path: Path, name: str, hint: str) -> str | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigError(f"{name}: cannot read file", hint) from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{name}: not valid UTF-8", hint) from exc


def _parse_toml(text: str, name: str, hint: str) -> dict[str, object]:
    try:
        return dict(tomllib.loads(text))
    except tomllib.TOMLDecodeError as exc:
        found = _TOML_LINE_RE.search(str(exc))
        line = int(found.group(1)) if found else max(1, len(text.splitlines()))
        raise ConfigError(f"{name}: invalid TOML at line {line}", hint) from exc


def _check_keys(data: dict[str, object], name: str, hint: str) -> None:
    unknown = sorted(set(data) - set(_KEYS))
    if unknown:
        raise ConfigError(f"{name}:{unknown[0]}: unknown key", hint)


def _sections(value: object, name: str, hint: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{name}:sections: expected a list of strings", hint)
    if not value:
        raise ConfigError(f"{name}:sections: must not be empty", hint)
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError(f"{name}:sections[{index}]: expected a string", hint)
        if not _SECTION_RE.fullmatch(item):
            raise ConfigError(f"{name}:sections[{index}]: invalid section: {item!r}", hint)
        if item in seen:
            raise ConfigError(f"{name}:sections[{index}]: duplicate section: {item!r}", hint)
        seen.add(item)
    return tuple(value)


def _path_list(value: object, key: str, home: Path, name: str, hint: str) -> tuple[Path, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{name}:{key}: expected a list of strings", hint)
    paths: list[Path] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError(f"{name}:{key}[{index}]: expected a string", hint)
        path = _expand(item, home)
        if not path.is_absolute():
            raise ConfigError(f"{name}:{key}[{index}]: not an absolute path: {item!r}", hint)
        paths.append(path)
    return tuple(paths)


def _expand(raw: str, home: Path) -> Path:
    if raw == "~":
        return home
    if raw.startswith("~/"):
        # Strip extra slashes: ``home / "/x"`` would discard ``home``.
        return home / raw[2:].lstrip("/")
    return Path(raw)
