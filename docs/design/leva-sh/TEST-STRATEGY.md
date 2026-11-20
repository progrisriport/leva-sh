# TEST-STRATEGY — Leva

- Progetto: Leva (`leva-sh`) · Data: 2026-11-20 · Versione: 0.1 · Stato: reviewed
- Doc collegati: [PRD](PRD.md) · [ARCHITECTURE](ARCHITECTURE.md) · [DESIGN-IN-THE-SMALL](DESIGN-IN-THE-SMALL.md) · [DESIGN-PATTERNS](DESIGN-PATTERNS.md) · [ANALYSIS](ANALYSIS.md) · [DESIGN-STATUS](DESIGN-STATUS.md)

## 1. Piramide

```
            e2e / live macOS  (pochi, lenti, marcati)
        TUI (Pilot + snapshot SVG)  (medi)
     integrazione (indice reale su fixture, mandoc reale)  (medi)
  unit (pure, veloci, ~70% dei test)
```

| Livello | Strumenti | Marker pytest | Dove gira |
|---|---|---|---|
| unit | pytest, hypothesis | (default) | locale, CI (anche Linux) |
| integrazione | pytest, `tmp_path`, fixture di man page | `integration` | locale, CI macOS |
| TUI | `pytest-asyncio`, Textual `Pilot`, `pytest-textual-snapshot` | `tui` | locale, CI macOS |
| live macOS | pytest, `leva-verify` | `macos_live` | solo runner macOS (>= 2 versioni), nightly + pre-release |

Gli unit test non devono richiedere macOS ne' `mandoc` ne' rete.

## 2. Test per modulo

| Modulo | Unit | Integrazione | E2E / live |
|---|---|---|---|
| `model` | invarianti dei value object, uguaglianza/hash | - | - |
| `paths` | `LEVA_HOME` vs default; nessun I/O | - | - |
| `placeholders` | `parse/to_plain/names`; property test: concatenazione = comando senza graffe; escape `\{{`; non chiuso; adiacenti `{{a}}{{b}}`; unicode | - | - |
| `clipboard` | `FakeClipboard`; `PbcopyClipboard` con binario finto (script che scrive su file) per exit != 0, timeout, binario assente | - | live: `pbcopy` reale + `pbpaste` roundtrip |
| `sources` | `ExecutableScanner`/`ManPageLocator` su directory finte (`tmp_path`): non eseguibili, symlink, `.gz`, directory mancanti, ordine stabile; `ProbeRunner` rifiuta comandi fuori allowlist, tronca output, timeout (script finto che dorme) | - | live: `/usr/bin` ha >= 1000 eseguibili, `ls` presente |
| `manparse` | golden test: `tests/fixtures/man/*.txt` (pagine sintetiche scritte da noi: `[`/`test` alias, NAME multi-riga, stub `.so`, sezioni non standard, testo vuoto); `parse_man` non solleva su input casuale (hypothesis) | `MandocRenderer` su pagine `.1` sintetiche con `mandoc` reale | live: tutte le pagine di `/usr/share/man/man1` si renderizzano con <= 2% saltate |
| `subcmd` | `HyphenPageExtractor` (git-*), `SectionListExtractor`, `HelpTextExtractor` su testi fixture (profili `two-col`, `git-list`, `brew-commands`); merge e priorita' | - | live: `git`, `diskutil`, `defaults`, `launchctl`, `brew` (se presente) producono >= N sottocomandi |
| `content` | schema valido/invalido: ogni regola di validazione ha un test negativo con messaggio `file:campo`; `skip` senza `reason`; id duplicati; placeholder malformati; schema sconosciuto | tutti i `commands/*.yaml` reali caricano senza errori (gira in CI su Linux) | - |
| `store` | `IndexWriter` rollback su eccezione; vincoli UNIQUE; `finalize` valorizza meta | scrittura -> lettura con `Repository`; migrazione `user_version` errata -> `IndexUnavailableError`; **determinismo**: due build sulla stessa fixture -> stesso `index_digest` | - |
| `repo` | query su DB piccolo in memoria costruito dalla fixture; sanitizzazione FTS (`"`, `*`, `-`, `NEAR`, SQL injection) | - | - |
| `search` | gold set piccolo (30 query -> atteso nel top-3) su indice fixture; refusi (`gerp` -> `grep`); query vuota; ordinamento stabile a parita' di score; nessun duplicato | latenza: 3000 voci sintetiche, p95 < 50 ms (soglia tollerante in CI) | live: gold set da 50 query "ho dimenticato il comando" sull'indice reale, >= 90% top-3 |
| `library` | `open` per nome/alias/"git commit"; cronologia back/forward; ordine esempi curated->tldr; fusione duplicati | - | - |
| `ingest` | `staleness` per ogni causa (MISSING/VERSION/SYSTEM/FRESH) con `SystemInfo` finto; pagina rotta -> skip + warn; >20% rotte -> errore; build fallita lascia intatto il vecchio indice; atomic swap | build completa su fixture tree (dir finte + `FakeRenderer`) | live: primo avvio su macOS reale: copertura 100% eseguibili, >= 95% con summary, tempo registrato (non bloccante in CI) |
| `tui` | view model, formattazione placeholder (Segment -> Rich Text) | **Pilot**: digitare query, frecce, Invio, `c` (FakeClipboard riceve il testo e StatusLine mostra `copied:`), `Esc`, tab 1-5, click (`pilot.click`) su riga/tab/esempio, `?`, terminale stretto (<60) | snapshot SVG: Search, Card (ogni tab), Ingest progress, About, errore, a 120x40 e 70x30 con indice fixture |
| `cli` | parsing argomenti, exit code, non-TTY -> 2, `--version` | `leva doctor` su `LEVA_HOME` temporaneo | smoke: `leva ls` apre la scheda (Pilot) |
| `verify` | sandbox: `HOME` isolato, env minimo, timeout, `bind` mancante -> fail, `skip` -> skip, comando che scrive fuori dalla sandbox non tocca il vero `HOME` | - | tutti gli esempi curati (`tests/live/test_curated_examples.py`) |

### Test architetturali
- `import-linter` con contratti: strati (`model` < `sources/manparse/subcmd/content/store/repo` < `search/ingest` < `library` < `tui` < `cli`), `tui` non importa `sqlite3`/`subprocess`, `verify` non e' importato dal runtime, nessun import ciclico.
- Test palette: lo stylesheet `leva.tcss` contiene solo i colori della palette (+ `$surface`, `$surface-soft` neutri) e nessuna proprieta' `background` esplicita (salvo fallback documentato).
- Test "no rete": un fixture autouse blocca `socket.socket` negli unit/integration test.
- Test di licenza: `content/ATTRIBUTION.md` esiste e cita tldr-pages e la versione in `tldr/SOURCE.json`.

## 3. Edge case noti da coprire

- Man page: `.gz`, stub `.so`, NAME con piu' nomi e `[`, caratteri non UTF-8, pagina vuota, pagina gigantesca (> 1 MB), sezioni duplicate.
- Eseguibili: symlink circolari, file non eseguibili in `bin`, stesso nome in piu' directory (vince la prima in ordine PATH, tutte annotate).
- Nomi: comandi con caratteri speciali (`[`, `[[`, `.`, `:`), alias builtin (`which`/`where`), nomi in conflitto tra zsh builtin e binario (`echo`, `test`, `kill`, `printf`): due entry distinte con `origin` diverso.
- Ricerca: query con spazi multipli, maiuscole, operatori FTS, query di 1 carattere, emoji/unicode, query lunghissima.
- UI: terminale ridimensionato durante l'uso, esempio con comando molto lungo (wrap, non troncato nella copia), esempio con `{{x}}` ripetuto, click su area vuota, `c` senza esempio selezionato (no-op con hint), `pbcopy` assente.
- Ingest: interruzione a meta' (Ctrl-C) lascia l'indice precedente; disco pieno (`OSError` -> `IngestError`); due istanze di `leva` simultanee (lock file `index.lock`, la seconda attende o usa l'indice esistente).
- Contenuto: esempio `exec` con placeholder non legato, esempio distruttivo mai in `exec`, `min_macos` superiore alla versione corrente -> skip nel report.

## 4. Primo test (TDD): come si inizia

Ordine di implementazione guidato dai test (foglie prima):

1. `tests/unit/test_placeholders.py`
```python
from leva.placeholders import parse, Segment

def test_parse_splits_placeholder_from_text():
    assert parse("tar -xzf {{archive.tar.gz}}") == [
        Segment("tar -xzf ", False),
        Segment("archive.tar.gz", True),
    ]
```
Deve fallire (modulo assente), poi si implementa il minimo.
2. `test_model.py`, `test_paths.py` (`LEVA_HOME`).
3. `test_manparse.py` con la prima fixture golden (`ls`-like sintetica).
4. `test_content.py` con un YAML minimo valido e uno con placeholder non chiuso.
5. `test_store_repo_roundtrip.py`.
6. `test_search.py` (gold set mini).
7. Primo test Pilot: `SearchScreen` con indice fixture.
8. Prima verifica live: un esempio `ls` in `verify: exec`.

## 5. Determinismo e riproducibilita' dei test

- Versioni pinnate: `uv.lock` + `.python-version`; CI usa `uv sync --frozen`.
- Ambiente dei test: `LEVA_HOME` = `tmp_path`; `HOME` isolato; `TZ=UTC`, `LC_ALL=en_US.UTF-8`, `MANWIDTH=80`, `COLUMNS=120` (fixture autouse `clean_env`). Nessuna lettura di `~/` reale.
- Fixture di contenuto: `tests/fixtures/{man,tldr,content}` sono pagine **sintetiche** scritte nel repo (nessuna man page di terzi copiata), piccole e versionate.
- Snapshot TUI: dimensione terminale fissa, indice fixture, `clock` iniettato (`built_at` fisso), assenza di animazioni/ritardi (debounce a 0 nei test); regenerazione snapshot solo con `--snapshot-update` e review del diff SVG.
- Hypothesis: `derandomize=True` in CI + database delle regressioni committato; seed stampato in caso di fallimento.
- Ordinamento: nessun test dipende dall'ordine del file system; tutti gli iteratori delle sorgenti sono ordinati (testato).
- Live macOS: matrice di runner (`macos-14` e `macos-15`, da riconfermare alla creazione del workflow) e, localmente, la versione dell'utente; esempi con `min_macos`; fixture `setup` creano tutto in sandbox, i comandi non toccano rete o dati reali.
- Contenuto riproducibile: `content_version` = hash dei file curati + `tldr/SOURCE.json` (tag e sha256); `tools/vendor_tldr.py` e' idempotente.
- CI: `ruff check`, `ruff format --check`, `mypy`, `import-linter`, `pytest -m "not macos_live"` su Linux e macOS; `pytest -m macos_live` solo macOS; la release e' bloccata se un esempio `exec` fallisce.

## 6. Metriche di qualita' dei test

- Copertura >= 90% su `placeholders`, `content`, `manparse`, `store`, `repo`, `search`, `ingest`; >= 70% su `tui` (comportamento via Pilot).
- Percentuale esempi `skip` < 15%; esempi `exec` >= 60%.
- Zero test flaky tollerati: un test instabile viene messo in quarantena (marker `quarantine`) con issue e scadenza.
