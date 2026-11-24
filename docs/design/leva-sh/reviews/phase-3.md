# Phase 3 review

- Date: 2026-11-24 · Scope: T-3.1, T-3.2 · Reviewer: ralph loop (executor, then Opus review round 1: F-5, F-6)

## Scope

`leva.content` (`_schema`, `_policy`, `_validate`, `_yaml_provider`, `_tldr_provider`, `_version`), the first curated
file `commands/ls.yaml`, `ATTRIBUTION.md`, `tests/unit/test_content_{schema,policy,validate,providers}.py`,
`tests/integration/test_content_real.py`, `tests/fixtures/{content,tldr}/**`, DECISIONS D-045/D-046, PLAN T-3.1/T-3.2.
Checked against PLAN §4 RC, DITS §8, ADR-0004, TEST-STRATEGY (content row, §3 "Contenuto"), D-009, D-010, D-016, D-017,
D-030, D-033, D-034.

## Checked items

Baseline before changes: `make check` green, 1181 passed, every coverage gate ok (content 100%), 3 contracts kept.

1. Public API matches DITS + DECISIONS: ok. Deviations are recorded in D-045: `help_probe: HelpProbe | None` (not
   `tuple[str, ...] | None`), `ExampleSpec.danger` and `to_example`, `TldrPage.to_examples`, read-only `VerifySpec.bind`,
   `EXEC_DENYLIST`/`is_destructive` public, `simple_commands` private (`_policy`). ARCHITECTURE content row (provides
   `ContentProvider`, `CuratedYamlProvider`, `TldrSnapshotProvider`, `ContentRecord`; depends on `model`,
   `placeholders`) is still true.
2. Docstrings: ok. Every module states one responsibility; public items carry Pre/Post/Raises.
3. Only `LevaError` crosses the boundary: finding F-1 and F-2 (fixed). Wrapped with `from exc`: file read
   (`OSError`, `UnicodeDecodeError`), `yaml.YAMLError`, JSON `ValueError`/`RecursionError`, `re.error`, `shlex`
   `ValueError`, `importlib.resources` errors. `ValueError` remains only for programmer errors (dataclass invariants).
4. No global mutable state, env, clock or path access outside `default_root()` (a pure function of `__file__`): ok.
5. Small functions, naming: ok (C901 passes). The validator's `_At`/`_Fields` helpers carry the repeated path logic;
   no duplicated rule bodies. `HELP_PROFILES` is the one deliberate copy (layers), pinned by a test.
6. Tests: meaningful and deterministic (no sleeps, `tmp_path`, `chmod` restored in `finally`). Every PLAN T-3.1 rule has a
   negative test with the full `file:field: reason` message; unbound exec placeholder, `kind` ≠ command, unknown keys at
   every level (incl. non-`str` keys), YAML `|` trailing newline, `min_macos` pattern, denylist on cmd and setup with
   absolute and wrapped forms, static/skip with denylisted commands. Hypothesis properties cover top-level, example and
   verify replacement (F-1 extended them with over-long ints and non-string keys). Providers: duplicate keys (also
   after a merge key), sorted order, all-or-nothing, cross-file ids, `.yml` rejected, tldr exact keys / platform =
   stem / osx replaces common / invalid examples dropped with a warning / missing snapshot empty; `content_version`
   recipe test plus one sensitivity test per input.
7. Coverage: ok, content 100.0% (gate 90%), overall 100.0%.
8. No `Any` in public APIs, no `cast`: ok. `Any` appears only in the private `_StrictLoader.construct_mapping`
   override (signature dictated by PyYAML). No TODO/FIXME.
9. Layers and arch: ok. `content` imports `model`, `placeholders`, stdlib and `yaml` only; 3 contracts kept.
10. Docs consistent: ok after the D-045/D-046 amendments and the R10 edits below.

Brief checks:

- **Validation completeness**: every rule of PLAN T-3.1 Steps is implemented and has a negative test.
- **Adversarial inputs** (scratch script, not committed): `float('nan')`/tuple keys, nested lists in `bind`, `nan` and
  huge `expect_exit`, huge `mode`, huge `schema`, YAML with 5001-digit ints, `2024-13-45`, `25:00:00`, 100 000
  nested `[`, lone-surrogate and NUL JSON strings. Escapes found: F-1, F-2. Left alone: lone surrogates (limitation).
- **D-030**: false positives checked (`man rm`, `which rm`, `echo rm`, `grep -r rm .`, `ls -lrt`, `echo 'rm -rf /'`,
  `dd if=x`) and false negatives (`rm -rf`, `sudo rm`, `find -delete`, `find -exec rm`, `xargs rm`, `git reset --hard`,
  `diskutil eraseDisk`, `dd of=`, `git push origin +main`). `echo rm`, `grep -r rm .`, `ls -lrt` had no test; added.
  Gaps recorded as known limitations in D-045 (see below).
- **D-016**: exactly 47 names, equal to the D-016 list (test); applied to exec `cmd` and `setup` words, also
  `/usr/bin/curl`, `sudo ls`, `env FOO=1 ssh host`, a pipe into `pbcopy`; static and skip examples pass.
- **TEST-STRATEGY §3**: "exec with an unbound placeholder → error" is satisfied (`missing placeholder`). "Esempio
  distruttivo mai in exec" is satisfied by D-016 (privileged and system commands) + D-030 (`danger`) + the sandbox (T-7.3);
  exec of `rm` on a fixture created by `setup` stays allowed. Recorded in D-045 (no behaviour change).
- **Providers**: strict YAML, sorted order, all-or-nothing, `.yml` rejected, `content_version` recipe,
  `attribution_text` via `importlib.resources`: ok.
- **`ls.yaml`**: CB compliant: summary 81 characters, explain 4 sentences, 7 intents, 8 examples with `verify` (5 exec,
  3 static), 4 related. Claims checked against `mandoc -T ascii /usr/share/man/man1/ls.1 | col -bx`: `-G` and
  `--color=when` exist, `-@` and `-O` apply to long (`-l`) output, `-1` is the default when not a terminal. Wording is
  original. The exec examples use fixtures in `d/`, no dates, sizes or colours (the `ls -l` example checks the `total` line and one entry line, F-6).
  The example commands were not run (R8).
- **Layering**: see item 9; the `HELP_PROFILES` equality test is in `test_content_schema.py`.
- **Docs**: DITS §8 is Italian design text and keeps its original signatures; the deviations live in D-045 (binding
  order: DECISIONS > design docs). CLAUDE.md content rules agree with the code; no CLAUDE.md change needed.

## Findings

- **F-1** (medium) `_validate.py`: `repr` of a YAML integer with more than 4300 digits (`unknown key`, `unsupported
  schema`, `unknown placeholder`, and `str(key)` in the path of a `bind` key) raised `ValueError`; a non-string `bind` key
  was reported as `bind.7` only by accident of `str`.
- **F-2** (medium) `_yaml_provider.py` `_parse`: only `yaml.YAMLError` was wrapped, so an impossible date
  (`2024-13-45`), an integer over 4300 digits and deeply nested flow sequences (`RecursionError`) escaped
  `CuratedYamlProvider.load` as raw exceptions.
- **F-3** (low, test gap) `test_content_policy.py`: no negative case for `echo rm`, `grep -r rm .`, `ls -lrt`.
- **F-4** (low, docs) D-045 had no entry for the TEST-STRATEGY "distruttivo mai in exec" case and the destructive-rule
  gaps (`mv`/`cp`/`>` overwrite, `shred`, `truncate`, `git checkout .`, ...).
- **F-5** (medium, Opus review) `_policy.py` `_expand`: wrappers and `find -exec` clauses were unwrapped recursively,
  so a chain of about 1000 wrappers (`nohup nohup ... rm x`, `sudo sudo ...`, `find . -exec -exec ...`) raised
  `RecursionError` out of `simple_commands`, `is_destructive` and `validate_command`.
- **F-6** (low, Opus review) `ls.yaml` `ls-long`: `stdout_contains: [total, a]` was vacuous for `a` (a substring of
  `total`), the same defect class T-3.2's review fixed in `ls-one-per-line`.

Kept on purpose (all recorded in DECISIONS):

- Lone surrogates in JSON or YAML escapes pass validation (D-046 limitation); vendored data has none.
- `command -v rm` is a false positive and `git clean -fn` a conservative one (D-045).
- `content_version` hashes `tldr/SOURCE.json`, not the JSONL (PLAN T-3.2): R10 below tells T-7.2 to change SOURCE.json
  whenever the JSONL output changes.

## Fixes

- **F-1** `_show(value)` returns `repr(value)` or `<integer too large to show>`; `_At.key` and the three messages use it.
  Tests `test_over_long_integers_are_reported_not_raised`, `test_non_string_bind_keys_are_reported_not_raised`; the
  Hypothesis `JSON_LIKE` strategy gets over-long ints (as values and keys) and int keys. D-045 amendment.
- **F-2** `_parse` also catches `ValueError` and `RecursionError` → `<label>: invalid YAML`. Three new cases in
  `test_curated_reports_yaml_problems` (impossible date, 5000-digit int, 100 000 nested `[`). D-046 amendment.
- **F-3** Three cases added to `test_non_destructive_commands`.
- **F-4** D-045 amendments (exec reading, known limitations).
- **F-5** `_expand` is an explicit depth-first stack (same order as before). Test
  `test_simple_commands_unwraps_chains_deeper_than_the_recursion_limit` (2000-deep `nohup`, `sudo`, `find -exec`);
  D-045 amendment. The F-1 tests now assert the exact messages with the stand-in text (they only checked prefixes).
- **F-6** `ls-long` verifies with `stdout_regex: '^total [0-9]+\n[^\n]* a\n$'` (one entry line ending in ` a`; holds
  with an `@` xattr marker and with `re.search`, `match` or `fullmatch`). Checked on synthetic text only; the command
  was not run (R8).

R10 edits to later PLAN tasks (facts verified against the merged code):

- T-6.1: `content_version(default_root())` named.
- T-6.4: providers `CuratedYamlProvider(default_root())`, `TldrSnapshotProvider(default_root())`; `spec.to_example()`
  keeps `danger`; `help_probe.args`/`.profile`; tldr via `TldrPage.to_examples()` (`<name>-tldr-<n>`, source `tldr`,
  verified `none`).
- T-7.2: exact JSONL line format and rejection rules; `content_version` hashes `SOURCE.json` only, so `SOURCE.json` must
  change with the JSONL output.
- T-7.3: `VerifySpec` field names, `files_exist` relative, `bind` already exact after validation.
- T-7.4: reuse `simple_commands` (export it from the package root) instead of a second tokenizer.
- T-9.3: "content loads" drains both providers on `default_root()`.

## Commands run

- `make check` (baseline) → green, 1181 passed, coverage 100%.
- `uv run pytest tests/unit/test_content_validate.py tests/unit/test_content_providers.py -q` → failed before the fixes
  (F-1, F-2 tests), 254 passed after.
- Scratch script with adversarial inputs (outside the repo, not committed): escapes found before the fixes, none after.
- `uv run ruff format .`; `make check` → green, 1189 passed, coverage 100% in every package, gate passed, 3 contracts kept.
- Opus review: second adversarial scratch script (not committed: deep wrapper chains, date/tuple/bytes keys, `nan`
  and `bool` exit codes, nested `bind`, huge and deep regexes, lone operators, YAML anchors/`!!set`/`!!omap`/BOM,
  tldr non-string fields and over-long ints) found F-5 only; `make check` green after F-5/F-6 (1192 passed, coverage 100%).
- `make py311`: not run (permission); 3.11 compatibility checked by reading (no `type` statements, PEP 695,
  `itertools.batched` or 3.12-only stdlib in `leva.content`).

## Open items

None.
