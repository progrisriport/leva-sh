# ADR-0004 — Contenuto curato in YAML con esempi verificabili

- Progetto: Leva · Data: 2026-11-20 · Versione: 0.1 · Stato doc: reviewed
- Stato ADR: Accepted
- Doc collegati: [PRD](../PRD.md) · [ARCHITECTURE](../ARCHITECTURE.md) · [DESIGN-IN-THE-SMALL](../DESIGN-IN-THE-SMALL.md) · [TEST-STRATEGY](../TEST-STRATEGY.md)

## Contesto

Livello 2: ~150-200 comandi con spiegazione chiara, esempi copiabili, note BSD vs GNU e zsh vs bash, correlati. L'affidabilita' e' il valore del prodotto: un esempio sbagliato distrugge la fiducia. Gli esempi base vengono da tldr-pages (CC BY 4.0 secondo le fonti consultate; la ricerca web riporta anche indicazioni discordanti, quindi `LICENSE.md` del repo va riletto al momento del vendoring).

## Decisione

1. **Formato**: un file `content/commands/<name>.yaml` per comando, con `schema: 1` e `kind: command` (il campo `kind` riserva `recipe` e `path` per v1.x/v2). Placeholder con sintassi `{{nome}}` (compatibile con tldr).
2. **Campi**: `name`, `section`, `summary`, `explain`, `intents` (frasi che l'utente cercherebbe: "extract an archive"), `tags`, `notes[]` (`kind: bsd-gnu|zsh-bash|macos|safety`), `examples[]` (`id`, `desc`, `cmd`, `verify`), `subcommands[]`, `related[]`, `help_probe` (opzionale, allowlist).
3. **Esempi verificabili**: ogni esempio ha un blocco `verify` con `mode`:
   - `exec`: eseguito in sandbox di directory temporanea (HOME e cwd temporanei, env minimo, timeout 10 s) dopo `setup` (script di fixture) e con `bind` che sostituisce i placeholder con valori di fixture; asserzioni `exit`, `stdout_contains|stdout_regex`, `files_exist`.
   - `static`: il comando viene tokenizzato con `shlex`, si verifica che il binario esista nell'indice e che ogni flag compaia nella man page/help; usato per esempi non eseguibili in sicurezza.
   - `skip` con `reason` obbligatorio: solo per esempi distruttivi/privilegiati (es. `diskutil eraseDisk`, `sudo`) ; il numero di `skip` e' una metrica monitorata (obiettivo < 15%).
4. **Gli esempi tldr** sono vendorizzati come snapshot compatto (`content/tldr/*.jsonl`, solo `common` + `osx`, inglese) a una release pinnata (`tools/vendor_tldr.py` registra tag e hash in `content/tldr/SOURCE.json`) e ricevono `verify: static` automatico; il testo di attribuzione sta in `content/ATTRIBUTION.md` ed e' mostrato da `leva --about` e dalla schermata About.
5. **Licenze**: codice MIT, contenuto curato CC BY 4.0 (coerente con tldr). Da confermare dal proprietario (vedi ANALYSIS, domande non bloccanti).
6. **Autoria**: assistita da LLM ma sempre passata da `leva-verify` e da revisione umana; il gate CI blocca la merge se un esempio `exec` fallisce su macOS.
7. Precedenza in UI: esempi curati prima, poi tldr; duplicati (stesso comando normalizzato) fusi.

## Conseguenze

- Il costo di scrittura e' piu' alto di un testo libero, ma i regressioni macOS-version sono rilevate automaticamente (CI su piu' runner macOS, `min_macos` opzionale per esempio).
- Lo schema e' parte dell'API pubblica del contenuto: modifiche con bump di `schema`.

## Alternative

- Markdown libero come tldr: piu' semplice ma non verificabile ne' strutturato; scartato.
- Tutto da `--help`/man senza curatela: non risolve "ricordo il comando" (scartato, e' il livello 1).
- Verifica solo statica: troppo debole per esempi su pipeline e flag BSD; scartato come unico livello.
