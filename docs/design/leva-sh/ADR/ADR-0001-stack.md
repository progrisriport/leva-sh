# ADR-0001 — Stack tecnologico

- Progetto: Leva (`leva-sh`)
- Data: 2026-11-20 · Versione: 0.1 · Stato doc: reviewed
- Stato ADR: Accepted (stack in larga parte imposto dal brief: Python + Textual)
- Doc collegati: [PRD](../PRD.md) · [ARCHITECTURE](../ARCHITECTURE.md) · [ANALYSIS](../ANALYSIS.md) · [ADR-0002](ADR-0002-ingest-man-mandoc.md) · [ADR-0003](ADR-0003-storage-sqlite-fts5.md) · [ADR-0004](ADR-0004-curated-content-verifiable.md) · [ADR-0005](ADR-0005-tui-textual-design-system.md) · [ADR-0006](ADR-0006-distribuzione.md)

## Contesto

Il brief impone Python + Textual per una TUI macOS. Restano da scegliere: versione di Python, storage/ricerca, fuzzy matching, parsing YAML, gestione dipendenze/build, test. Vincoli: avvio rapido, offline, installabile via PyPI e brew tap, sviluppo rapido ("vibecoded") ma riproducibile.

Fatto rilevante: il Python di sistema su macOS (Xcode CLT) e' vecchio (3.9.x); Leva non puo' contare su di esso. Textual 8.x risulta l'ultima linea stabile (8.2.x, evidenza da Debian tracker/MacPorts; da riconfermare su PyPI al momento del pin).

## Decisione

| Area | Scelta | Note |
|---|---|---|
| Linguaggio | Python `>=3.11` (sviluppo e CI su 3.13) | 3.11 = piu' vecchia versione ancora supportata dalle dipendenze e da Homebrew |
| TUI | Textual `>=8.2,<9` | imposto dal brief; pin esatto nel lockfile |
| Storage/ricerca | SQLite (stdlib `sqlite3`) con FTS5 | vedi ADR-0003; `leva doctor` verifica FTS5 |
| Fuzzy | `rapidfuzz` | veloce, wheel macOS arm64/x86_64, usato solo sui nomi (~3k) |
| Contenuto curato | YAML via `PyYAML` (`safe_load`) + validazione con dataclass e validatori propri | niente pydantic a runtime: meno peso all'import e meno dipendenze |
| Rendering man | `mandoc` di sistema (`/usr/bin/mandoc`, macOS 13+) | vedi ADR-0002 |
| Build backend | `hatchling` | wheel pura Python, include `content/` come package data |
| Gestione env | `uv` (lockfile `uv.lock`, `.python-version`) | ambienti riproducibili e veloci |
| Qualita' | `ruff` (lint+format), `mypy --strict` sul core non-TUI | |
| Test | `pytest`, `pytest-asyncio`, `pytest-textual-snapshot`, `hypothesis` | vedi TEST-STRATEGY |

Dipendenze runtime complessive: `textual`, `rapidfuzz`, `pyyaml` (+ transitive di Textual/rich). Nessuna dipendenza di rete a runtime.

## Alternative considerate

Linguaggio/UI:
1. **Python + Textual (scelta)**: sviluppo rapido, CSS-like, mouse nativo, Pilot per test UI. Costo: avvio ~150-300 ms, Python da installare (mitigato da brew/uv/pipx).
2. Rust + ratatui: avvio istantaneo, binario singolo. Scartata: contraddice il brief e rallenta lo sviluppo "vibecoded".
3. Python + prompt_toolkit/rich (stack del design system PyDF): nessun supporto mouse/layout ricco paragonabile; il brief indica Textual.

Storage/ricerca:
1. **SQLite FTS5 + fuzzy in memoria sui nomi (scelta)**.
2. Whoosh/Tantivy: dipendenze extra, nessun beneficio a questa scala (~3k documenti).
3. Solo ricerca in memoria su JSON: avvio lento con bodies grandi, nessuna ricerca full-text efficiente.

Fuzzy: `rapidfuzz` (scelta) vs `thefuzz` (piu' lento, usa rapidfuzz comunque) vs implementazione propria (manutenzione inutile).

YAML schema: pydantic v2 (valida bene ma import pesante e dipendenza compilata) vs dataclass + validatori propri (scelta; lo schema e' piccolo, errori con percorso `file:campo`).

## Conseguenze

- Distribuzione richiede Python >= 3.11: la formula brew dichiara `python@3.13`; PyPI users usano `uv tool install leva` / `pipx install leva` (ADR-0006).
- Dipendenza da `mandoc` di sistema limita il supporto a macOS >= 13; fallback `man | col -bx` previsto (ADR-0002).
- Tutte le versioni sono pinnate in `uv.lock`; l'aggiornamento di Textual e' un'operazione esplicita guardata dai test snapshot.
- Evidenze consultate: pagina PyPI/Debian/MacPorts di Textual (ricerca web 2026-11-20); da riconfermare all'atto del pin.
