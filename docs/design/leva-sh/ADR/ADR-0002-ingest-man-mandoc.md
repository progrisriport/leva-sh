# ADR-0002 — Strategia di ingest delle man page

- Progetto: Leva · Data: 2026-11-20 · Versione: 0.1 · Stato doc: reviewed
- Stato ADR: Accepted
- Doc collegati: [PRD](../PRD.md) · [ARCHITECTURE](../ARCHITECTURE.md) · [ADR-0001](ADR-0001-stack.md) · [ADR-0003](ADR-0003-storage-sqlite-fts5.md)

## Contesto

Livello 1 dell'enciclopedia: indice automatico dei comandi del Mac dell'utente (~1300 eseguibili in `/bin /sbin /usr/bin /usr/sbin`, ~2000 man page sez. 1/8, 103 builtin zsh, man Homebrew in `/opt/homebrew/share/man`). Deve essere offline e coerente con la versione di macOS. Le man page sono materiale di terzi (Apple/BSD/GNU): non redistribuibili nel pacchetto. Ottenere sottocomandi richiede talvolta `--help`, ma eseguire binari arbitrari e' pericoloso (`reboot --help`, comandi interattivi, side effect).

## Decisione

1. **Nessuna man page e' distribuita con Leva**: l'ingest avviene sempre in locale, al primo avvio e quando il fingerprint cambia.
2. **Scoperta**: directory man da `manpath` (binario di sistema a path fisso) unite a `/opt/homebrew/share/man`, `/usr/local/share/man` e `extra_man_paths` di config; sezioni `1` e `8` (configurabile, es. aggiungere `5`). Eseguibili: scansione di `/bin /sbin /usr/bin /usr/sbin` (+ `/opt/homebrew/bin`, `/usr/local/bin` se presenti, + `extra_bin_dirs`).
3. **Rendering**: `mandoc -T ascii -O width=80` (poi rimozione overstrike con `col -bx` se serve), eseguito in un `ThreadPoolExecutor` (subprocess, 8 worker, timeout 10 s per pagina). Fallback se `mandoc` manca: `man -P cat` + `col -bx`. Il renderer sta dietro il Protocol `ManRenderer`.
4. **Parsing**: il testo e' diviso in sezioni sull'intestazione a colonna 0 in maiuscolo; `NAME` produce nomi/alias e summary (`name1, name2 -- summary`); pagine stub `.so` diventano alias; pagine illeggibili vengono saltate e contate nel `BuildReport` (mai abortire l'intera build).
5. **Builtin**: `man zshbuiltins` (103 builtin) e `man builtin`/`man bash` per i builtin bash vengono parsati con estrattori dedicati; entry con `kind=builtin` e `origin=zsh|bash`.
6. **Sottocomandi**: strategie pluggabili `SubcommandExtractor`: (a) pagine `<parent>-<sub>` (git-commit); (b) sezioni `COMMANDS/SUBCOMMANDS/VERBS` delle man page; (c) YAML curato; (d) **help probe** solo se dichiarato nel YAML curato (allowlist) e per comandi read-only (`brew commands`, `diskutil` senza argomenti, `defaults` senza argomenti, `launchctl help`, `git help -a`): `shell=False`, stdin `/dev/null`, cwd temporaneo, env minimo, timeout 5 s, output troncato a 256 KiB. Mai eseguire un binario non in allowlist.
7. **Eseguibili senza man page** diventano entry con summary vuoto marcato "no manual entry" e il path del binario.
8. **Determinismo**: elaborazione parallela ma scrittura nell'indice in ordine alfabetico `(name, section, origin)`; `LC_ALL=en_US.UTF-8`, `MANWIDTH=80`, `TZ=UTC` nell'ambiente dei subprocess.
9. **Fingerprint** = sha256 di: versione contenuto Leva, schema_version, macOS ProductVersion+Build, (numero file, mtime massimo) per ogni directory man e bin, hash della config. Mismatch dovuto a Leva/schema: rebuild automatico bloccante; mismatch di sistema: hint in UI e `r`/`leva --rebuild`.
10. **Scrittura atomica**: build su `index.db.new`, poi `os.replace`.

## Conseguenze

- Il primo avvio costa tempo (target <= 30 s su Apple Silicon, con progress). Rischio R-1: spike di benchmark come primo task; piano B: rendering lazy (solo NAME all'ingest, corpo reso on demand e cachato).
- Dipendenza dal formato testo di `mandoc` per le euristiche di sezione: coperta da golden test su pagine sintetiche + suite `macos_live`.
- Sicurezza: la superficie di esecuzione e' limitata a `mandoc`, `manpath`, `sw_vers`, `pbcopy` e alle sonde in allowlist.

## Alternative

- Distribuire un dump pre-generato delle man page: scartato (licenze, incoerenza con macOS dell'utente).
- Parsare il sorgente roff/mdoc in proprio: scartato (complessita' enorme).
- Usare `apropos`/`whatis` (database makewhatis): solo summary, nessun corpo; scartato come fonte primaria.
- Eseguire `--help` su tutti gli eseguibili: scartato (sicurezza, lentezza, formati disomogenei).
- Ingest lazy puro (nessun indice del corpo): scartato per v1 perche' la ricerca full-text sul corpo e' un valore centrale; resta piano B.
