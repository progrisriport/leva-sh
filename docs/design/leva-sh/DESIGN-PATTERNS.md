# DESIGN-PATTERNS — Leva

- Progetto: Leva (`leva-sh`) · Data: 2026-11-20 · Versione: 0.1 · Stato: reviewed
- Doc collegati: [PRD](PRD.md) · [ARCHITECTURE](ARCHITECTURE.md) · [DESIGN-IN-THE-SMALL](DESIGN-IN-THE-SMALL.md) · [TEST-STRATEGY](TEST-STRATEGY.md) · [ANALYSIS](ANALYSIS.md) · [DESIGN-STATUS](DESIGN-STATUS.md)

## Principi guida

Pochi pattern, usati dove riducono davvero il costo di cambiamento: Protocol (ports) per ogni confine con il mondo esterno, dataclass immutabili per il dominio, un solo composition root. Niente framework di dependency injection, niente gerarchie ereditarie.

## Tabella

| Modulo | Pattern | Perche' | Alternative scartate | Costo |
|---|---|---|---|---|
| `model` | Value Object (`@dataclass(frozen=True, slots=True)`) | Tipi condivisi immutabili, hashable, facili da testare e confrontare nel test di determinismo | dict liberi (nessun contratto); pydantic (peso a runtime) | Verbosita' di costruzione |
| `paths` | Parameter Object + risoluzione esplicita dell'ambiente | Test e riproducibilita': `LEVA_HOME` e env passati come argomento | letture globali di `os.environ` (non isolabile) | Un argomento in piu' alla composizione |
| `placeholders` | Funzioni pure + tokenizer a stati | Logica minima, testabile con property test | regex monolitica (casi annidati/escape fragili) | Piccolo parser da mantenere |
| `clipboard` | Port/Adapter (Protocol + `PbcopyClipboard`, `FakeClipboard`) | Isola `subprocess`; test senza toccare gli appunti reali; futuro Linux | chiamare `pbcopy` dalla UI (non testabile) | Un file in piu' |
| `sources` | Strategy + Adapter sul sistema (`SystemInfo` iniettato) | Ogni sorgente e' indipendente e sostituibile in test con fixture di directory | scansione unica monolitica (accoppia tutto al FS reale) | Piu' classi piccole |
| `manparse` | Strategy (`ManRenderer`) + Parser a stati per sezioni | Cambiare renderer (mandoc/man) senza toccare il parser; golden test | parsing roff in proprio (scartato in ADR-0002) | Euristiche di sezione sensibili al formato |
| `subcmd` | Strategy + Chain of Responsibility (lista ordinata di extractor, risultati uniti per nome) | Aggiungere fonti di sottocomandi senza toccare le altre (estensibilita') | un unico estrattore con if per comando (ingestibile) | Regole di merge/deduplicazione |
| `content` | Provider (Repository-like) + Validatore di schema versionato (`schema: 1`) | Nuovi tipi di contenuto (ricette, tutorial) = nuovo provider; errori di autoria con `file:campo` | glob di YAML sparsi nel codice; pydantic | Validatori scritti a mano |
| `store` | Unit of Work (`IndexWriter` transazionale) + migrazioni numerate + Atomic Swap | Indice sempre coerente: o il vecchio o il nuovo, mai metà | scrittura in-place (corruzione su crash) | Doppio spazio disco durante la build |
| `repo` | Repository (query tipizzate, sola lettura) | La UI e la ricerca non vedono SQL | SQL sparso nella UI | Mappatura riga -> dataclass |
| `search` | Pipeline di ranking: candidate generation (fuzzy+FTS) -> score fusion pesata | Qualita' controllabile e testabile con gold set | solo FTS (tollera male refusi e nomi); solo fuzzy (non trova intent) | Taratura pesi + gold set da mantenere |
| `library` | Facade + Memento leggero (cronologia back/forward di `Card`) | La UI ha una sola API di lettura; navigazione indietro coerente | UI che compone `repo` + `search` (accoppiamento) | Un livello in piu' |
| `ingest` | Pipeline/Orchestrator con Observer (`ProgressSink`) + worker pool | Orchestrazione unica; progress senza dipendere dalla UI | callback ad hoc nella UI; thread dentro la UI | Concorrenza da testare (ordine di scrittura deterministico) |
| `tui` | Model-View (view model `Card`/`SearchResult`), Screen routing Textual, Command (azioni dei binding) | Textual e' event-driven; la logica rimane fuori dai widget | widget che interrogano il DB (non testabili) | Duplicazione minima di stato nella UI |
| `tui.theme` | Design Tokens (un solo Theme + stylesheet `leva.tcss`) | Il design system Flosh e' verificabile da un test sullo stylesheet | colori inline nei widget (deriva dalla palette) | Disciplina: niente colori nei widget |
| `cli` | Composition Root (wiring manuale) | Un solo punto conosce le implementazioni concrete; zero magia DI | container DI (eccessivo); singleton globali | Wiring esplicito da aggiornare |
| `verify` | Template Method (setup -> run -> assert -> teardown) su sandbox temporanea | Ogni esempio verificato nello stesso modo, isolato e deterministico | script shell ad hoc per esempio | Fixture da mantenere per esempio |

## Pattern trasversali

- **Errori come tipi**: gerarchia `LevaError`; ogni confine converte eccezioni di terzi (vedi DESIGN-IN-THE-SMALL).
- **Null Object**: `FakeClipboard`/`NullProgress` per test e modalita' non interattive.
- **Fail-soft nell'ingest, fail-fast nel contenuto**: una man page corrotta si salta e si conta; un YAML curato invalido blocca la build del pacchetto (CI), mai l'utente finale.
- **Nessuno stato globale mutabile**: ogni dipendenza e' passata via costruttore.
