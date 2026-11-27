"""`leva.ingest.IndexBuilder.build` end to end over a synthetic man and bin tree."""

from __future__ import annotations

import shutil
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from leva.content import (
    ContentProvider,
    ContentRecord,
    CuratedYamlProvider,
    TldrSnapshotProvider,
    content_version,
)
from leva.ingest import (
    IndexBuilder,
    NullProgress,
    Staleness,
    compute_fingerprint,
)
from leva.ingest._lock import BUSY, LOCK_NAME, index_lock
from leva.manparse import MandocRenderer, ManRenderer
from leva.model import ContentError, IngestError, Kind, Origin
from leva.repo import Repository
from leva.sources import ExecutableScanner, ManPageLocator, SystemInfo
from leva.store import open_readonly
from tests.support.fake_bin import fake_bin
from tests.support.ingest_fakes import (
    FakeCancel,
    FakeProber,
    FakeRenderer,
    RecordingProgress,
    rendered_page,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CONTENT = FIXTURES / "content" / "valid"
SYSTEM = SystemInfo("26.2", "25C56", "arm64")
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_DIGEST = "c" * 64
LEVA_VERSION = "0.0.0-test"
UNREADABLE = "man pages unreadable; run leva doctor"
NOT_INSTALLED = "curated command not installed"
STUB_SOURCE = ".so man1/test.1\n"
DUMMY_SOURCE = '.\\" synthetic page\n'


@dataclass(frozen=True)
class Tree:
    """A synthetic man and bin tree under ``tmp_path``.

    Attributes:
        man: Man root holding ``man1`` and ``man8``.
        bin: Directory of fake executables.
        target: Index path, outside every scanned directory.
        texts: Rendered text of every page that is not a stub.
    """

    man: Path
    bin: Path
    target: Path
    texts: dict[Path, str]


def builtins_body(*items: tuple[str, str]) -> str:
    return "\n".join(f"{term}\n       {desc}" for term, desc in items)


def man_pages(man: Path) -> dict[Path, str]:
    """Return the rendered text of every non-stub page, keyed by the file written under `man`."""
    pages = {
        ("1", "echo"): rendered_page("echo", "1", "write arguments to the output"),
        ("1", "test"): rendered_page("test", "1", "evaluate a condition"),
        ("1", "git"): rendered_page("git", "1", "a synthetic version control tool"),
        ("1", "git-commit"): rendered_page(
            "git-commit",
            "1",
            "record changes",
            sections=[("SYNOPSIS", "git commit [-m msg]")],
        ),
        ("1", "alpha"): rendered_page("alpha", "1", "a synthetic alpha"),
        ("1", "zshbuiltins"): rendered_page(
            "zshbuiltins",
            "1",
            "zsh built-in commands",
            sections=[
                (
                    "SHELL BUILTIN COMMANDS",
                    builtins_body(
                        ("echo [-n] [arg ...]", "Write the arguments to standard output."),
                        ("cd [dir]", "Change the current directory."),
                    ),
                )
            ],
        ),
        ("1", "bash"): rendered_page(
            "bash",
            "1",
            "the synthetic shell",
            sections=[
                (
                    "SHELL BUILTIN COMMANDS",
                    builtins_body(
                        ("echo [arg ...]", "Output the arguments."),
                        ("cd [dir]", "Move to another directory."),
                    ),
                )
            ],
        ),
        ("8", "sync"): rendered_page("sync", "8", "flush file system buffers"),
    }
    return {
        man / f"man{section}" / f"{name}.{section}": text for (section, name), text in pages.items()
    }


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    man = tmp_path / "man"
    texts = man_pages(man)
    for path in texts:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DUMMY_SOURCE, encoding="utf-8")
    (man / "man1" / "[.1").write_text(STUB_SOURCE, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    for name in ("echo", "test", "[", "git", "alpha", "bat"):
        fake_bin(bin_dir, name, "exit 0")
    return Tree(man, bin_dir, tmp_path / "data" / "index.db", texts)


def make_builder(
    tree: Tree,
    *,
    renderer: ManRenderer | None = None,
    providers: Sequence[ContentProvider] | None = None,
    workers: int = 2,
) -> IndexBuilder:
    if providers is None:
        providers = [CuratedYamlProvider(CONTENT), TldrSnapshotProvider(FIXTURES)]
    return IndexBuilder(
        executables=ExecutableScanner([tree.bin]),
        man=ManPageLocator([tree.man]),
        renderer=renderer if renderer is not None else FakeRenderer(tree.texts),
        providers=providers,
        system=SYSTEM,
        config_digest=CONFIG_DIGEST,
        clock=lambda: FIXED_TIME,
        leva_version=LEVA_VERSION,
        content_root=CONTENT,
        probe_factory=FakeProber({}).factory,
        workers=workers,
    )


@contextmanager
def open_index(path: Path) -> Iterator[Repository]:
    repo = Repository(open_readonly(path))
    try:
        yield repo
    finally:
        repo.close()


def new_file(target: Path) -> Path:
    return target.with_name(target.name + ".new")


def test_full_build_indexes_every_source(tree: Tree) -> None:
    builder = make_builder(tree)
    report = builder.build(tree.target, NullProgress())

    assert report.entries == 13
    assert report.man_pages == 8
    assert report.curated == 1
    assert report.skipped == (("beta", NOT_INSTALLED),)
    assert report.seconds >= 0
    with open_index(tree.target) as repo:
        bracket = repo.get_entry("[")
        assert bracket is not None
        assert bracket.name == "test"
        echo = repo.get_entry("echo")
        assert echo is not None
        assert (echo.section, echo.kind, echo.path) == (
            "1",
            Kind.EXECUTABLE,
            str(tree.bin / "echo"),
        )
        builtin_origins = {
            row.origin for row in repo.names() if row.name == "echo" and row.kind is Kind.BUILTIN
        }
        assert builtin_origins == {Origin.ZSH, Origin.BASH}
        git = repo.get_entry("git")
        assert git is not None
        assert "commit" in [sub.name for sub in repo.subcommands(git.id)]
        bat = repo.get_entry("bat")
        assert bat is not None
        assert (bat.kind, bat.section, bat.has_man) == (Kind.EXECUTABLE, None, False)
        alpha = repo.get_entry("alpha")
        assert alpha is not None
        assert alpha.curated
        assert {example.source for example in repo.examples(alpha.id)} == {"curated", "tldr"}
        meta = repo.meta()
    assert meta["index_digest"] == report.digest
    assert meta["attribution"]
    assert meta["leva_version"] == LEVA_VERSION
    assert meta["content_version"] == content_version(CONTENT)
    assert (meta["macos_version"], meta["macos_build"]) == ("26.2", "25C56")
    assert meta["fingerprint_version"] == builder.fingerprint().version_part
    assert meta["fingerprint_system"] == builder.fingerprint().system_part
    assert builder.staleness(tree.target) is Staleness.FRESH


def test_progress_phases_come_in_order(tree: Tree) -> None:
    progress = RecordingProgress()
    make_builder(tree).build(tree.target, progress)
    phases = [
        payload[0]
        for kind, payload in progress.events
        if kind == "phase" and isinstance(payload, tuple)
    ]
    assert phases == ["scan", "render", "enrich", "write", "finalize"]


def test_ids_follow_name_section_origin_order(tree: Tree) -> None:
    report = make_builder(tree).build(tree.target, NullProgress())
    with open_index(tree.target) as repo:
        entries = [repo.get_entry_by_id(entry_id) for entry_id in range(1, report.entries + 1)]
        assert repo.get_entry_by_id(report.entries + 1) is None
    keys = []
    for entry in entries:
        assert entry is not None
        keys.append((entry.name, entry.section or "", entry.origin.value))
    assert keys == sorted(keys)


def test_same_inputs_give_the_same_digest(tree: Tree, tmp_path: Path) -> None:
    first = make_builder(tree).build(tree.target, NullProgress())
    other = make_builder(tree).build(tmp_path / "other" / "index.db", NullProgress())
    rebuilt = make_builder(tree).build(tree.target, NullProgress())
    assert first.digest == other.digest == rebuilt.digest


def test_stale_new_file_is_replaced(tree: Tree) -> None:
    tree.target.parent.mkdir(parents=True)
    new_file(tree.target).write_text("garbage", encoding="utf-8")
    make_builder(tree).build(tree.target, NullProgress())
    assert not new_file(tree.target).exists()
    with open_index(tree.target) as repo:
        assert repo.stats().entries == 13


def test_old_index_is_kept_when_the_build_fails(tree: Tree) -> None:
    make_builder(tree).build(tree.target, NullProgress())
    before = tree.target.read_bytes()
    failing = make_builder(tree, renderer=FakeRenderer(tree.texts, failing=tree.texts))
    with pytest.raises(IngestError) as caught:
        failing.build(tree.target, NullProgress())
    assert caught.value.message == UNREADABLE
    assert tree.target.read_bytes() == before
    assert not new_file(tree.target).exists()


def test_keyboard_interrupt_cleans_up_and_releases_the_lock(tree: Tree) -> None:
    make_builder(tree).build(tree.target, NullProgress())
    before = tree.target.read_bytes()

    def interrupt(name: str, total: int | None) -> None:
        if name == "write":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        make_builder(tree).build(tree.target, RecordingProgress(on_phase=interrupt))
    assert tree.target.read_bytes() == before
    assert not new_file(tree.target).exists()
    make_builder(tree).build(tree.target, NullProgress())


def test_interrupt_while_writing_removes_the_partial_file(tree: Tree) -> None:
    phases: list[str] = []

    def interrupt(n: int) -> None:
        if phases[-1] == "write":
            raise KeyboardInterrupt

    progress = RecordingProgress(
        on_phase=lambda name, total: phases.append(name), on_advance=interrupt
    )
    with pytest.raises(KeyboardInterrupt):
        make_builder(tree).build(tree.target, progress)
    assert not tree.target.exists()
    assert not new_file(tree.target).exists()


def test_cancel_stops_the_build_and_keeps_the_old_index(tree: Tree) -> None:
    make_builder(tree).build(tree.target, NullProgress())
    before = tree.target.read_bytes()
    cancel = FakeCancel()

    def cancel_at_enrich(name: str, total: int | None) -> None:
        if name == "enrich":
            cancel.set()

    with pytest.raises(IngestError) as caught:
        make_builder(tree).build(
            tree.target, RecordingProgress(on_phase=cancel_at_enrich), cancel=cancel
        )
    assert caught.value.message == "build cancelled"
    assert tree.target.read_bytes() == before
    assert not new_file(tree.target).exists()


def test_cancel_while_writing_removes_the_partial_file(tree: Tree) -> None:
    cancel = FakeCancel()
    phases: list[str] = []

    def cancel_on_advance(n: int) -> None:
        if phases[-1] == "write":
            cancel.set()

    progress = RecordingProgress(
        on_phase=lambda name, total: phases.append(name), on_advance=cancel_on_advance
    )
    with pytest.raises(IngestError) as caught:
        make_builder(tree).build(tree.target, progress, cancel=cancel)
    assert caught.value.message == "build cancelled"
    assert not tree.target.exists()
    assert not new_file(tree.target).exists()


def test_lock_contention_fails_without_writing(tree: Tree) -> None:
    tree.target.parent.mkdir(parents=True)
    with index_lock(tree.target.parent / LOCK_NAME), pytest.raises(IngestError) as caught:
        make_builder(tree).build(tree.target, NullProgress())
    assert caught.value.message == BUSY
    assert not tree.target.exists()
    assert not new_file(tree.target).exists()


def test_unwritable_parent_is_an_ingest_error(tree: Tree, tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(IngestError) as caught:
        make_builder(tree).build(blocker / "index.db", NullProgress())
    assert caught.value.message.startswith("cannot write index")
    assert isinstance(caught.value.__cause__, OSError)


def test_target_that_is_a_directory_is_an_ingest_error(tree: Tree) -> None:
    tree.target.mkdir(parents=True)
    with pytest.raises(IngestError) as caught:
        make_builder(tree).build(tree.target, NullProgress())
    assert caught.value.message == f"cannot write index: {tree.target}"
    assert tree.target.is_dir()
    assert not new_file(tree.target).exists()


def test_content_error_propagates_unchanged(tree: Tree) -> None:
    class FailingProvider:
        def load(self) -> Iterator[ContentRecord]:
            yield from ()
            raise ContentError("bad.yaml:name: broken")

    builder = make_builder(tree, providers=[FailingProvider()])
    with pytest.raises(ContentError) as caught:
        builder.build(tree.target, NullProgress())
    assert caught.value.message == "bad.yaml:name: broken"
    assert not new_file(tree.target).exists()
    assert not tree.target.exists()


def test_report_seconds_come_from_the_injected_timer(tree: Tree) -> None:
    ticks = iter([10.0, 12.5])
    builder = IndexBuilder(
        executables=ExecutableScanner([tree.bin]),
        man=ManPageLocator([tree.man]),
        renderer=FakeRenderer(tree.texts),
        providers=[],
        system=SYSTEM,
        config_digest=CONFIG_DIGEST,
        clock=lambda: FIXED_TIME,
        leva_version=LEVA_VERSION,
        content_root=CONTENT,
        probe_factory=FakeProber({}).factory,
        timer=lambda: next(ticks),
    )
    report = builder.build(tree.target, NullProgress())
    assert report.seconds == 2.5
    assert report.curated == 0


@pytest.mark.skipif(not Path("/usr/bin/mandoc").exists(), reason="mandoc not installed")
def test_build_with_the_real_mandoc_renderer(tmp_path: Path) -> None:
    man1 = tmp_path / "man" / "man1"
    man1.mkdir(parents=True)
    for name in ("leva-sample.1", "leva-stub.1", "leva-target.1", "leva-legacy.1"):
        shutil.copy(FIXTURES / "man" / "src" / name, man1 / name)
    bin_dir = tmp_path / "bin"
    fake_bin(bin_dir, "leva-sample", "exit 0")
    builder = IndexBuilder(
        executables=ExecutableScanner([bin_dir]),
        man=ManPageLocator([tmp_path / "man"]),
        renderer=MandocRenderer(),
        providers=[],
        system=SYSTEM,
        config_digest=CONFIG_DIGEST,
        clock=lambda: FIXED_TIME,
        leva_version=LEVA_VERSION,
        content_root=CONTENT,
        probe_factory=FakeProber({}).factory,
    )
    report = builder.build(tmp_path / "data" / "index.db", NullProgress())

    assert report.skipped == ()
    with open_index(tmp_path / "data" / "index.db") as repo:
        sample = repo.get_entry("leva-sample")
        assert sample is not None
        assert sample.kind is Kind.EXECUTABLE
        assert sample.summary
        stub = repo.get_entry("leva-stub")
        assert stub is not None
        assert stub.name == "leva-target"
        assert repo.get_entry("leva-legacy") is not None


def test_zero_workers_is_a_programmer_error(tree: Tree) -> None:
    with pytest.raises(ValueError, match="workers"):
        make_builder(tree, workers=0)


def test_fingerprint_matches_compute_fingerprint(tree: Tree) -> None:
    expected = compute_fingerprint(
        leva_version=LEVA_VERSION,
        content_version=content_version(CONTENT),
        system=SYSTEM,
        man_dirs=[tree.man],
        sections=("1", "8"),
        bin_dirs=[tree.bin],
        config_digest=CONFIG_DIGEST,
    )
    assert make_builder(tree).fingerprint() == expected


def test_staleness_of_a_missing_index(tree: Tree, tmp_path: Path) -> None:
    assert make_builder(tree).staleness(tmp_path / "nope.db") is Staleness.MISSING
