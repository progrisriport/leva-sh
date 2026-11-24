"""Read the vendored tldr snapshot (``tldr/common.jsonl`` and ``tldr/osx.jsonl``)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from leva.content._schema import TldrExample, TldrPage
from leva.content._yaml_provider import read_text
from leva.model import ContentError, Example, is_name

_logger = logging.getLogger("leva.content")

TLDR_DIR: Final = "tldr"
_PLATFORMS: Final = ("common", "osx")
_PAGE_KEYS: Final = ("name", "platform", "description", "examples")
_EXAMPLE_KEYS: Final = frozenset({"desc", "cmd"})


class _DuplicateKeyError(ValueError):
    """A JSON object repeats a key."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_constant(name: str) -> object:
    raise ValueError(f"invalid constant {name}")


def _parse_line(line: str, at: str) -> object:
    try:
        return json.loads(line, object_pairs_hook=_object, parse_constant=_reject_constant)
    except _DuplicateKeyError as exc:
        raise ContentError(f"{at}: duplicate key {exc.key!r}") from exc
    except (ValueError, RecursionError) as exc:
        raise ContentError(f"{at}: invalid JSON") from exc


def _read_examples(value: object, at: str) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        raise ContentError(f"{at}:examples: must be a list")
    pairs: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        if (
            not isinstance(item, dict)
            or item.keys() != _EXAMPLE_KEYS
            or not all(isinstance(text, str) for text in item.values())
        ):
            raise ContentError(f"{at}:examples[{index}]: expected an object with keys desc, cmd")
        pairs.append((item["desc"].strip(), item["cmd"].strip()))
    return pairs


def _keep_valid(name: str, pairs: list[tuple[str, str]], at: str) -> tuple[TldrExample, ...]:
    """Drop (and log) examples whose command breaks the `Example` invariants (D-033)."""
    kept: list[TldrExample] = []
    for desc, cmd in pairs:
        try:
            Example(f"{name}-tldr-1", desc, cmd, "tldr", "none")
        except ValueError as exc:
            _logger.warning("tldr example dropped: %s: %s", at, exc)
        else:
            kept.append(TldrExample(desc, cmd))
    return tuple(kept)


def _page(raw: object, stem: str, at: str) -> TldrPage:
    if not isinstance(raw, dict):
        raise ContentError(f"{at}: expected an object")
    for key in raw:
        if key not in _PAGE_KEYS:
            raise ContentError(f"{at}: unknown key {key!r}")
    for key in _PAGE_KEYS:
        if key not in raw:
            raise ContentError(f"{at}: missing key {key!r}")
    name = raw["name"]
    if not isinstance(name, str) or not is_name(name):
        raise ContentError(f"{at}:name: must be a command name")
    if raw["platform"] != stem:
        raise ContentError(f"{at}:platform: must be {stem!r}")
    description = raw["description"]
    if not isinstance(description, str):
        raise ContentError(f"{at}:description: must be a string")
    examples = _keep_valid(name, _read_examples(raw["examples"], at), at)
    return TldrPage(name, stem, description.strip(), examples)


def _read_file(root: Path, stem: str) -> dict[str, TldrPage]:
    path = root / TLDR_DIR / f"{stem}.jsonl"
    label = f"{TLDR_DIR}/{stem}.jsonl"
    if not path.is_file():
        return {}
    pages: dict[str, TldrPage] = {}
    for number, line in enumerate(read_text(path, label).split("\n"), start=1):
        if not line.strip():
            continue
        at = f"{label}:{number}"
        page = _page(_parse_line(line, at), stem, at)
        if page.name in pages:
            raise ContentError(f"{at}:name: duplicate page {page.name!r}")
        pages[page.name] = page
    return pages


class TldrSnapshotProvider:
    """Load the tldr snapshot of a content root (D-017, D-046).

    Attributes:
        root: Content root that holds ``tldr/``.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self) -> Iterator[TldrPage]:
        """Read both snapshot files; a missing file counts as empty.

        Post: pages sorted by name; a page of ``osx`` replaces the page of the same name from
            ``common``; invalid example commands are dropped with a warning; all lines are
            validated before the first page is returned.

        Raises:
            ContentError: For an unreadable, non-UTF-8 or malformed file; the message reads
                ``file:line:field: reason``.
        """
        merged: dict[str, TldrPage] = {}
        for stem in _PLATFORMS:
            merged.update(_read_file(self.root, stem))
        return iter(sorted(merged.values(), key=lambda page: page.name))
