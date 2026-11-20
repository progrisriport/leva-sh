"""Leva: a macOS terminal encyclopedia of shell commands."""

from __future__ import annotations

from importlib.metadata import version

__all__ = ["__version__"]

__version__: str = version("leva")
