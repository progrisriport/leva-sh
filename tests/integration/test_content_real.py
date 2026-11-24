"""Integration tests: the providers load the content bundled with the package."""

from __future__ import annotations

from leva.content import (
    CuratedYamlProvider,
    TldrSnapshotProvider,
    content_version,
    default_root,
)


def test_every_bundled_curated_file_loads() -> None:
    commands = {command.name: command for command in CuratedYamlProvider(default_root()).load()}

    ls = commands["ls"]
    assert len(ls.examples) >= 3
    assert any(example.verify.mode == "exec" for example in ls.examples)
    assert [example.to_example().id for example in ls.examples] == [
        example.id for example in ls.examples
    ]


def test_bundled_tldr_snapshot_loads_without_error() -> None:
    pages = list(TldrSnapshotProvider(default_root()).load())

    assert [page.name for page in pages] == sorted(page.name for page in pages)


def test_bundled_content_version_is_stable() -> None:
    version = content_version(default_root())

    assert len(version) == 64
    assert content_version(default_root()) == version
