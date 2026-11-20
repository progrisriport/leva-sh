# PRD — Leva

- Progetto: Leva (`leva-sh`, comando `leva`) · Data: 2026-11-20 · Versione: 0.1 · Stato: reviewed (in attesa di approvazione umana)
- Doc collegati: [ARCHITECTURE](ARCHITECTURE.md) · [DESIGN-PATTERNS](DESIGN-PATTERNS.md) · [DESIGN-IN-THE-SMALL](DESIGN-IN-THE-SMALL.md) · [TEST-STRATEGY](TEST-STRATEGY.md) · [DESIGN-STATUS](DESIGN-STATUS.md) · ADR: [0001](ADR/ADR-0001-stack.md) [0002](ADR/ADR-0002-ingest-man-mandoc.md) [0003](ADR/ADR-0003-storage-sqlite-fts5.md) [0004](ADR/ADR-0004-curated-content-verifiable.md) [0005](ADR/ADR-0005-tui-textual-design-system.md) [0006](ADR/ADR-0006-distribuzione.md)

## 1. Problema

Chi lavora in shell su macOS dimentica spesso nome, opzioni o differenze (BSD vs GNU, zsh vs bash) di un comando. Le alternative sono lente o inadatte: `man` e' denso e poco orientato agli esempi, `tldr` copre pochi comandi senza il contesto macOS, ss64.com/mac e i cheat sheet richiedono un browser e non riflettono la versione di macOS installata. Nessun tool esistente offre un'enciclopedia offline, coerente con il sistema dell'utente, navigabile e con esempi affidabili.

## 2. Obiettivi e non-obiettivi

**Obiettivi (v1 — Enciclopedia)**
1. Copertura di tutti i comandi utilizzabili sul Mac dell'utente (eseguibili, builtin, man page) in un indice offline.
2. Per ~150-200 comandi comuni: spiegazione chiara, esempi copiabili **verificati automaticamente**, note BSD/GNU e zsh/bash, correlati.
3. Trovare un comando in meno di 5 secondi, anche senza ricordarne il nome.
4. Interfaccia in split, rapida e sobria, conforme al design system Flosh.
5. Filosofia "less effort, more thought": zero configurazione, zero rete.

**Non-obiettivi (v1)**: ricette orientate al compito (v1.x), tutorial/percorsi (v2), esecuzione di comandi dall'app, integrazione con la shell (history, widget zsh), Linux/Windows, sincronizzazione cloud, telemetria, preferiti/cronologia persistente, traduzioni dei contenuti, editor di contenuto in-app.

## 3. Utenti e attori

- **Utente primario**: sviluppatore/power user macOS che lavora in terminale e usa Leva in un pannello affiancato.
- **Utente curioso/apprendista**: impara la shell consultando e copiando esempi.
- **Autore** (maintainer): scrive e verifica contenuto curato.
- **Sistema**: macOS (man page, eseguibili, `pbcopy`).

## 4. User stories

- US-1: Come utente, scrivo `leva tar` e vedo subito cosa fa, gli esempi principali e le differenze BSD/GNU.
- US-2: Come utente, scrivo "extract archive" e trovo `tar`, `unzip`, `ditto`.
- US-3: Come utente, clicco (o premo `c`) su un esempio e lo trovo negli appunti con conferma verde.
- US-4: Come utente, vedo i placeholder evidenziati cosi' so cosa sostituire.
- US-5: Come utente, esploro i sottocomandi di `git`, `brew`, `diskutil`, `defaults`, `launchctl`.
- US-6: Come utente, leggo la man page completa per sezioni senza uscire da Leva.
- US-7: Come utente, passo a un comando correlato e torno indietro.
- US-8: Come utente, al primo avvio vedo l'avanzamento della costruzione dell'indice e poi uso Leva offline.
- US-9: Come utente, uso Leva in un pannello stretto senza perdere funzioni.
- US-10: Come autore, aggiungo un comando in YAML e un comando di verifica mi dice se gli esempi funzionano su macOS.
- US-11: Come utente, dopo un aggiornamento di macOS ricevo un avviso per aggiornare l'indice.

## 5. Requisiti funzionali

| ID | Requisito | Priorita' |
|---|---|---|
| FR-1 | Al primo avvio Leva costruisce l'indice locale dalle man page con schermata di avanzamento, poi funziona offline | Must |
| FR-2 | Copertura: eseguibili in `/bin /sbin /usr/bin /usr/sbin` e man page sez. 1/8 da `manpath`, `/opt/homebrew/share/man`, `/usr/local/share/man` e percorsi extra di config; entry anche per eseguibili senza man page | Must |
| FR-3 | Builtin zsh (103) e bash come entry (`kind=builtin`) con descrizione dalle relative man page | Must |
| FR-4 | Scheda comando: nome, sezione, origine, summary, spiegazione, note, esempi, sottocomandi, correlati | Must |
| FR-5 | Vista del manuale completo con navigazione per sezioni | Must |
| FR-6 | Layer curato YAML: spiegazione, `intents`, esempi con placeholder, note BSD-GNU/zsh-bash/macOS/safety, correlati | Must |
| FR-7 | Esempi base da tldr-pages (snapshot vendorizzato) con attribuzione visibile | Must |
| FR-8 | Sottocomandi navigabili (pagine `<cmd>-<sub>`, sezioni COMMANDS delle man page, YAML, help probe in allowlist) per almeno git, brew, diskutil, defaults, launchctl | Must |
| FR-9 | Ricerca fuzzy sui nomi + full-text su intents, summary e corpo; ranking deterministico | Must |
| FR-10 | Navigazione completa da tastiera (vedi tabella binding in DESIGN-IN-THE-SMALL) | Must |
| FR-11 | Navigazione con mouse: righe, tab, esempi, sottocomandi, breadcrumb, scroll | Must |
| FR-12 | Click o `c` su un esempio copia con `pbcopy` e mostra conferma verde `copied: ...`; errore rosso breve se fallisce | Must |
| FR-13 | `leva <query>`: match esatto apre la scheda, altrimenti apre la ricerca con query precompilata | Must |
| FR-14 | Placeholder `{{x}}` evidenziati nell'accento; la copia li "sbracketta" (`x`) | Must |
| FR-15 | Navigazione verso comandi correlati con cronologia indietro/avanti | Should |
| FR-16 | Rilevamento indice obsoleto (cambio Leva/schema: rebuild automatico; cambio di sistema: hint e `r`/`leva --rebuild`) | Must |
| FR-17 | About/attribuzioni (`leva --about`, tasto `a`) con tldr-pages e licenze | Must |
| FR-18 | Strumento `leva-verify` e suite di test che verificano gli esempi curati su macOS | Must |
| FR-19 | Layout responsivo per split: >= 100 colonne due pannelli, 60-99 pannello singolo, < 60 messaggio | Should |
| FR-20 | `leva doctor`: diagnostica (mandoc, FTS5, pbcopy, indice, versioni) | Should |

## 6. Requisiti non-funzionali

| ID | Requisito |
|---|---|
| NFR-1 | Prestazioni di avvio: con indice presente, primo frame <= 300 ms (Apple Silicon, mediana) |
| NFR-2 | Latenza di ricerca: p95 < 50 ms per battitura su ~3000 voci |
| NFR-3 | Primo avvio: build dell'indice <= 30 s su Apple Silicon con progress continuo (soglia da validare in spike S-2) |
| NFR-4 | Offline e privacy: nessun accesso di rete a runtime, nessuna telemetria, nessun contenuto utente inviato |
| NFR-5 | Compatibilita': macOS >= 13 (arm64 e x86_64), Python >= 3.11, terminali Terminal.app, iTerm2, Ghostty |
| NFR-6 | Conformita' al design system Flosh: palette, bordi box-drawing, header+footer sempre, sfondo trasparente, no emoji, un solo accento (ADR-0005) |
| NFR-7 | **Mantenibilita'**: ogni modulo ha una responsabilita' singola dichiarata; errori tipizzati; naming coerente; mypy strict e ruff in CI; contenuto dichiarativo separato dal codice |
| NFR-8 | **Riproducibilita'**: dipendenze pinnate (`uv.lock`, `.python-version`); build dell'indice deterministica (`index_digest`); test con ambiente isolato (`LEVA_HOME`, `HOME`, `TZ`, `LC_ALL`); snapshot tldr pinnato con hash |
| NFR-9 | **Modularita'**: grafo di dipendenze aciclico imposto da import-linter; interfacce esplicite (Protocol); ogni modulo comprensibile da solo |
| NFR-10 | **Estensibilita'**: aggiungere sorgenti, extractor, renderer, tipi di contenuto, tab o azioni senza modificare i moduli esistenti, salvo la registrazione documentata in `tui`/`cli` |
| NFR-11 | Sicurezza di esecuzione: Leva esegue solo `mandoc`, `manpath`, `sw_vers`, `pbcopy` e sonde help in allowlist (read-only, timeout, env minimo); mai comandi arbitrari |
| NFR-12 | Robustezza: una man page illeggibile non interrompe l'ingest; build atomica; l'indice precedente non si corrompe mai |
| NFR-13 | Accessibilita': nessuna informazione solo a colore (la conferma e' anche testuale); tutte le azioni da mouse hanno equivalente da tastiera |
| NFR-14 | Conformita' licenze: nessuna man page di terzi distribuita; attribuzione tldr inclusa e verificata da test |
| NFR-15 | Dimensione: indice <= 100 MB, wheel <= 15 MB |

## 7. Success metrics

| Metrica | Obiettivo v1.0 |
|---|---|
| Copertura eseguibili nelle 4 directory di sistema con entry | 100% |
| Entry con summary (dove esiste man page) | >= 95% |
| Comandi curati | >= 150 (minimo accettabile al rilascio: 100) |
| Esempi curati verificati `exec` o `static` | >= 85%; `exec` >= 60% |
| Gold set di 50 query "ho dimenticato il comando": atteso nei primi 3 | >= 90% |
| Tempo da `leva <cmd>` alla copia di un esempio | <= 3 interazioni |
| Primo avvio | <= 30 s; avvii successivi <= 300 ms |
| Uso personale (dogfooding) | uso quotidiano per 2 settimane senza consultare altre fonti per i comandi coperti |

## 8. Scope e out-of-scope

**In scope v1.0**: livello 1 (ingest man locale), livello 2 (YAML curato + tldr), ricerca, scheda, manuale, sottocomandi, copia, `leva <query>`, rebuild, doctor, About, verifica esempi, distribuzione PyPI + brew tap.

**Roadmap (non in v1.0)**: v1.x ricette orientate al compito (es. "scrivere, compilare ed eseguire un programma C con clang", "spostare cartelle") come `kind: recipe` con tab dedicata; v2 tutorial/percorsi (`kind: path`). Il design riserva `kind` nel YAML, la tabella `content_item` e punti di estensione per tab/azioni.

**Out-of-scope**: vedi non-obiettivi (esecuzione, integrazione shell, cross-platform, telemetria).

## 9. Rischi (sintesi, dettagli in ANALYSIS)

| Rischio | Score | Mitigazione |
|---|---|---|
| Esempi errati/obsoleti (R-5) | 15 | `leva-verify` su runner macOS, gate di release |
| Ingest lento (R-1) | 12 | Spike S-2, pool, piano B lazy |
| Parsing fragile (R-3) | 12 | Degradazione elegante, extractor pluggabili, golden test |
| Costo autoria curata (R-6) | 12 | Rilascio incrementale, pipeline di verifica |
| Sfondo trasparente Textual (R-4) | 9 | Spike S-1, fallback `$surface` neutro |
| Licenza tldr (R-7) | 8 | Verifica `LICENSE.md`, ATTRIBUTION |

## 10. Riferimenti agli ADR

- [ADR-0001 Stack](ADR/ADR-0001-stack.md): Python 3.11+, Textual 8.x, SQLite FTS5, rapidfuzz, PyYAML, uv, hatchling.
- [ADR-0002 Ingest man/mandoc](ADR/ADR-0002-ingest-man-mandoc.md)
- [ADR-0003 Storage SQLite+FTS5](ADR/ADR-0003-storage-sqlite-fts5.md)
- [ADR-0004 Contenuto curato verificabile](ADR/ADR-0004-curated-content-verifiable.md)
- [ADR-0005 TUI Textual e design system](ADR/ADR-0005-tui-textual-design-system.md)
- [ADR-0006 Distribuzione](ADR/ADR-0006-distribuzione.md)

## 11. Pianificazione ad alto livello (suggerita, non vincolante)

0. Aggiornare il design system (NB-2) e rieseguire gli spike S-1, S-2, S-3.
1. Foglie + store/repo/search su fixture (TDD).
2. Ingest reale + schermata di avanzamento.
3. TUI: ricerca, scheda, copia.
4. Contenuto curato: primi 30 comandi + `leva-verify`; poi ampliamento a 150.
5. Release PyPI + tap.
