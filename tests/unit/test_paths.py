"""Path resolution: LEVA_HOME override, macOS defaults, validation, purity."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from leva.model import ConfigError
from leva.paths import LEVA_HOME_VAR, LevaPaths

HOME = Path("/Users/u")


def test_resolve_leva_home_relocates_every_path() -> None:
    paths = LevaPaths.resolve({"LEVA_HOME": "/data/lv"}, HOME)

    assert paths.data_dir == Path("/data/lv")
    assert paths.log_dir == Path("/data/lv/logs")
    assert paths.config_file == Path("/data/lv/config.toml")
    assert paths.index_db == Path("/data/lv/index.db")


def test_resolve_default_uses_macos_locations() -> None:
    paths = LevaPaths.resolve({}, HOME)

    data_dir = Path("/Users/u/Library/Application Support/leva")
    assert paths.data_dir == data_dir
    assert paths.log_dir == Path("/Users/u/Library/Logs/leva")
    assert paths.config_file == data_dir / "config.toml"
    assert paths.index_db == data_dir / "index.db"


def test_resolve_empty_leva_home_counts_as_unset() -> None:
    assert LevaPaths.resolve({"LEVA_HOME": ""}, HOME) == LevaPaths.resolve({}, HOME)


@pytest.mark.parametrize("value", ["rel/dir", ".", "~/leva"])
def test_resolve_relative_leva_home_raises_config_error(value: str) -> None:
    with pytest.raises(ConfigError) as info:
        LevaPaths.resolve({"LEVA_HOME": value}, HOME)

    assert info.value.message == f"LEVA_HOME: not an absolute path: {value!r}"
    assert info.value.hint == "set LEVA_HOME to an absolute directory, or unset it"


def test_resolve_trailing_slash_disappears() -> None:
    assert LevaPaths.resolve({"LEVA_HOME": "/data/lv/"}, HOME).data_dir == Path("/data/lv")


def test_resolve_ignores_home_in_env() -> None:
    paths = LevaPaths.resolve({"HOME": "/elsewhere"}, HOME)

    assert paths.data_dir.is_relative_to(HOME)
    assert paths.log_dir.is_relative_to(HOME)


def test_resolve_ignores_other_env_keys() -> None:
    env = {"XDG_DATA_HOME": "/xdg", "XDG_CONFIG_HOME": "/xdg/c", "LEVA_HOMES": "/x"}

    assert LevaPaths.resolve(env, HOME) == LevaPaths.resolve({}, HOME)


def test_resolve_relative_home_raises_value_error() -> None:
    with pytest.raises(ValueError, match="home must be an absolute path"):
        LevaPaths.resolve({}, Path("u"))


def test_resolve_relative_home_raises_even_with_leva_home() -> None:
    with pytest.raises(ValueError, match="home must be an absolute path"):
        LevaPaths.resolve({"LEVA_HOME": "/data/lv"}, Path("u"))


def test_resolve_does_no_io(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    missing = base / "nonexistent"

    LevaPaths.resolve({"LEVA_HOME": str(missing)}, missing)
    LevaPaths.resolve({}, missing)

    assert not missing.exists()
    assert list(base.iterdir()) == []


def test_resolve_does_not_read_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEVA_HOME", "/from/os")

    assert LevaPaths.resolve({}, HOME).data_dir == Path("/Users/u/Library/Application Support/leva")


def test_leva_paths_is_frozen_slotted_and_hashable() -> None:
    paths = LevaPaths(Path("/a"), Path("/a/c.toml"), Path("/a/l"))

    with pytest.raises(FrozenInstanceError):
        paths.data_dir = Path("/b")  # type: ignore[misc]  # assigning a frozen field on purpose
    assert not hasattr(paths, "__dict__")
    assert paths == LevaPaths(Path("/a"), Path("/a/c.toml"), Path("/a/l"))
    assert hash(paths) == hash(LevaPaths(Path("/a"), Path("/a/c.toml"), Path("/a/l")))
    assert paths.index_db == Path("/a/index.db")


def test_resolve_keeps_unicode_and_spaces_verbatim() -> None:
    paths = LevaPaths.resolve({"LEVA_HOME": "/data/My Leva é"}, HOME)

    assert paths.data_dir == Path("/data/My Leva é")
    assert paths.index_db == Path("/data/My Leva é/index.db")


def test_leva_home_var_names_the_variable() -> None:
    assert LEVA_HOME_VAR == "LEVA_HOME"
