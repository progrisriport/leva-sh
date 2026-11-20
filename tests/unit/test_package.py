"""Package scaffold: version, typing marker, D-002 package set, wheel contents."""

from __future__ import annotations

import importlib
import pkgutil
import re
import tomllib
from importlib import metadata, resources
from pathlib import Path

import pytest

import leva

D002_PACKAGES = (
    "model",
    "paths",
    "placeholders",
    "clipboard",
    "config",
    "sources",
    "manparse",
    "subcmd",
    "content",
    "store",
    "repo",
    "search",
    "library",
    "ingest",
    "tui",
    "cli",
    "verify",
)

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_version_matches_installed_distribution_metadata() -> None:
    assert leva.__version__ == metadata.version("leva")
    assert re.fullmatch(r"\d+\.\d+\.\d+", leva.__version__)


def test_package_ships_pep561_typed_marker() -> None:
    assert resources.files("leva").joinpath("py.typed").is_file()


def test_subpackages_are_exactly_the_d002_set() -> None:
    found = {info.name for info in pkgutil.iter_modules(leva.__path__)}

    assert found == set(D002_PACKAGES)


@pytest.mark.parametrize("name", D002_PACKAGES)
def test_subpackage_is_a_package_with_a_responsibility_docstring(name: str) -> None:
    module = importlib.import_module(f"leva.{name}")

    assert hasattr(module, "__path__"), f"leva.{name} must be a package"
    assert module.__doc__ is not None
    assert module.__doc__.strip()


def test_wheel_excludes_the_verify_package() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    wheel = config["tool"]["hatch"]["build"]["targets"]["wheel"]

    assert wheel["packages"] == ["src/leva"]
    assert "src/leva/verify" in wheel["exclude"]
