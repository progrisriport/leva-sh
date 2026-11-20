# DESIGN-IN-THE-SMALL — Leva

- Progetto: Leva (`leva-sh`) · Data: 2026-11-20 · Versione: 0.1 · Stato: reviewed
- Doc collegati: [PRD](PRD.md) · [ARCHITECTURE](ARCHITECTURE.md) · [DESIGN-PATTERNS](DESIGN-PATTERNS.md) · [TEST-STRATEGY](TEST-STRATEGY.md) · [ANALYSIS](ANALYSIS.md) · [DESIGN-STATUS](DESIGN-STATUS.md)

Le firme sono contratti di design (Python 3.11+, type hints completi), non implementazione. Il corpo e' omesso.

## 0. Convenzioni

**Naming**
- Moduli `snake_case` brevi (un sostantivo): `sources`, `manparse`. Classi `PascalCase`; funzioni/metodi `snake_case` con verbo (`parse_man`, `locate`); costanti `UPPER_SNAKE`.
- Protocol con nome del ruolo (`Clipboard`, `ManRenderer`, `ContentProvider`, `SubcommandExtractor`, `ProgressSink`); implementazioni con prefisso tecnologia (`PbcopyClipboard`, `MandocRenderer`).
- Test: `test_<modulo>.py`, funzioni `test_<comportamento>_<condizione>`.
- Contenuto: file `commands/<nome>.yaml` in minuscolo; `example.id` = `<comando>-<slug>` unico.
- UI: stringhe in inglese, minuscole nei messaggi di stato (`copied: ls -la`).

**Errori** (in `leva.model.errors`)
```python
class LevaError(Exception):
    message: str                      # breve, mostrabile all'utente
    hint: str | None                  # azione suggerita
class IngestError(LevaError): ...     # sorgente non leggibile, build fallita
class ManRenderError(LevaError): ...  # una pagina non renderizzabile (non fatale)
class ContentError(LevaError): ...    # YAML/tldr invalido: message = "file:campo: motivo"
class IndexUnavailableError(LevaError): ...  # index.db assente/corrotto/schema errato
class ClipboardError(LevaError): ...
class VerificationError(LevaError): ...
```
Regole: nessuna eccezione di `sqlite3`/`yaml`/`subprocess` oltrepassa il proprio modulo; la UI mostra `message` in rosso su una riga, i dettagli vanno nel log (`~/Library/Logs/leva/leva.log`, rotazione 1 MB x 3) mai a schermo.

**Exit code CLI**: `0` ok · `1` errore runtime (`LevaError`) · `2` uso errato o stdout/stdin non TTY · `130` interrotto da Ctrl-C.

## 1. `leva.model`

```python
class Origin(StrEnum):  MACOS="macos"; HOMEBREW="homebrew"; ZSH="zsh"; BASH="bash"
class Kind(StrEnum):    EXECUTABLE="executable"; BUILTIN="builtin"; MANPAGE_ONLY="manpage"

@dataclass(frozen=True, slots=True)
class Entry:
    id: int; name: str; section: str | None; kind: Kind; origin: Origin
    summary: str            # "" se assente
    path: str | None        # percorso del binario
    has_man: bool; curated: bool

@dataclass(frozen=True, slots=True)
class Section:  heading: str; body: str; ord: int

@dataclass(frozen=True, slots=True)
class Example:
    id: str; desc: str; cmd: str                    # cmd con {{placeholder}}
    source: Literal["curated","tldr"]; verified: Literal["exec","static","skip","none"]

@dataclass(frozen=True, slots=True)
class Note:  kind: Literal["bsd-gnu","zsh-bash","macos","safety"]; text: str

@dataclass(frozen=True, slots=True)
class Subcommand: name: str; summary: str; entry_name: str | None; source: str
```
Invarianti: `name` non vuoto, senza spazi; `Example.cmd` non vuoto, una sola riga logica (continuazioni con `\` ammesse).

## 2. `leva.placeholders`

```python
@dataclass(frozen=True, slots=True)
class Segment: text: str; is_placeholder: bool

def parse(cmd: str) -> list[Segment]: ...
def to_plain(cmd: str) -> str: ...        # {{a}} -> a
def names(cmd: str) -> list[str]: ...
```
- Pre: `cmd` stringa qualsiasi. Post: `"".join(s.text for s in parse(cmd))` equivale a `cmd` con le graffe doppie rimosse; i segmenti non sono mai vuoti.
- Escape: `\{{` produce letterale `{{`. Placeholder non chiuso -> trattato come testo letterale (nessun errore a runtime). La validazione **stretta** (placeholder vuoto, non chiuso) avviene in `content` e solleva `ContentError`.
- Esempio: `parse("tar -xzf {{archive.tar.gz}}")` -> `[Segment("tar -xzf ", False), Segment("archive.tar.gz", True)]`.

## 3. `leva.clipboard`

```python
class Clipboard(Protocol):
    def copy(self, text: str) -> None: ...      # solleva ClipboardError

class PbcopyClipboard:
    def __init__(self, *, binary: str = "/usr/bin/pbcopy", timeout: float = 2.0) -> None: ...
```
- Pre: `text` non vuoto, <= 64 KiB. Post: gli appunti contengono esattamente `text` (UTF-8). Errori: binario mancante, timeout, exit != 0 -> `ClipboardError("clipboard unavailable")`.
- Uso: `clip.copy(placeholders.to_plain(example.cmd))`. `FakeClipboard` espone `.last`.

## 4. `leva.paths`

```python
@dataclass(frozen=True, slots=True)
class LevaPaths:
    data_dir: Path; config_file: Path; log_dir: Path
    @property
    def index_db(self) -> Path: ...
    @classmethod
    def resolve(cls, env: Mapping[str, str], home: Path) -> "LevaPaths": ...
```
Se `LEVA_HOME` e' in `env`, tutti i percorsi stanno li' (test/CI); altrimenti `~/Library/Application Support/leva` e `~/Library/Logs/leva`. Non crea directory (lo fa il chiamante).

## 5. `leva.sources`

```python
@dataclass(frozen=True, slots=True)
class SystemInfo:  macos_version: str; macos_build: str; arch: str
    @classmethod
    def detect(cls) -> "SystemInfo": ...         # unico punto che invoca sw_vers

@dataclass(frozen=True, slots=True)
class Executable:  name: str; path: Path; origin: Origin
@dataclass(frozen=True, slots=True)
class ManFile:     path: Path; section: str; origin: Origin; mtime_ns: int

class ExecutableScanner:
    def __init__(self, dirs: Sequence[Path]) -> None: ...
    def scan(self) -> Iterator[Executable]: ...  # ordinato per (name, path); salta non-eseguibili, duplicati in PATH-order

class ManPageLocator:
    def __init__(self, man_dirs: Sequence[Path], sections: Sequence[str] = ("1","8")) -> None: ...
    def locate(self) -> Iterator[ManFile]: ...   # ordinato; .gz ammesso

class BuiltinSource:
    def __init__(self, renderer: ManRenderer) -> None: ...
    def builtins(self) -> Iterator[tuple[Origin, str]]: ...   # (ZSH|BASH, nome) da zshbuiltins/builtin

class ProbeRunner:
    def __init__(self, allowlist: Mapping[str, tuple[str, ...]], *, timeout: float = 5.0, max_bytes: int = 262_144) -> None: ...
    def run(self, command: str) -> str: ...      # command deve essere chiave dell'allowlist
```
- Errori: directory assente -> ignorata (non errore); `ProbeRunner.run` con comando fuori allowlist -> `IngestError` (mai eseguito); timeout/exit != 0 -> `IngestError` non fatale (l'ingest lo logga e continua).
- Esempio: `list(ExecutableScanner([Path("/bin")]).scan())[0].name == "["`.

## 6. `leva.manparse`

```python
class ManRenderer(Protocol):
    def render(self, path: Path) -> str: ...     # solleva ManRenderError

class MandocRenderer:
    def __init__(self, binary: str = "/usr/bin/mandoc", width: int = 80, timeout: float = 10.0) -> None: ...

@dataclass(frozen=True, slots=True)
class ParsedMan:
    names: tuple[str, ...]       # da NAME: tutti gli alias
    summary: str
    sections: tuple[Section, ...]
    redirect_to: str | None      # pagine stub ".so"

def parse_man(text: str, *, name_hint: str) -> ParsedMan: ...
```
- Pre: `text` gia' senza overstrike. Post: `sections` in ordine di apparizione, `names` mai vuoto (almeno `name_hint`), `summary` una riga <= 200 caratteri.
- Edge: `[ -- condition evaluation`, `test, [ -- ...`, NAME multi-riga, sezioni non standard, righe vuote finali.
- Errori: `ManRenderError` per file illeggibile/timeout; `parse_man` non solleva su testo strano (degrada: una sezione `DESCRIPTION` con tutto il testo).

## 7. `leva.subcmd`

```python
class SubcommandExtractor(Protocol):
    def extract(self, parent: str, parsed: ParsedMan | None, known: Mapping[str, Entry]) -> list[Subcommand]: ...

class HyphenPageExtractor: ...      # git-commit -> Subcommand("commit", summary, entry_name="git-commit")
class SectionListExtractor: ...     # sezioni COMMANDS|SUBCOMMANDS|VERBS: termine indentato + descrizione
class HelpTextExtractor:            # per output di ProbeRunner, con profili: "two-col", "git-list", "brew-commands"
    def __init__(self, profile: str, text: str) -> None: ...
```
- Post: nomi unici, ordinati; il merge a cura di `ingest` preferisce, in ordine: curato > help probe > sezione man > hyphen.

## 8. `leva.content`

```python
@dataclass(frozen=True, slots=True)
class CuratedCommand:
    name: str; section: str | None; summary: str; explain: str
    intents: tuple[str, ...]; tags: tuple[str, ...]
    notes: tuple[Note, ...]; examples: tuple[ExampleSpec, ...]
    subcommands: tuple[Subcommand, ...]; related: tuple[str, ...]
    help_probe: tuple[str, ...] | None

@dataclass(frozen=True, slots=True)
class ExampleSpec:
    id: str; desc: str; cmd: str
    verify: VerifySpec                      # mode: exec|static|skip

@dataclass(frozen=True, slots=True)
class VerifySpec:
    mode: Literal["exec","static","skip"]
    setup: str = ""; bind: Mapping[str, str] = {}
    expect_exit: int = 0; stdout_contains: tuple[str, ...] = (); stdout_regex: str | None = None
    files_exist: tuple[str, ...] = (); reason: str | None = None; min_macos: str | None = None

class ContentProvider(Protocol):
    def load(self) -> Iterator[CuratedCommand | TldrPage]: ...   # solleva ContentError

class CuratedYamlProvider:  def __init__(self, root: Path) -> None: ...
class TldrSnapshotProvider: def __init__(self, root: Path) -> None: ...
```
- Pre: file UTF-8 con `schema: 1`. Post: oggetti validati; esempi con id unici; `skip` richiede `reason`; `related` solo stringhe; placeholder ben formati.
- Errori: `ContentError("commands/tar.yaml:examples[2].cmd: unclosed placeholder")`.
- Esempio YAML:
```yaml
schema: 1
kind: command
name: tar
section: "1"
summary: Create, list and extract archive files.
explain: |
  tar bundles files into one archive; with -z/-j/-J it also (de)compresses.
intents: [extract an archive, make a zip-like backup, list archive contents]
notes:
  - {kind: bsd-gnu, text: "macOS tar is bsdtar: --wildcards and --transform are GNU-only; use -s for substitution."}
examples:
  - id: tar-extract-gz
    desc: Extract a .tar.gz into the current directory
    cmd: tar -xzf {{archive.tar.gz}}
    verify:
      mode: exec
      setup: "mkdir d && echo hi > d/a && tar -czf archive.tar.gz d && rm -r d"
      bind: {archive.tar.gz: archive.tar.gz}
      files_exist: [d/a]
related: [gzip, zip, ditto]
```

## 9. `leva.store`

```python
SCHEMA_VERSION: int

class IndexWriter:
    def __init__(self, path: Path) -> None: ...         # path = index.db.new
    def __enter__(self) -> "IndexWriter": ...
    def __exit__(self, *exc) -> None: ...               # rollback se eccezione
    def add_entry(self, e: NewEntry) -> int: ...
    def add_alias(self, entry_id: int, alias: str) -> None: ...
    def add_sections(self, entry_id: int, sections: Sequence[Section]) -> None: ...
    def add_examples(self, entry_id: int, examples: Sequence[Example]) -> None: ...
    def add_subcommands(self, entry_id: int, subs: Sequence[Subcommand]) -> None: ...
    def add_notes(self, entry_id: int, notes: Sequence[Note]) -> None: ...
    def add_related(self, entry_id: int, names: Sequence[str]) -> None: ...
    def set_meta(self, key: str, value: str) -> None: ...
    def finalize(self) -> None: ...                     # FTS rebuild, ANALYZE, index_digest in meta

def open_readonly(path: Path) -> sqlite3.Connection: ...   # solleva IndexUnavailableError
```
Schema (v1):
```sql
meta(key TEXT PRIMARY KEY, value TEXT)
entry(id INTEGER PRIMARY KEY, name TEXT, section TEXT, kind TEXT, origin TEXT,
      summary TEXT, path TEXT, has_man INT, curated INT, explain TEXT, UNIQUE(name, section, origin))
alias(entry_id INT, alias TEXT)             -- indice su alias
doc_section(entry_id INT, ord INT, heading TEXT, body TEXT)
example(entry_id INT, ord INT, id TEXT, desc TEXT, cmd TEXT, source TEXT, verified TEXT)
note(entry_id INT, ord INT, kind TEXT, text TEXT)
subcommand(entry_id INT, ord INT, name TEXT, summary TEXT, entry_name TEXT, source TEXT)
related(entry_id INT, ord INT, name TEXT)
intent(entry_id INT, text TEXT)
content_item(id INTEGER PRIMARY KEY, kind TEXT, key TEXT, payload JSON)   -- riservata a ricette/tutorial
search_fts USING fts5(name, intents, summary, body, content='', tokenize='unicode61 remove_diacritics 2')
```
- Pre: file non esistente. Post dopo `finalize`: `PRAGMA integrity_check = ok`, `meta.schema_version`, `meta.index_digest` valorizzati. Errori: I/O o violazione vincoli -> `IngestError`.

## 10. `leva.repo`

```python
class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None: ...
    def meta(self) -> Mapping[str, str]: ...
    def names(self) -> list[NameRow]: ...                       # (entry_id, name, kind, summary, intents) per fuzzy in memoria
    def get_entry(self, name: str, section: str | None = None) -> Entry | None: ...  # nome o alias
    def sections(self, entry_id: int) -> list[Section]: ...
    def examples(self, entry_id: int) -> list[Example]: ...
    def notes(self, entry_id: int) -> list[Note]: ...
    def subcommands(self, entry_id: int) -> list[Subcommand]: ...
    def related(self, entry_id: int) -> list[str]: ...
    def fts(self, query: str, limit: int) -> list[FtsHit]: ...  # query sanitizzata: mai SQL/operatori utente grezzi
    def stats(self) -> IndexStats: ...
```
- Errori: DB incoerente -> `IndexUnavailableError`. `fts` con query vuota -> `[]`.

## 11. `leva.search`

```python
@dataclass(frozen=True, slots=True)
class SearchResult:  entry_id: int; name: str; summary: str; score: float; why: Literal["name","alias","intent","summary","body"]

class Searcher:
    def __init__(self, repo: Repository, *, weights: Weights = DEFAULT_WEIGHTS) -> None: ...
    def search(self, query: str, limit: int = 50) -> list[SearchResult]: ...
```
Ranking (deterministico, a parita' di score ordine per nome): match esatto nome > prefisso nome > fuzzy nome (`rapidfuzz.fuzz.WRatio` >= 80) > intents > summary > corpo (bm25). Curated e builtin ricevono un bonus piccolo e fisso. Pre: `query` stripped; vuota -> lista vuota. Post: <= `limit` risultati, nessun duplicato per `entry_id`.
Esempio: `search("extract tar")` -> primo `tar` (why=`intent`).

## 12. `leva.library`

```python
@dataclass(frozen=True, slots=True)
class Card:
    entry: Entry; explain: str; notes: tuple[Note, ...]; examples: tuple[Example, ...]
    subcommands: tuple[Subcommand, ...]; related: tuple[str, ...]; sections: tuple[Section, ...]
    breadcrumb: tuple[str, ...]            # ("git", "commit")

class Library:
    def __init__(self, repo: Repository, searcher: Searcher) -> None: ...
    def search(self, query: str, limit: int = 50) -> list[SearchResult]: ...
    def open(self, name: str) -> Card | None: ...        # nome o alias; "git commit" apre il sottocomando
    def open_subcommand(self, card: Card, sub: str) -> Card | None: ...
    def back(self) -> Card | None
    def forward(self) -> Card | None
    def attribution(self) -> str                         # testo ATTRIBUTION per About
```
Post: `open` registra la cronologia (max 50). Esempi ordinati: curated prima, poi tldr, duplicati normalizzati fusi.

## 13. `leva.ingest`

```python
class ProgressSink(Protocol):
    def phase(self, name: str, total: int | None) -> None: ...
    def advance(self, n: int = 1) -> None: ...
    def warn(self, message: str) -> None: ...

class Staleness(StrEnum): MISSING; VERSION_CHANGED; SYSTEM_CHANGED; FRESH

@dataclass(frozen=True, slots=True)
class BuildReport: entries: int; man_pages: int; skipped: tuple[tuple[str,str], ...]; curated: int; seconds: float; digest: str

class IndexBuilder:
    def __init__(self, *, executables: ExecutableScanner, man: ManPageLocator, builtins: BuiltinSource,
                 renderer: ManRenderer, extractors: Sequence[SubcommandExtractor],
                 providers: Sequence[ContentProvider], probes: ProbeRunner,
                 system: SystemInfo, workers: int = 8) -> None: ...
    def fingerprint(self) -> str: ...
    def staleness(self, index_db: Path) -> Staleness: ...
    def build(self, target: Path, progress: ProgressSink) -> BuildReport: ...
```
- Pre `build`: `target` directory scrivibile. Post: `target` (dopo swap atomico) e' un indice valido; se la build fallisce il vecchio indice resta intatto e il file `.new` e' rimosso. Pagina singola non renderizzabile -> `progress.warn` + in `skipped`, mai abort. Piu' del 20% di pagine saltate -> `IngestError("man pages unreadable; run leva doctor")`.

## 14. `leva.tui`

```python
class StartTarget(NamedTuple):  kind: Literal["search","card"]; value: str

class LevaApp(App[int]):
    def __init__(self, library: Library, clipboard: Clipboard, builder: IndexBuilder | None,
                 start: StartTarget, paths: LevaPaths) -> None: ...
```
Binding (visibili nel footer):

| Contesto | Tasto | Azione |
|---|---|---|
| globale | `/` | focus ricerca |
| globale | `?` | aiuto tasti |
| globale | `Esc` | indietro / chiude overlay |
| globale | `q`, `Ctrl+C` | esci (`q` non nei campi di testo) |
| globale | `r` | rebuild indice (con conferma: operazione lunga, non distruttiva) |
| globale | `a` | About/attribuzioni |
| lista | `Up/Down`, `j/k`, `PgUp/PgDn`, `g/G` | naviga |
| lista | `Enter` | apri scheda |
| scheda | `1`-`5`, `Left/Right`, `h/l` | cambia tab |
| scheda | `Enter` (su sottocomando/correlato) | apri |
| scheda | `c` | copia esempio selezionato |
| scheda | `[` / `]` | sezione man precedente/successiva |
| scheda | `Backspace`, `Alt+Left` | indietro nella cronologia |

Mouse: click su riga lista, tab, esempio (click = copia), sottocomando/correlato (apre), breadcrumb (torna), rotella (scroll). Footer e' un widget fisso: separatore `─` + testo `#7A7A7A`; `StatusLine` sopra al footer mostra `copied: ...` (verde) o errore (rosso) per 3 s.
Pre: terminale >= 60 colonne e >= 12 righe, altrimenti schermata "terminal too narrow" (header+footer presenti). Errori di `Library` -> riga rossa, l'app non si chiude.

## 15. `leva.cli`

```python
def main(argv: Sequence[str] | None = None) -> int: ...
```
Sintassi: `leva [query...]` · `leva --rebuild` · `leva --about` · `leva --version` · `leva doctor [--offline]`.
Flusso: risolve `LevaPaths` -> se `staleness` in {MISSING, VERSION_CHANGED} apre `IngestScreen` (build bloccante con progress) -> parse query (join degli argomenti con spazio) -> `StartTarget`. `leva doctor` stampa testo semplice (versioni, `mandoc` presente, FTS5 disponibile, conteggi indice, `pbcopy` presente) con exit 0/1.
Non-TTY: stampa `leva needs an interactive terminal` su stderr, exit 2.

## 16. `leva.verify`

```python
@dataclass(frozen=True, slots=True)
class VerifyResult: example_id: str; status: Literal["pass","fail","skip"]; detail: str; seconds: float

class Verifier:
    def __init__(self, repo: Repository | None, *, workdir: Path, timeout: float = 10.0) -> None: ...
    def verify(self, command: str, spec: ExampleSpec) -> VerifyResult: ...
```
- `exec`: crea `workdir/<id>/` temporanea, `HOME` = quella, `env` minimo (`PATH=/usr/bin:/bin:/usr/sbin:/sbin`, `LC_ALL=en_US.UTF-8`), esegue `setup` poi il comando con placeholder sostituiti via `bind` (`/bin/zsh -f -c`), `stdin=/dev/null`, timeout; poi asserzioni. Placeholder non presenti in `bind` -> `fail` ("unbound placeholder").
- `static`: `shlex.split`, binario presente nell'indice o nel PATH, ogni flag corto/lungo trovato nel testo man/help.
- `skip`: ritorna `skip` con `reason` (e la CI conteggia la percentuale).
- Esempio d'uso (dev): `uv run leva-verify --command tar --min-macos 14`; in pytest: `tests/live/test_curated_examples.py` parametrizzato su tutti gli esempi.

## 17. Dettagli trasversali

- **Logging**: `logging` stdlib, logger `leva.<modulo>`, file rotante; mai su stdout durante la TUI.
- **Tempo/casualita'**: nessuna casualita' nel runtime; l'orologio entra solo in `meta.built_at` ed e' iniettabile.
- **Concorrenza**: solo `ThreadPoolExecutor` nell'ingest (subprocess I/O bound); la UI usa i worker di Textual (`run_worker(thread=True)`) per la build.
