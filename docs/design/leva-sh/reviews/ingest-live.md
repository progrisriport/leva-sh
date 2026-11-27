# Live ingest on this Mac (T-6.6)

Numbers from `make live` on 2026-11-27 (`uv run pytest -m macos_live tests/live -o log_cli=true
--log-cli-level=INFO`). The index is built once per session by the `real_index` fixture
(`tests/live/conftest.py`) with the real `manpath` (user `PATH`/`MANPATH`), `mandoc`, the six
default bin dirs and the bundled curated content (only `ls.yaml`; no tldr snapshot yet, so the
subcommand counts are before curated content). Build times vary by about ±0.3 s between runs
(executor run 5.41 s, reviewer runs 4.98 s and 5.03 s); the table holds the last reviewer run.

## Environment

| Item | Value |
|---|---|
| macOS | 27.2.1 (build 26B131), Darwin 27.2.0 |
| Architecture | arm64 (Apple Silicon) |
| Python | 3.13.12 |
| Man dirs (`discover_man_dirs(run_manpath(env))`) | 7 |
| Sections | `1`, `8` (`LevaConfig` defaults) |

## Measured

| Item | Value |
|---|---|
| Executables (unique names) in `/bin`, `/sbin`, `/usr/bin`, `/usr/sbin` | 1264 |
| Entries | 3254 |
| Man pages (`man_pages`) | 2654 |
| Builtins (`stats()`) | 178 |
| Curated entries | 1 |
| Examples / subcommand rows (`stats()`) | 8 / 857 |
| Skipped | 1 |
| Skip reasons | stub target missing: 1 (`vidio2(1)`, its `.so` target under `/System/Library/Filesystems/acfs.fs` is not there) |
| Build seconds (report) | 5.03 |
| Build seconds (wall) | 5.03 |
| Index size | 44.59 MB |
| Man-backed entries (rows with a section) | 2654 |
| Man-backed entries with a blank summary | 104 |
| Summary share | 0.9608 |
| Subcommands of `git` | 153 |
| Subcommands of `diskutil` | 34 |
| Subcommands of `launchctl` | 20 |

## Assertions

| Test | Threshold | Result |
|---|---|---|
| `test_every_system_executable_resolves` | 100% resolve via `get_entry` | pass (0 missing of 1264) |
| `test_man_backed_entries_have_summaries` | share ≥ 0.95 | pass (0.9608) |
| `test_build_is_fast_enough` | ≤ 30 s | pass (5.03 s) |
| `test_index_is_small_enough` | ≤ 100 MB | pass (44.59 MB) |
| `test_subcommand_thresholds[git-20]` | ≥ 20 | pass (153) |
| `test_subcommand_thresholds[diskutil-15]` | ≥ 15 | pass (34) |
| `test_subcommand_thresholds[launchctl-10]` | ≥ 10 | pass (20) |

All other live files (`test_clipboard_live.py`, `test_sources_live.py`, `test_subcmd_live.py`)
pass in the same run: 18 passed.

## Observations

- The summary share has a margin of about 1 point (0.9608 vs 0.95, 104 blank). The blank ones are
  mostly daemons and vendor tools (`BTLEServer(1)`, `Firewall(8)`, `appstored(8)`, `coreaudiod(8)`,
  the `cv*` StorNext tools). Spot checks show malformed NAME sections, not a parser defect:
  `appstored(8)` and `BTLEServer(1)` have only the name in NAME (the description sits in SYNOPSIS
  or nowhere); `assetutil(1)` has `assetutil process asset catalog .car files` without the ` - `
  separator. Recovering these would need a new NAME heuristic in `manparse` (not in scope here);
  watch the share when new man dirs or sections are added.
- Build time (≈5 s) is far below the 30 s budget and consistent with S-2 (render ≈4 s); the hyphen
  subcommand pass needs no optimisation.
- Index size (44.59 MB) is close to the S-3 prototype (41 MB) and well within NFR-15.
