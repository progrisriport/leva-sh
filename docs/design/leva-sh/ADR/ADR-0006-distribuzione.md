# ADR-0006 — Distribuzione: PyPI, brew tap, repo

- Progetto: Leva · Data: 2026-11-20 · Versione: 0.1 · Stato doc: reviewed
- Stato ADR: Accepted
- Doc collegati: [PRD](../PRD.md) · [ARCHITECTURE](../ARCHITECTURE.md) · [ADR-0001](ADR-0001-stack.md)

## Contesto

Brief: pacchetto PyPI `leva` (nome libero al momento del brief, da riverificare prima della prima publish), brew tap personale, repo GitHub `leva-sh` (il nome `leva` e' occupato da pmndrs/leva). Il comando installato e' `leva`.

## Decisione

- Repo `leva-sh`; distribuzione PyPI `leva` (import package `leva`, entry point `leva = leva.cli:main`, `leva-verify` come script di sviluppo in extra `dev`).
- Publish con GitHub Actions + PyPI Trusted Publishing (OIDC), da tag `vX.Y.Z` (SemVer). Build `uv build`; il wheel include `content/**` come package data; nessuna man page inclusa.
- Brew tap personale `homebrew-tap` (repo separato): formula `leva` con `include Language::Python::Virtualenv`, `depends_on "python@3.13"`, `resource` pinnati con hash (generati da script, non a mano), `test do` che esegue `leva --version` e `leva doctor --offline`.
- Percorso consigliato nel README: `uv tool install leva` o `pipx install leva`.
- Versionamento: `leva --version` mostra versione + `content_version` (data snapshot tldr + hash contenuto curato).
- Release checklist automatizzata: lint, test, `leva-verify` su runner macOS, build, publish, aggiornamento formula.

## Conseguenze

- Il progetto resta puro Python (wheel `py3-none-any`): nessuna matrice di build binaria propria.
- Il bump formula e' un passo di CI separato; fallimenti non bloccano PyPI.

## Alternative

- Binario unico (PyInstaller/Nuitka): avvio piu' lento/complessita' di notarizzazione; scartato per v1.
- Solo brew core: richiede popolarita'/review; rinviato.
