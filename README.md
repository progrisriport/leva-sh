# Leva

*Less effort, more thought.*

Leva is a terminal TUI for macOS that works as an encyclopedia of shell
commands. It combines curated, searchable command references with examples
and a local index of the man pages already installed on your machine.
Recipes are planned for v1.x and tutorials for v2. Built with Python and
Textual; the CLI command is `leva`.

Leva is a vibecoded app: it is built with AI assistance, with the aim of
sparing us needless effort, like digging through man pages or searching the
web for the right flags, so attention goes to the work that matters.

## Status

In development — not usable yet (no TUI or `leva` command so far).
Last updated 2026-11-24: 24 of 97 planned tasks done.

| Phase | Scope | State |
|---|---|---|
| 0 | Foundations, conventions, spikes | done |
| 1 | Domain types, placeholders, paths, clipboard, config | done |
| 2 | System sources, man page parsing, subcommands | done |
| 3 | Curated content: schema, validation, loaders | in progress (review left) |
| 4 | Index storage (SQLite + FTS5) and repository | planned |
| 5 | Search and library | planned |
| 6 | Ingest (building the index from this Mac) | planned |
| 7 | Example verification and first curated commands | planned |
| 8 | TUI | planned |
| 9 | CLI and `doctor` | planned |
| 10 | Curated content expansion | planned |
| 11 | Performance, robustness, polish | planned |

## Install (planned)

Not available yet. Planned:

```
pipx install leva
```

or via a Homebrew tap.

## License

Leva is dual-licensed:

- Source code: MIT License (see `LICENSE`).
- Curated content (YAML data under `content/`): Creative Commons
  Attribution 4.0 International, CC BY 4.0 (see `LICENSE-CONTENT`).

Third-party attributions are listed in `NOTICE.md`.
