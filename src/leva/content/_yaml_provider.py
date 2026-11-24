"""Read the curated ``commands/*.yaml`` files from a content root with a strict YAML loader."""

from __future__ import annotations

from collections.abc import Hashable, Iterator
from pathlib import Path
from typing import Any, Final, Protocol

import yaml

from leva.content._schema import ContentRecord, CuratedCommand
from leva.content._validate import validate_command
from leva.model import ContentError

COMMANDS_DIR: Final = "commands"
_EXTENSION: Final = ".yaml"
_REJECTED_EXTENSION: Final = ".yml"


class ContentProvider(Protocol):
    """A source of validated content records."""

    def load(self) -> Iterator[ContentRecord]:
        """Read and validate every record.

        Post: nothing is yielded unless the whole source is valid.

        Raises:
            ContentError: If the source is unreadable or invalid; the message reads
                ``file:field: reason``.
        """
        ...


class _DuplicateKeyError(yaml.MarkedYAMLError):
    """A mapping repeats a key; ``problem_mark`` points at the second occurrence."""

    def __init__(self, key: object, mark: yaml.Mark) -> None:
        super().__init__(problem="duplicate key", problem_mark=mark)
        self.key = key
        self.line = mark.line + 1


class _StrictLoader(yaml.SafeLoader):
    """A safe loader that rejects duplicate mapping keys instead of keeping the last one."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        self.flatten_mapping(node)
        seen: set[Hashable] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, Hashable):
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found unhashable key",
                    key_node.start_mark,
                )
            if key in seen:
                raise _DuplicateKeyError(key, key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep)


def read_text(path: Path, label: str) -> str:
    """Read a file as strict UTF-8.

    Args:
        path: File to read.
        label: Name used in error messages, such as ``commands/ls.yaml``.

    Returns:
        The decoded text.

    Raises:
        ContentError: If the file cannot be read or is not valid UTF-8.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ContentError(f"{label}: cannot read file") from exc
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContentError(f"{label}: not valid UTF-8") from exc


def command_files(root: Path) -> list[Path]:
    """List the regular files directly in ``root/commands``, sorted by name.

    Post: empty when ``commands`` is not a directory.

    Raises:
        ContentError: If the directory cannot be listed.
    """
    commands = root / COMMANDS_DIR
    if not commands.is_dir():
        return []
    try:
        files = [path for path in commands.iterdir() if path.is_file()]
    except OSError as exc:
        raise ContentError(f"{COMMANDS_DIR}: cannot read directory") from exc
    return sorted(files, key=lambda path: path.name)


def is_curated_file(path: Path) -> bool:
    """Tell whether ``path`` has the ``.yaml`` extension of a curated file."""
    return path.suffix == _EXTENSION


def _parse(text: str, label: str) -> object:
    try:
        loader = _StrictLoader(text)  # the reader rejects control characters here
        try:
            return loader.get_single_data()
        finally:
            loader.dispose()
    except _DuplicateKeyError as exc:
        raise ContentError(f"{label}: duplicate key {exc.key!r} at line {exc.line}") from exc
    except yaml.YAMLError as exc:
        mark = exc.problem_mark if isinstance(exc, yaml.MarkedYAMLError) else None
        where = f" at line {mark.line + 1}" if mark is not None else ""
        raise ContentError(f"{label}: invalid YAML{where}") from exc
    except (ValueError, RecursionError) as exc:  # constructors: bad dates, long ints; deep nesting
        raise ContentError(f"{label}: invalid YAML") from exc


def _check_ids(command: CuratedCommand, label: str, owners: dict[str, str]) -> None:
    for index, example in enumerate(command.examples):
        other = owners.setdefault(example.id, label)
        if other != label:
            raise ContentError(
                f"{label}:examples[{index}].id: duplicate example id {example.id!r}"
                f" (also in {other})"
            )


class CuratedYamlProvider:
    """Load and validate every ``commands/*.yaml`` file of a content root (D-046).

    Attributes:
        root: Content root that holds ``commands/``.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self) -> Iterator[CuratedCommand]:
        """Read, parse and validate every curated file.

        Pre: nothing; a missing ``commands/`` directory means no content.
        Post: commands in file-name order; every call rereads the disk; all files are
            validated before the first command is returned.

        Raises:
            ContentError: For an unreadable, non-UTF-8, invalid or ``.yml`` file and for an
                example id used by two files; the message reads ``file:field: reason``.
        """
        commands: list[CuratedCommand] = []
        owners: dict[str, str] = {}
        for path in command_files(self.root):
            if path.suffix == _REJECTED_EXTENSION:
                raise ContentError(f"{COMMANDS_DIR}/{path.name}: use the .yaml extension")
            if not is_curated_file(path):
                continue
            label = f"{COMMANDS_DIR}/{path.name}"
            command = validate_command(_parse(read_text(path, label), label), label)
            _check_ids(command, label, owners)
            commands.append(command)
        return iter(commands)
