# ANALYSIS — Leva

Progetto: Leva (leva-sh) · Data: 2026-11-20 · Versione: 0.1 · Stato: reviewed
Documenti collegati: [PRD](PRD.md), [ARCHITECTURE](ARCHITECTURE.md), [DESIGN-PATTERNS](DESIGN-PATTERNS.md), [DESIGN-IN-THE-SMALL](DESIGN-IN-THE-SMALL.md), [TEST-STRATEGY](TEST-STRATEGY.md), [DESIGN-STATUS](DESIGN-STATUS.md), [ADR-0001](ADR/ADR-0001-stack.md)

## 1. Discovery

- Greenfield (cartella `leva-sh` nuova).
- Vincolo esplicito: design system TUI in `PyDF Tool/CLAUDE.md` (vedi ADR-0005).
- Web (2026-11-20):
  - Textual 8.2.x linea corrente ([Debian tracker](https://tracker.debian.org/textual), [MacPorts](https://ports.macports.org/port/py313-textual/stats/)).
  - I client tldr usano `https://github.com/tldr-pages/tldr/releases/latest/download/tldr.zip`; `tldr.sh/assets` deprecato ([specifica client](https://github.com/tldr-pages/tldr/wiki/Minimum-specifications-for-tldr-pages-command-line-clients)).
  - Licenza tldr discordante tra le fonti (CC BY 4.0 vs BY-SA 4.0) → NB-3.

## 2. Attori e use case

Attori: utente, autore contenuto, CI/maintainer, macOS.

| UC | Descrizione | FR |
|---|---|---|
| UC-1 | `leva tar` → esempi + note BSD/GNU → `c` copia | FR-4, FR-6, FR-12, FR-13 |
| UC-2 | Cerca "extract archive" → tar/unzip/ditto | FR-9 |
| UC-3 | Sottocomandi git/brew/diskutil | FR-8 |
| UC-4 | Manuale per sezioni | FR-5 |
| UC-5 | Primo avvio con progress | FR-1, FR-2, FR-3 |
| UC-6 | Aggiorna indice dopo update macOS | FR-16 |
| UC-7 | Correlati e indietro | FR-15 |
| UC-8 | Autore aggiunge e verifica un comando | FR-6, FR-18 |
| UC-9 | Pannello stretto | FR-19 |
| UC-10 | `leva doctor` | FR-20 |

## 3. Rischi (P×I, scala 1-5)

| ID | Rischio | P | I | Score | Mitigazione |
|---|---|---|---|---|---|
| R-1 | Ingest primo avvio >30 s | 3 | 4 | 12 | Spike S-2, pool 8 worker, piano B rendering lazy |
| R-2 | mandoc assente / output diverso tra versioni macOS | 2 | 4 | 8 | Fallback `man -P cat` + `col -bx`, golden test, doctor |
| R-3 | Euristiche di parsing fragili | 4 | 3 | 12 | Degradazione elegante, extractor pluggabili |
| R-4 | Sfondo trasparente non ottenibile in Textual | 3 | 3 | 9 | Spike S-1, fallback `$surface` neutro |
| R-5 | Esempi errati o obsoleti | 3 | 5 | 15 | leva-verify su più macOS, gate di release |
| R-6 | Costo di autoria 150-200 comandi | 4 | 3 | 12 | Rilascio incrementale, tldr come base, verifica automatica |
| R-7 | Licenza/attribuzione tldr | 2 | 4 | 8 | Controllo LICENSE.md, ATTRIBUTION.md, test di presenza |
| R-8 | Breaking change Textual | 3 | 3 | 9 | Pin `<9`, snapshot |
| R-9 | Python di sistema 3.9 | 3 | 3 | 9 | brew/uv/pipx |
| R-10 | Help probe pericolosa | 1 | 5 | 5 | Allowlist, read-only, sandbox |
| R-11 | FTS5 assente | 1 | 3 | 3 | Doctor, degradazione a LIKE |
| R-12 | Indice stale | 3 | 2 | 6 | Fingerprint + hint |
| R-13 | Scope creep | 3 | 3 | 9 | Non-obiettivi espliciti |

## 4. Dipendenze e maturità

- Textual 8.x: alta, API in evoluzione.
- rapidfuzz, PyYAML, SQLite/FTS5: alta.
- mandoc: alta, versione legata a macOS, da confermare in S-2.
- tldr-pages: alta, licenza da riconfermare.
- Runner macOS di GitHub Actions: media, i nomi ruotano.
- Toolchain di sviluppo: alta.

## 5. Debito potenziale

- Euristiche di parsing da riallineare a ogni major di macOS.
- Invecchiamento del corpus curato.
- Pesi di ranking e gold set.
- Contratto `schema: 1` del YAML.
- Convenzioni visive nuove da riportare nel design system.

## 6. Valutazione dei 4 requisiti

- **Mantenibilità**: buona. 15 moduli a responsabilità singola, errori tipizzati, contenuto dichiarativo. Punto debole: euristiche di parsing.
- **Riproducibilità**: buona. uv.lock, LEVA_HOME, env fisso, fixture sintetiche, `index_digest`, snapshot tldr pinnato. L'indice dipende dal Mac ma è deterministico a parità di input.
- **Modularità**: buona. Grafo aciclico imposto da import-linter, Protocol ai confini, composition root unico.
- **Estensibilità**: buona. Punti espliciti in ARCHITECTURE sez. 5. Una nuova tab richiede una registrazione in `tui` (documentato).

## 7. Comandi curati iniziali (~170)

- **File**: ls cd pwd mkdir rmdir rm cp mv ln touch cat less more head tail wc file stat find du df basename dirname realpath readlink chmod chown chgrp chflags xattr mktemp open ditto rsync scp tree
- **Testo**: grep egrep sed awk cut sort uniq tr tee xargs diff cmp comm paste join column fold fmt nl rev printf echo jq
- **Archivi**: tar zip unzip gzip gunzip bzip2 xz hdiutil
- **Sistema**: ps top kill killall pkill uptime uname sw_vers sysctl system_profiler caffeinate pmset launchctl log date cal time sleep which whereis type env history jobs crontab lsof
- **Rete**: curl ping traceroute netstat ifconfig networksetup dig nslookup host ssh ssh-keygen ssh-add sftp nc route arp scutil
- **macOS**: pbcopy pbpaste say screencapture defaults plutil osascript diskutil mdfind mdls mdutil softwareupdate tmutil dscl spctl codesign security xcode-select xcrun sips textutil qlmanage
- **Dev**: git make clang cc ld lldb otool nm strings lipo python3 ruby perl swift swiftc xcodebuild brew
- **Builtin**: alias unalias export source set unset read trap fg bg wait pushd popd test setopt unsetopt autoload typeset local return exit eval exec ulimit umask
- **Varie**: whoami id groups sudo su w who last passwd man apropos whatis tput clear stty script base64 openssl shasum md5 cksum dd hexdump xxd od bc expr seq yes true false

La v1.0 può uscire con almeno 100 comandi se tutti gli esempi sono verificati.

## 8. Domande non bloccanti

NB-1 … NB-9, come elencate in [DESIGN-STATUS](DESIGN-STATUS.md).

## 9. Spike iniziali

- **S-1**: Textual con sfondo trasparente, bordi `solid` e palette in Terminal.app, iTerm2 e Ghostty.
- **S-2**: mandoc su 20 pagine campione (ls, tar, git, zshbuiltins, `[`) + benchmark su ~2000 pagine con 8 worker.
- **S-3**: FTS5 nel Python di brew/uv e dimensione reale dell'indice.

## 10. Decisioni prese durante la revisione

Nessun follow-up in questa prima sessione. Assunzioni registrate:

- Documentazione in italiano; UI e contenuti in inglese.
- Solo macOS, nessuna rete a runtime.
- Python >=3.11, wheel pura.
- Copia placeholder "sbracketati" (`{{x}}` → `x`).
- Ricette (v1.x) e tutorial (v2) non progettati nel dettaglio: riservati `kind` YAML, tabella `content_item` e punti di estensione.
- Licenze confermate dall'utente: codice MIT, contenuto CC BY 4.0, titolare progrisriport (chiude NB-1).
- GitHub: `progrisriport/leva-sh` (privata) (chiude NB-4 per la parte repo).
