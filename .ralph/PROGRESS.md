# Ralph loop progress

## 2026-11-20T23:41:18Z T-0.1 Repo constitution: CLAUDE.md, DECISIONS.md, gitignore, design-system snapshot — DONE
- Wrote `CLAUDE.md` (10 `##` sections: docs map, language, architecture + D-002 layers, coding, testing, TUI, content, safety, commands, git).
- Wrote `docs/design/leva-sh/DECISIONS.md`: D-001..D-024 copied verbatim from PLAN Appendix A (checked line by line with a python3 one-liner); new entries go under "Later decisions" from D-025.
- `.gitignore`: added `.venv-*/`, `.cache/`, `.coverage*`, `coverage.json`, `htmlcov/`, `.hypothesis/`, `spikes/out/`.
- `docs/design/design-system-snapshot.md` was already committed; compared with the external file via the Read tool (identical, 118 lines). Bash `diff` on the external path is denied by permissions in this loop, so later checks of that file must use Read.
- Permission notes for next iterations: Bash commands that touch paths outside the repo, and commands not in `scripts/ralph.sh` ALLOWED_TOOLS (e.g. `git config`, `git -C`), are denied; prefer one allowed command per call. The working dir is the repo root, so plain relative paths work.
- `make check` does not exist yet; it arrives with T-0.2/T-0.3.

## 2026-11-21T00:10:00Z T-0.2 Python project scaffold — DONE
- pyproject (hatchling, PEP 639 license), `.python-version` 3.13, `uv.lock`, Makefile (check/lint/fmt/type/arch/test/cov/live/verify/py311), 17 D-002 packages (docstring only), `py.typed`, `tools/__init__.py`, `tests/unit/test_package.py` (21 tests).
- Resolved: textual 8.2.8, pytest 8.4.2 (syrupy 4.8.0 requires pytest<9, confirmed), pytest-asyncio 1.5.0, ruff 0.17.6, mypy 2.4.1, import-linter 2.17.
- Ruff 0.17 formats Python blocks inside Markdown: added `extend-exclude = ["*.md"]` so design docs are never touched.
- Added ruff `isort.required-imports = from __future__ import annotations` (enforces CLAUDE.md; docstring-only modules exempt).
- tui forbidden contract uses `allow_indirect_imports = true` (tui reaches repo/search via library). All 3 contracts KEPT.
- `make check` has no coverage gate yet (T-0.3 adds `tools/coverage_gate.py`). `make verify` calls `uv run leva --rebuild`, which exists only after T-9.1; T-7.4 owns the target.
- No Python 3.11 installed locally; `make py311` will make uv download it (T-11.x). Heredoc `cat >>` is denied in this loop; use Edit for PROGRESS.md.

## 2026-11-21T03:01:04Z T-0.3 Test harness and architecture fitness functions — DONE
- `tests/conftest.py`: autouse `clean_env` (LEVA_HOME=tmp_path, HOME=tmp_path/home, pinned locale/TZ/width), Hypothesis profile `leva`, `tryfirst` hook adding integration/tui/macos_live markers by top-level dir; `pytest_plugins = ("pytester",)`.
- `tests/arch/rules.py`: pure AST checker (`find_violations`, `source_modules`, `Restriction`, `PrivateImport`, `RULES`); qualified-name matching, superset scope recorded as D-025. `tools/coverage_gate.py` (D-026) is now the last step of `make check`/`make cov`; exits 0/1/2.
- Marker test runs the real conftest + real pyproject pytest options in pytester (in-process, `-p no:textual-snapshot`: that plugin's per-process temp dir breaks under nested sessions; `timeout` excluded so the inner SIGALRM does not cancel the outer one).
- pyproject: targeted filterwarnings ignore for pytest-socket's pre-raise UserWarning; ruff `known-first-party = ["tests", "tools"]` (repo root is not a ruff src root).
- Tests import helpers as `from tests.support.fake_bin import fake_bin` / `from tests.arch.rules import ...` (`tests` is a namespace package; `pythonpath = ["."]`). Test code also passes `mypy --explicit-package-bases tests/...` (not gated).
- `tests/` own `tmp_path` contains `home/` (from clean_env): tests that list `tmp_path` must account for it.
