"""Suite-wide test harness: isolated environment, Hypothesis profile, directory markers."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from hypothesis import settings

pytest_plugins = ("pytester",)

TESTS_ROOT: Final = Path(__file__).resolve().parent

# Top-level directory under tests/ -> marker applied to every test collected from it.
DIRECTORY_MARKERS: Final = {
    "integration": "integration",
    "tui": "tui",
    "live": "macos_live",
}

PINNED_ENV: Final = {
    "TZ": "UTC",
    "LC_ALL": "en_US.UTF-8",
    "LANG": "en_US.UTF-8",
    "LANGUAGE": "en",
    "MANWIDTH": "80",
    "COLUMNS": "120",
}

# D-018: deterministic runs; regressions are pinned with @example, not a committed database.
settings.register_profile("leva", derandomize=True, deadline=None, print_blob=True)
settings.load_profile("leva")


@pytest.fixture(autouse=True)
def clean_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test: ``LEVA_HOME`` is ``tmp_path``, ``HOME`` is ``tmp_path/home``.

    Locale, time zone and terminal width are pinned so output never depends on the user's
    shell, and no test can reach the real ``~``.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("LEVA_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(home))
    for name, value in PINNED_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark tests by directory before ``-m`` deselects (so ``not macos_live`` sees them)."""
    for item in items:
        marker = directory_marker(item.path)
        if marker is not None:
            item.add_marker(marker)


def directory_marker(path: Path) -> str | None:
    """Return the marker for a test file from its top-level directory under ``tests/``."""
    if not path.is_relative_to(TESTS_ROOT):
        return None
    return DIRECTORY_MARKERS.get(path.relative_to(TESTS_ROOT).parts[0])
