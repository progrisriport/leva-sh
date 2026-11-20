# ADR-0003 — Storage: indice SQLite unico, generato, con FTS5

- Progetto: Leva · Data: 2026-11-20 · Versione: 0.1 · Stato doc: reviewed
- Stato ADR: Accepted
- Doc collegati: [PRD](../PRD.md) · [ARCHITECTURE](../ARCHITECTURE.md) · [DESIGN-IN-THE-SMALL](../DESIGN-IN-THE-SMALL.md) · [ADR-0002](ADR-0002-ingest-man-mandoc.md)

## Contesto

Serve un archivio unico interrogabile in pochi millisecondi che unisca: man page locali (dipendenti dalla macchina), contenuto curato e snapshot tldr (distribuiti col pacchetto). Deve essere ricostruibile da zero (cache, non fonte di verita') e predisposto per i contenuti v1.x (ricette) e v2 (tutorial).

## Decisione

- Un unico file `~/Library/Application Support/leva/index.db` (override: `LEVA_HOME`), **interamente rigenerabile**: cancellarlo e' sempre sicuro.
- Schema versionato con `PRAGMA user_version` e migrazioni numerate (`0001_init.sql`, ...). Poiche' l'indice e' una cache, la migrazione standard e' "rebuild"; le migrazioni SQL esistono solo per i casi in cui un rebuild sarebbe troppo costoso (non previsto in v1).
- Tabelle principali: `meta`, `entry` (con flag `curated` e colonna `explain`), `alias`, `doc_section`, `subcommand`, `example`, `note`, `related`, `intent`, `content_item` (generica, per ricette/tutorial futuri) e tabelle virtuali FTS5 `search_fts` (nome, intents, summary, corpo).
- Ricerca a due stadi: (1) fuzzy `rapidfuzz` su elenco nomi/alias/intents caricato in memoria all'avvio (~3k righe, < 5 ms per query); (2) FTS5 `bm25` con pesi (nome > intents > summary > corpo) per query testuali. `Searcher` fonde i punteggi.
- Connessione in sola lettura (`mode=ro`) a runtime; solo `IndexWriter` scrive.
- Esempi tldr e curati stanno nella stessa tabella `example` con colonna `source` (`curated|tldr`) cosi' la UI li tratta uniformemente e puo' mostrare l'attribuzione.
- Determinismo: inserimento in ordine totale, nessun timestamp nelle tabelle di contenuto (solo in `meta`); `index_digest()` = hash del contenuto, usato nei test.

## Conseguenze

- Aggiungere un tipo di contenuto (ricette) = nuova migrazione/tabella + nuovo provider, senza modificare `entry`.
- Dimensione attesa 30-60 MB (corpo delle man page). Se FTS5 non e' disponibile nel `sqlite3` di Python, `leva doctor` lo segnala e Leva degrada a ricerca LIKE solo su nomi/summary.
- Il fuzzy in memoria aumenta l'RSS di pochi MB: accettabile.

## Alternative

- Due DB (curato/pacchetto + sistema/cache) con `ATTACH`: separazione netta ma query piu' complesse e due cicli di vita; scartato, la rigenerazione completa risolve la coerenza.
- JSON/pickle: nessuna FTS, avvio lento; scartato.
- Indice FTS5 `trigram` per fuzzy nel DB: tokenizer piu' pesante e ranking meno controllabile di rapidfuzz; scartato per v1, rivalutabile.
