# Phase 2 review

- Date: 2026-11-23 · Scope: T-2.1..T-2.7 · Reviewer: ralph loop (executor, two Opus review rounds)

## Scope

`leva.sources` (`_system`, `_executables`, `_origin`, `_names`, `_manpages`, `_probe`), `leva.manparse`
(`_overstrike`, `_stub`, `_render`, `_sections`, `_name`, `_definitions`, `_builtins`), `leva.subcmd`, their
unit and integration tests and the fixtures under `tests/fixtures/{man,help}/`. Checked against PLAN §4 RC,
DITS §5–§7, D-004, D-005, D-007..D-009, D-027, D-038..D-044, and cross-checked against T-6.2..T-6.6, T-9.x.

## Checked items

Baseline before changes: `make check` green, 801 passed, all coverage gates ok, 3 contracts kept.

1. Public API matches DITS + DECISIONS: ok. Deviations are recorded: `BuiltinSource` dropped (D-002),
   `ManFile` fields (D-040), `SystemInfo.detect` kwargs (D-038), `ProbeRunner` exit status ignored (D-042),
   `col -bx` (D-007), uppercase headings (D-027), `Mapping[str, KnownPage]` (D-008, D-044), `subcmd → manparse` (D-002).
2. Docstrings: ok. Every module states one responsibility; public items carry Pre/Post/Raises where DITS gives them.
3. Only `LevaError` crosses boundaries: finding F-2 (fixed). Wrapped with `from exc`: `sources` `SystemInfo.detect`
   (`OSError`, `TimeoutExpired`, decode errors), `run_manpath` (`OSError`, `TimeoutExpired`, non-zero exit ->
   `IngestError`), `ProbeRunner.run` (`OSError` of temp dir/captures after F-2, `TimeoutExpired` ->
   `IngestError`); `manparse` `MandocRenderer.render` (`OSError`, `TimeoutExpired`, non-zero exit, empty page ->
   `ManRenderError`) and `read_man_source` (`OSError`). `subcmd` and the pure parsers never raise; `ValueError`
   is used only for programmer errors (invalid `name_hint`, unknown help profile, invariants, relative probe argv).
4. No global mutable state, injected env: ok (Grep for `os.environ|getenv|expanduser|Path.home|datetime|time.time|monotonic|sleep(` over `src/leva` → no match).
5. Small functions, no duplication, naming: finding F-1 (name rule three times, fixed) and F-3. C901 passes.
6. Tests meaningful and deterministic: finding F-4 (flaky clipboard test) and the F-1 mirror-property test
   (replaced by insertion/alphabet properties). TEST-STRATEGY §3 edge cases covered: sources: symlinks, missing
   and unreadable dirs, non-executables, names `[`/`[[`, duplicates across dirs (`test_sources_executables`,
   `test_sources_manpages`), probe timeout, process-group kill, output cap, missing/empty output
   (`test_sources_probe`); manparse: overstrike/backspace and `col -bx` output, stub pages and redirect targets,
   empty and >1 MB pages, headingless pages, NAME with several names or no dash, 10 golden fixtures plus
   Hypothesis on arbitrary text (`test_manparse_*`, `test_mandoc_renderer`); subcmd: hyphen pages (`git-commit`
   vs `ssh-keygen`), section lists (launchctl/diskutil-like layouts, target specifiers, camelCase verbs, prose
   terms, parent name), three help profiles with tab and alias fixtures, merge priority (`test_subcmd`). No
   `time.sleep`; subprocess tests use fake scripts and explicit timeouts.
7. Coverage: ok, all packages 100.0% (manparse ≥90, sources/subcmd ≥85, overall 100.0%).
8. No `Any`, no unjustified `cast`: ok. The `noqa: ARG002` in `subcmd` and `type: ignore[misc]` in tests carry code and reason; no TODO/FIXME.
9. Layers and arch: ok after the refactor (`sources`, `manparse` import `leva.model`, a lower layer); 3 contracts kept.
10. Docs consistent: ok. R10 edits to T-6.2, T-6.3, T-6.4 (facts from D-040, D-043, D-044 that the tasks lacked).

## Findings

- **F-1** `leva.model._types._is_name`, `sources/_names.is_entry_name`, `manparse/_name.is_name`: identical bodies.
- **F-2** `sources/_probe.py` `ProbeRunner.run`: an `OSError` from the temp dir, `mkdir`, or reading captures escaped unwrapped.
- **F-3** `manparse/_sections.py` `ParsedMan.summary`: line-break check missed `\x85` and `U+2028` (stricter in `BuiltinDoc`) and was two overlapping checks.
- **F-4** `tests/unit/test_clipboard.py` `capture_to_file`: 2 s default timeout around a fake script, flaky under load.
- **F-5** `subcmd/_section_list.py` `SectionListExtractor.extract`: the intro prose of a `SUBCOMMANDS` section became subcommands (base-indent prose with two spaces after a full stop parses as an inline term, D-043). `merge_subcommands` is a union by name, so curated content would never remove them and the app would list `launchctl manages`. Real data: launchctl 23 names with `launchctl`, `fundamental`, `manages` as noise; ktrace 18 with `ktrace`, `logical`; tailspin 10 with `tailspin`, `logical`.

Kept on purpose:

- `ProbeRunner` does not kill a background grandchild of a probe that exits normally (curated probes do not daemonize).
- D-044: `a | b` alternation (`bootout`, `disable`, `unload` are missed) is not expanded because the same syntax lists argument alternatives (`kill signal-name | signal-number`, `config system | user`); `info[rmation]` is dropped; less(1) `COMMANDS` keys may yield one-letter names.
- launchctl's `LEGACY SUBCOMMANDS` section (`list`, `load`, `start`, `stop`, ...) is not scanned: the heading rule is a full match and only that page uses the heading on this Mac; curated content covers it.
- When a term wraps, its tail lands in the description, so `debug`'s summary starts with option text and `bootstrap`'s with `service-target` (D-043 layout heuristic).

## Fixes

- **F-1** Public `leva.model.is_name` (D-033 amendment); `sources/_names.py` is deleted. Tests moved to `tests/unit/test_model.py`, where the property test now inserts a whitespace character at a drawn position (must be rejected) and draws non-whitespace text (must be accepted) instead of re-implementing the body.
- **F-2** `run` wraps `OSError` as `IngestError("probe failed: <name>")` via `_capture`; test `test_unusable_temp_dir_raises_ingest_error`.
- **F-3** One check `"".join(summary.splitlines()) != summary`; two new cases.
- **F-4** `capture_to_file` uses `timeout=10.0`.
- **F-5** `_subcommands` skips a term whose first token is `parent` or that contains a sentence end (`[A-Za-z0-9)\]][.!?](?:\s|$)`; `[tool arg0 ...]` and `a.b [arg]` do not match); `noqa: ARG002` on `parent` removed. Unit tests for parent, prose terms with a kept sibling, and kept forms. D-044 amendment. Live test `test_intro_prose_is_not_extracted_as_subcommands` pins launchctl, ktrace, tailspin.

## Live results (this Mac, macOS 27.2.1 arm64)

`/usr/bin`: 934 executables; default bin dirs: 1692. man1 under `/usr/share/man`: 1174 first-per-name pages, 0 render failures (bound 2%), all parsed. after F-5: launchctl 20 names (was 23), ktrace 16 (was 18), tailspin 8 (was 10), diskutil 34 including `list` and `eraseDisk`; none contains the parent name or the prose words.

## Commands run

- `make check` (baseline) -> green, 801 passed; after the F-1..F-4 fixes -> green, 810 passed.
- After F-5 and the test changes: `uv run ruff format .` -> 67 files unchanged; `make check` -> green, 820 passed, coverage 100% in every package, gate passed, 3 contracts kept.
- `uv run pytest tests/unit/test_subcmd.py -q` -> 62 passed; `uv run pytest tests/unit/test_model.py -q` -> 192 passed.
- `uv run pytest -m macos_live tests/live/test_sources_live.py tests/live/test_subcmd_live.py -q` -> 10 passed.
- `make py311`: not run (permission); 3.11 compatibility checked by reading.

## Open items

None.
