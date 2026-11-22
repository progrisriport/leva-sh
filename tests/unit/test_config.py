"""Config loading: defaults, strict validation, path expansion, digest."""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import leva.config as config
from leva.config import DEFAULT_SECTIONS, LevaConfig, load_config
from leva.model import ConfigError

DEFAULT_DIGEST = hashlib.sha256(
    b'{"extra_bin_dirs":[],"extra_man_paths":[],"sections":["1","8"]}'
).hexdigest()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


def write(tmp_path: Path, text: str, name: str = "config.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def load_error(tmp_path: Path, home: Path, text: str, name: str = "config.toml") -> ConfigError:
    with pytest.raises(ConfigError) as excinfo:
        load_config(write(tmp_path, text, name), home)
    return excinfo.value


def test_missing_file_gives_defaults(tmp_path: Path, home: Path) -> None:
    cfg = load_config(tmp_path / "config.toml", home)
    assert cfg == LevaConfig()
    assert cfg.sections == ("1", "8")
    assert cfg.extra_man_paths == ()
    assert cfg.extra_bin_dirs == ()
    assert DEFAULT_SECTIONS == ("1", "8")


@pytest.mark.parametrize("text", ["", "# only a comment\n\n  # another\n"])
def test_empty_or_comment_only_file_gives_defaults(tmp_path: Path, home: Path, text: str) -> None:
    assert load_config(write(tmp_path, text), home) == LevaConfig()


def test_full_valid_file_expands_home(tmp_path: Path, home: Path) -> None:
    path = write(
        tmp_path,
        'sections = ["1", "8", "5"]\n'
        'extra_man_paths = ["/opt/man", "~/man"]\n'
        'extra_bin_dirs = ["~"]\n',
    )
    cfg = load_config(path, home)
    assert cfg.sections == ("1", "8", "5")
    assert cfg.extra_man_paths == (Path("/opt/man"), home / "man")
    assert cfg.extra_bin_dirs == (home,)
    assert all(isinstance(p, Path) for p in cfg.extra_man_paths + cfg.extra_bin_dirs)


def test_partial_file_keeps_other_defaults(tmp_path: Path, home: Path) -> None:
    cfg = load_config(write(tmp_path, 'extra_bin_dirs = ["/opt/bin"]\n'), home)
    assert cfg.sections == DEFAULT_SECTIONS
    assert cfg.extra_man_paths == ()
    assert cfg.extra_bin_dirs == (Path("/opt/bin"),)


def test_invalid_toml_reports_line(tmp_path: Path, home: Path) -> None:
    err = load_error(tmp_path, home, 'sections = ["1"]\n\nthis is = = broken\n')
    assert err.message == "config.toml: invalid TOML at line 3"
    assert err.hint is not None
    assert isinstance(err.__cause__, tomllib.TOMLDecodeError)


def test_invalid_toml_at_end_of_document_reports_last_line(tmp_path: Path, home: Path) -> None:
    err = load_error(tmp_path, home, 'sections = ["1",\n\n\n')
    assert err.message == "config.toml: invalid TOML at line 3"


def test_invalid_toml_at_end_of_empty_ish_document_reports_line_one(
    tmp_path: Path, home: Path
) -> None:
    err = load_error(tmp_path, home, "sections = ")
    assert err.message == "config.toml: invalid TOML at line 1"


def test_invalid_utf8_is_rejected(tmp_path: Path, home: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_bytes(b'sections = ["\xff"]\n')
    with pytest.raises(ConfigError) as excinfo:
        load_config(path, home)
    assert excinfo.value.message == "config.toml: not valid UTF-8"
    assert excinfo.value.hint is not None
    assert isinstance(excinfo.value.__cause__, UnicodeDecodeError)


def test_directory_instead_of_file_is_unreadable(tmp_path: Path, home: Path) -> None:
    path = tmp_path / "config.toml"
    path.mkdir()
    with pytest.raises(ConfigError) as excinfo:
        load_config(path, home)
    assert excinfo.value.message == "config.toml: cannot read file"
    assert excinfo.value.hint == f"edit {path} or delete it to use the defaults"
    assert isinstance(excinfo.value.__cause__, OSError)


def test_unknown_key_is_rejected(tmp_path: Path, home: Path) -> None:
    err = load_error(tmp_path, home, 'colour = "red"\n')
    assert err.message == "config.toml:colour: unknown key"
    assert err.hint is not None


def test_first_unknown_key_in_sorted_order_is_reported(tmp_path: Path, home: Path) -> None:
    err = load_error(tmp_path, home, "zeta = 1\nalpha = 2\n")
    assert err.message == "config.toml:alpha: unknown key"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('sections = "1"', "config.toml:sections: expected a list of strings"),
        ("sections = [1, 8]", "config.toml:sections[0]: expected a string"),
        ("[sections]\na = 1", "config.toml:sections: expected a list of strings"),
        ('extra_man_paths = "/x"', "config.toml:extra_man_paths: expected a list of strings"),
        ("extra_bin_dirs = [true]", "config.toml:extra_bin_dirs[0]: expected a string"),
        ('extra_bin_dirs = ["/a", 3]', "config.toml:extra_bin_dirs[1]: expected a string"),
    ],
)
def test_wrong_types_are_rejected(tmp_path: Path, home: Path, text: str, message: str) -> None:
    assert load_error(tmp_path, home, text).message == message


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("sections = []", "config.toml:sections: must not be empty"),
        ('sections = ["1", "Man"]', "config.toml:sections[1]: invalid section: 'Man'"),
        ('sections = ["1 "]', "config.toml:sections[0]: invalid section: '1 '"),
        ('sections = [""]', "config.toml:sections[0]: invalid section: ''"),
        ('sections = ["../x"]', "config.toml:sections[0]: invalid section: '../x'"),
        ('sections = ["1", "8", "1"]', "config.toml:sections[2]: duplicate section: '1'"),
    ],
)
def test_invalid_sections_are_rejected(tmp_path: Path, home: Path, text: str, message: str) -> None:
    assert load_error(tmp_path, home, text).message == message


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            'extra_man_paths = ["relative/dir"]',
            "config.toml:extra_man_paths[0]: not an absolute path: 'relative/dir'",
        ),
        (
            'extra_bin_dirs = ["/ok", ""]',
            "config.toml:extra_bin_dirs[1]: not an absolute path: ''",
        ),
        (
            'extra_man_paths = ["~user/x"]',
            "config.toml:extra_man_paths[0]: not an absolute path: '~user/x'",
        ),
    ],
)
def test_non_absolute_paths_are_rejected(
    tmp_path: Path, home: Path, text: str, message: str
) -> None:
    assert load_error(tmp_path, home, text).message == message


def test_path_is_normalised(tmp_path: Path, home: Path) -> None:
    cfg = load_config(write(tmp_path, 'extra_man_paths = ["/a/b/", "/a//b"]'), home)
    assert cfg.extra_man_paths == (Path("/a/b"), Path("/a/b"))


def test_tilde_with_extra_slashes_stays_under_home(tmp_path: Path, home: Path) -> None:
    cfg = load_config(write(tmp_path, 'extra_man_paths = ["~//man", "~/"]'), home)
    assert cfg.extra_man_paths == (home / "man", home)


def test_duplicate_paths_are_kept(tmp_path: Path, home: Path) -> None:
    cfg = load_config(write(tmp_path, 'extra_bin_dirs = ["/a", "/a"]'), home)
    assert cfg.extra_bin_dirs == (Path("/a"), Path("/a"))


def test_message_prefix_follows_file_name(tmp_path: Path, home: Path) -> None:
    err = load_error(tmp_path, home, 'colour = "red"', name="leva.toml")
    assert err.message == "leva.toml:colour: unknown key"


def test_relative_home_is_a_programmer_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="home"):
        load_config(tmp_path / "config.toml", Path("rel"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sections": ()},
        {"sections": ("1", "1")},
        {"sections": ("X",)},
        {"sections": ("",)},
        {"extra_man_paths": (Path("rel"),)},
        {"extra_bin_dirs": (Path("rel"),)},
    ],
)
def test_levaconfig_rejects_invalid_invariants(kwargs: dict[str, tuple[object, ...]]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - message is internal, invariant is the point
        LevaConfig(**kwargs)  # type: ignore[arg-type]  # parametrised kwargs are untyped


def test_levaconfig_is_frozen_slotted_hashable() -> None:
    cfg = LevaConfig(sections=("1",))
    with pytest.raises(FrozenInstanceError):
        cfg.sections = ("8",)  # type: ignore[misc]  # frozen on purpose
    assert not hasattr(cfg, "__dict__")
    assert cfg == LevaConfig(sections=("1",))
    assert hash(cfg) == hash(LevaConfig(sections=("1",)))
    assert cfg != LevaConfig()


def test_default_digest_matches_canonical_literal() -> None:
    digest = LevaConfig().digest()
    assert digest == DEFAULT_DIGEST
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


def test_digest_ignores_key_order_whitespace_and_comments(tmp_path: Path, home: Path) -> None:
    a = write(
        tmp_path,
        'sections = ["1", "5"]\nextra_man_paths = ["/opt/man"]\nextra_bin_dirs = ["/opt/bin"]\n',
        "a.toml",
    )
    b = write(
        tmp_path,
        '# hello\nextra_bin_dirs   =  [ "/opt/bin" ]  # c\n\nextra_man_paths=["/opt/man"]\n'
        'sections=["1","5"]\n',
        "b.toml",
    )
    assert load_config(a, home).digest() == load_config(b, home).digest()


def test_digest_same_for_tilde_and_expanded_path(tmp_path: Path, home: Path) -> None:
    tilde = load_config(write(tmp_path, 'extra_man_paths = ["~/man"]', "a.toml"), home)
    full = load_config(write(tmp_path, f'extra_man_paths = ["{home}/man"]', "b.toml"), home)
    assert tilde.digest() == full.digest()


def test_digest_changes_with_every_field() -> None:
    base = LevaConfig()
    digests = {
        base.digest(),
        LevaConfig(sections=("1", "8", "5")).digest(),
        LevaConfig(sections=("8", "1")).digest(),
        LevaConfig(extra_man_paths=(Path("/a"),)).digest(),
        LevaConfig(extra_bin_dirs=(Path("/a"),)).digest(),
        LevaConfig(extra_man_paths=(Path("/a"), Path("/b"))).digest(),
        LevaConfig(extra_man_paths=(Path("/b"), Path("/a"))).digest(),
    }
    assert len(digests) == 7


def test_digest_handles_non_ascii_path() -> None:
    plain = LevaConfig(extra_man_paths=(Path("/opt/man"),)).digest()
    accented = LevaConfig(extra_man_paths=(Path("/opt/mån"),)).digest()
    assert accented != plain
    assert len(accented) == 64


def test_tilde_expansion_ignores_process_env(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", "/nowhere")
    cfg = load_config(write(tmp_path, 'extra_man_paths = ["~/man"]'), home)
    assert cfg.extra_man_paths == (home / "man",)


def test_public_api() -> None:
    assert config.__all__ == ["DEFAULT_SECTIONS", "LevaConfig", "load_config"]
