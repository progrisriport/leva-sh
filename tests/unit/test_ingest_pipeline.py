"""leva.ingest page pipeline: winners, stub resolution, parallel render, failures, cancel."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from pathlib import Path

import pytest

from leva.ingest._pipeline import (
    MAX_FAILURE_RATIO,
    UNREADABLE,
    Page,
    PageSet,
    StubAlias,
    page_label,
    render_pages,
    resolve_stub,
    select_winners,
)
from leva.ingest._progress import CANCELLED
from leva.manparse import parse_man
from leva.model import IngestError, Origin
from leva.sources import ManFile, ManPageLocator
from tests.support.ingest_fakes import FakeCancel, FakeRenderer, RecordingProgress, rendered_page

DUMMY = ".TH X 1\n"


def write(path: Path, content: str | bytes = DUMMY) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def locate(*man_dirs: Path) -> list[ManFile]:
    return list(ManPageLocator(list(man_dirs), ("1", "8")).locate())


def plain_files(root: Path, names: Sequence[str]) -> list[ManFile]:
    for name in names:
        write(root / "man1" / f"{name}.1")
    return locate(root)


def man_file(path: Path, name: str = "x", section: str = "1") -> ManFile:
    return ManFile(path, name, section, Origin.MACOS, 0, 0)


def test_rendered_page_round_trips_through_parse_man() -> None:
    text = rendered_page(
        "ls",
        "1",
        "list directory contents",
        names=("ls", "dir"),
        sections=[("DESCRIPTION", "line one\nline two")],
    )
    parsed = parse_man(text, name_hint="ls")
    assert parsed.names == ("ls", "dir")
    assert parsed.summary == "list directory contents"
    assert [section.heading for section in parsed.sections] == ["NAME", "DESCRIPTION"]
    assert parsed.sections[1].body == "     line one\n     line two"
    assert parsed.redirect_to is None


def test_rendered_page_without_summary_has_no_separator() -> None:
    parsed = parse_man(rendered_page("ls"), name_hint="ls")
    assert parsed.names == ("ls",)
    assert parsed.summary == ""


def test_page_label_is_name_and_section() -> None:
    assert page_label(man_file(Path("/m/man8/x.8"), "x", "8")) == "x(8)"


def test_select_winners_first_directory_wins(tmp_path: Path) -> None:
    write(tmp_path / "brew" / "man1" / "git.1")
    write(tmp_path / "clt" / "man1" / "git.1")
    write(tmp_path / "clt" / "man1" / "foo.1")
    write(tmp_path / "usr" / "man1" / "foo.1")
    files = locate(tmp_path / "brew", tmp_path / "clt", tmp_path / "usr")
    winners = select_winners(files)
    assert [(m.name, m.dir_index) for m in winners] == [("foo", 1), ("git", 0)]
    assert winners[1].path == tmp_path / "brew" / "man1" / "git.1"


def test_select_winners_keeps_one_per_section_and_order(tmp_path: Path) -> None:
    write(tmp_path / "d" / "man1" / "x.1")
    write(tmp_path / "d" / "man8" / "x.8")
    write(tmp_path / "d" / "man1" / "a.1")
    files = locate(tmp_path / "d")
    winners = select_winners(files)
    assert [(m.name, m.section) for m in winners] == [(m.name, m.section) for m in files]
    assert [(m.name, m.section) for m in winners] == [("a", "1"), ("x", "1"), ("x", "8")]


def test_select_winners_empty() -> None:
    assert select_winners([]) == []


def test_resolve_stub_from_man_root(tmp_path: Path) -> None:
    root = tmp_path / "man"
    target = write(root / "man1" / "b.1")
    stub = man_file(root / "man1" / "a.1", "a")
    assert resolve_stub(stub, "man1/b.1") == target


def test_resolve_stub_from_page_dir(tmp_path: Path) -> None:
    root = tmp_path / "man"
    target = write(root / "man1" / "b.1")
    stub = man_file(root / "man1" / "a.1", "a")
    assert resolve_stub(stub, "b.1") == target


def test_resolve_stub_prefers_man_root_over_page_dir(tmp_path: Path) -> None:
    root = tmp_path / "man"
    from_root = write(root / "b.1")
    write(root / "man1" / "b.1")
    assert resolve_stub(man_file(root / "man1" / "a.1", "a"), "b.1") == from_root


def test_resolve_stub_finds_gz_only_target(tmp_path: Path) -> None:
    root = tmp_path / "man"
    target = write(root / "man1" / "b.1.gz", b"")
    stub = man_file(root / "man1" / "a.1", "a")
    assert resolve_stub(stub, "man1/b.1") == target


def test_resolve_stub_allows_paths_outside_the_man_dirs(tmp_path: Path) -> None:
    root = tmp_path / "share" / "man"
    target = write(tmp_path / "elsewhere" / "man1" / "c.1")
    stub = man_file(write(root / "man1" / "a.1"), "a")
    resolved = resolve_stub(stub, "../../elsewhere/man1/c.1")
    assert resolved is not None
    assert resolved.samefile(target)


def test_resolve_stub_missing_gives_none(tmp_path: Path) -> None:
    stub = man_file(tmp_path / "man" / "man1" / "a.1", "a")
    assert resolve_stub(stub, "man1/nope.1") is None


def test_resolve_stub_ignores_directories(tmp_path: Path) -> None:
    root = tmp_path / "man"
    (root / "man1" / "b.1").mkdir(parents=True)
    assert resolve_stub(man_file(root / "man1" / "a.1", "a"), "man1/b.1") is None


def test_resolve_stub_gz_argument_does_not_try_double_gz(tmp_path: Path) -> None:
    root = tmp_path / "man"
    write(root / "man1" / "b.1.gz.gz", b"")
    stub = man_file(root / "man1" / "a.1", "a")
    assert resolve_stub(stub, "man1/b.1.gz") is None


def test_resolve_stub_treats_oserror_as_missing(tmp_path: Path) -> None:
    stub = man_file(tmp_path / "man" / "man1" / "a.1", "a")
    assert resolve_stub(stub, "x" * 5000) is None


def test_plain_pages_come_back_in_input_order(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", ["a", "b", "c"])
    texts = {m.path: rendered_page(m.name, "1", f"summary {m.name}") for m in files}
    progress = RecordingProgress()
    result = render_pages(files, FakeRenderer(texts), progress)
    assert [page.man for page in result.pages] == files
    assert [page.parsed.names[0] for page in result.pages] == ["a", "b", "c"]
    assert [page.parsed.summary for page in result.pages] == ["summary a", "summary b", "summary c"]
    assert all(page.parsed.redirect_to is None for page in result.pages)
    assert result.aliases == ()
    assert result.skipped == ()
    assert progress.events == [
        ("phase", ("render", 3)),
        ("advance", 1),
        ("advance", 1),
        ("advance", 1),
    ]


def test_entry_name_is_the_man_file_name_not_the_first_name_line(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", ["a"])
    texts = {files[0].path: rendered_page("a", names=("other", "a"))}
    result = render_pages(files, FakeRenderer(texts), RecordingProgress())
    assert result.pages[0].man.name == "a"
    assert result.pages[0].parsed.names == ("other", "a")


def test_stub_to_an_indexed_page_becomes_an_alias(tmp_path: Path) -> None:
    root = tmp_path / "d"
    write(root / "man1" / "[.1", ".so man1/test.1\n")
    write(root / "man1" / "test.1")
    files = locate(root)
    renderer = FakeRenderer()
    result = render_pages(files, renderer, RecordingProgress())
    stub, real = files
    assert result.aliases == (StubAlias(stub, "test", "1"),)
    assert [page.man for page in result.pages] == [real]
    assert renderer.calls == [real.path]


def test_winning_stub_shadows_a_later_real_page(tmp_path: Path) -> None:
    write(tmp_path / "usr" / "man1" / "rsync.1", ".so man1/openrsync.1\n")
    write(tmp_path / "usr" / "man1" / "openrsync.1")
    write(tmp_path / "clt" / "man1" / "rsync.1")
    files = locate(tmp_path / "usr", tmp_path / "clt")
    renderer = FakeRenderer()
    result = render_pages(files, renderer, RecordingProgress())
    assert [
        (alias.man.name, alias.target_name, alias.target_section) for alias in result.aliases
    ] == [("rsync", "openrsync", "1")]
    assert result.aliases[0].man.dir_index == 0
    assert [page.man.name for page in result.pages] == ["openrsync"]
    assert renderer.calls == [tmp_path / "usr" / "man1" / "openrsync.1"]


def test_stub_alias_target_may_be_a_symlink_alias_of_another_file(tmp_path: Path) -> None:
    root = tmp_path / "d"
    write(root / "man1" / "real.1")
    (root / "man1").joinpath("link.1").symlink_to(root / "man1" / "real.1")
    write(root / "man1" / "stub.1", ".so man1/link.1\n")
    files = locate(root)
    result = render_pages(files, FakeRenderer(), RecordingProgress())
    assert {alias.man.name: alias.target_name for alias in result.aliases} == {"stub": "link"}


def test_stub_pointing_outside_the_man_dirs_is_rendered_as_itself(tmp_path: Path) -> None:
    root = tmp_path / "share" / "man"
    stub_path = write(root / "man1" / "x.1", ".so ../../elsewhere/man1/c.1\n")
    write(tmp_path / "elsewhere" / "man1" / "c.1")
    files = locate(root)
    renderer = FakeRenderer()
    result = render_pages(files, renderer, RecordingProgress())
    assert result.aliases == ()
    assert [page.man for page in result.pages] == files
    assert result.pages[0].parsed.redirect_to == "../../elsewhere/man1/c.1"
    assert result.pages[0].parsed.names == ("x",)
    assert renderer.calls == [stub_path]


def test_stub_with_missing_target_is_skipped_not_failed(tmp_path: Path) -> None:
    root = tmp_path / "d"
    write(root / "man1" / "x.1", ".so man1/nope.1\n")
    progress = RecordingProgress()
    renderer = FakeRenderer()
    result = render_pages(locate(root), renderer, progress)
    assert result.pages == ()
    assert result.aliases == ()
    assert result.skipped == (("x(1)", "stub target missing: man1/nope.1"),)
    assert renderer.calls == []
    assert progress.events == [
        ("phase", ("render", 1)),
        ("advance", 1),
        ("warn", "x(1): stub target missing: man1/nope.1"),
    ]


def test_stub_pointing_to_itself_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "d"
    write(root / "man1" / "x.1", ".so man1/x.1\n")
    progress = RecordingProgress()
    result = render_pages(locate(root), FakeRenderer(), progress)
    assert result.skipped == (("x(1)", "stub points to itself: man1/x.1"),)
    assert ("warn", "x(1): stub points to itself: man1/x.1") in progress.events


def test_stub_pointing_to_a_page_the_locator_skipped_is_rendered_as_itself(tmp_path: Path) -> None:
    root = tmp_path / "d"
    stub_path = write(root / "man1" / "x.1", ".so man1/y.2\n")
    write(root / "man1" / "y.2")
    renderer = FakeRenderer()
    result = render_pages(locate(root), renderer, RecordingProgress())
    assert result.pages[0].parsed.redirect_to == "man1/y.2"
    assert renderer.calls == [stub_path]


def test_unreadable_source_is_a_failure_and_never_rendered(tmp_path: Path) -> None:
    root = tmp_path / "d"
    garbage = write(root / "man1" / "bad.1.gz", b"not gzip")
    for name in "abcde":
        write(root / "man1" / f"{name}.1")
    files = locate(root)
    renderer = FakeRenderer()
    progress = RecordingProgress()
    result = render_pages(files, renderer, progress)
    assert result.skipped == (("bad(1)", f"cannot read man page: {garbage}"),)
    assert garbage not in renderer.calls
    assert [page.man.name for page in result.pages] == list("abcde")
    assert ("warn", f"bad(1): cannot read man page: {garbage}") in progress.events


def test_render_failure_is_skipped_and_the_rest_returned(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", list("abcdef"))
    bad = files[2].path
    progress = RecordingProgress()
    result = render_pages(files, FakeRenderer(failing={bad}), progress)
    assert result.skipped == (("c(1)", f"mandoc failed: {bad}"),)
    assert [page.man.name for page in result.pages] == list("abdef")
    assert ("warn", f"c(1): mandoc failed: {bad}") in progress.events
    assert sum(1 for kind, _ in progress.events if kind == "advance") == 6


def test_failures_up_to_twenty_percent_are_tolerated(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", [f"p{i}" for i in range(10)])
    failing = {m.path for m in files[:2]}
    result = render_pages(files, FakeRenderer(failing=failing), RecordingProgress())
    assert len(result.pages) == 8
    assert len(result.skipped) == 2
    assert MAX_FAILURE_RATIO == 0.2


def test_more_than_twenty_percent_failures_raise(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", [f"p{i}" for i in range(10)])
    failing = {m.path for m in files[:3]}
    with pytest.raises(IngestError) as info:
        render_pages(files, FakeRenderer(failing=failing), RecordingProgress())
    assert info.value.message == "man pages unreadable; run leva doctor" == UNREADABLE
    assert info.value.hint is None


def test_a_single_failing_page_out_of_one_raises(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", ["a"])
    with pytest.raises(IngestError, match="man pages unreadable"):
        render_pages(files, FakeRenderer(failing={files[0].path}), RecordingProgress())


def test_skipped_stubs_do_not_count_as_failures(tmp_path: Path) -> None:
    root = tmp_path / "d"
    for name in "abc":
        write(root / "man1" / f"{name}.1", f".so man1/missing-{name}.1\n")
    result = render_pages(locate(root), FakeRenderer(), RecordingProgress())
    assert len(result.skipped) == 3
    assert result.pages == ()


def test_results_follow_input_order_even_when_a_later_page_finishes_first(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", ["a", "b", "c"])
    path_a, _, path_c = (m.path for m in files)
    c_started = threading.Event()
    waited: list[bool] = []

    def hook(path: Path) -> None:
        if path == path_c:
            c_started.set()
        elif path == path_a:
            waited.append(c_started.wait(timeout=5))

    renderer = FakeRenderer(before_render=hook)
    result = render_pages(files, renderer, RecordingProgress(), workers=2)
    assert waited == [True]
    assert renderer.calls[-1] == path_a
    assert [page.man.name for page in result.pages] == ["a", "b", "c"]


def test_same_input_gives_equal_results(tmp_path: Path) -> None:
    root = tmp_path / "d"
    write(root / "man1" / "s.1", ".so man1/a.1\n")
    write(root / "man1" / "m.1", ".so man1/missing.1\n")
    for name in "abcdef":
        write(root / "man1" / f"{name}.1")
    files = locate(root)
    first = render_pages(files, FakeRenderer(), RecordingProgress(), workers=4)
    second = render_pages(files, FakeRenderer(), RecordingProgress(), workers=3)
    assert first == second
    assert isinstance(first, PageSet)
    assert all(isinstance(page, Page) for page in first.pages)


def test_cancel_from_a_render_stops_before_the_next_page(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", ["p1", "p2", "p3"])
    cancel = FakeCancel()
    path2 = files[1].path

    def hook(path: Path) -> None:
        if path == path2:
            cancel.set()

    renderer = FakeRenderer(before_render=hook)
    with pytest.raises(IngestError) as info:
        render_pages(files, renderer, RecordingProgress(), workers=1, cancel=cancel)
    assert info.value.message == "build cancelled" == CANCELLED
    assert renderer.calls == [files[0].path, path2]


def test_cancel_set_before_the_call_renders_nothing(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", ["a", "b"])
    cancel = FakeCancel()
    cancel.set()
    renderer = FakeRenderer()
    with pytest.raises(IngestError, match="build cancelled"):
        render_pages(files, renderer, RecordingProgress(), cancel=cancel)
    assert renderer.calls == []


class WorkerOnlyCancel:
    """Token seen as set by worker threads only, so the worker-side check decides."""

    def is_set(self) -> bool:
        return threading.current_thread() is not threading.main_thread()


def test_cancel_seen_by_the_worker_raises_without_rendering(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", ["a", "b"])
    renderer = FakeRenderer()
    progress = RecordingProgress()
    with pytest.raises(IngestError, match="build cancelled"):
        render_pages(files, renderer, progress, workers=1, cancel=WorkerOnlyCancel())
    assert renderer.calls == []
    assert progress.events == [("phase", ("render", 2))]


def test_keyboard_interrupt_propagates_and_the_pool_is_shut_down(tmp_path: Path) -> None:
    files = plain_files(tmp_path / "d", [f"p{i}" for i in range(6)])

    def interrupt(_: int) -> None:
        raise KeyboardInterrupt

    before = threading.active_count()
    with pytest.raises(KeyboardInterrupt):
        render_pages(files, FakeRenderer(), RecordingProgress(on_advance=interrupt), workers=2)
    assert threading.active_count() == before


def test_workers_below_one_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="workers"):
        render_pages([], FakeRenderer(), RecordingProgress(), workers=0)


def test_empty_input_gives_an_empty_page_set() -> None:
    progress = RecordingProgress()
    result = render_pages([], FakeRenderer(), progress)
    assert result == PageSet(pages=(), aliases=(), skipped=())
    assert progress.events == [("phase", ("render", 0))]
