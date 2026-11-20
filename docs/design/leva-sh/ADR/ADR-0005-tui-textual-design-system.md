# ADR-0005 — TUI: Textual conforme al design system Flosh

- Progetto: Leva · Data: 2026-11-20 · Versione: 0.1 · Stato doc: reviewed
- Stato ADR: Accepted (con azione preliminare: aggiornare il design system, vedi Conseguenze)
- Doc collegati: [PRD](../PRD.md) · [ARCHITECTURE](../ARCHITECTURE.md) · [ADR-0001](ADR-0001-stack.md)
- Fonte vincolante: `/Users/flosh/Desktop/Coding.nosync/Progetti/PyDF Tool/CLAUDE.md`

## Contesto

Il design system e' scritto per prompt_toolkit+rich, ma ammette esplicitamente `$surface`/`$surface-soft` per Textual. Alcune sue regole (1-4) riguardano pt/rich e non si applicano a Textual; le regole sul visual (palette, bordi, header/footer, no emoji, sfondo trasparente) si applicano integralmente. La regola 5 di "Applicare" impone di aggiornare il file prima di introdurre dipendenze grafiche nuove; la regola 6 di documentare prima nuove convenzioni visive.

## Decisione

**Tema** (un solo Theme Textual, `leva.tui.theme`):

| Ruolo | Valore | Uso in Leva |
|---|---|---|
| accento | `#E8B84B` | titoli box, voce selezionata, tab attivo, placeholder |
| testo | `#D4D4D4` | corpo |
| secondario | `#7A7A7A` | hint, footer, summary, attribuzioni |
| bordo | `#3A3A3A` | bordi box, separatori |
| errore | `#E85B4B` | errori brevi |
| successo | `#4BE87A` | conferma copia ("copied: ...") |
| `$surface`, `$surface-soft` | `#1A1A1A`, `#202020` | solo fallback se lo sfondo trasparente non e' ottenibile |

**Sfondo**: si tenta lo sfondo nativo del terminale (spike S-1: `ansi_color`/background trasparente in Terminal.app, iTerm2, Ghostty). Se non ottenibile per un widget, si usano solo i grigi neutri ammessi.

**Layout**: ogni schermata = Header (box `┌─ Leva ─...┐` con tagline in secondario) + corpo a box con titolo nel bordo superiore (`border_title`; bordo CSS `solid` di Textual, che disegna i box-drawing `┌ ┐ └ ┘ │ ─` richiesti; da confermare visivamente nello spike S-1, evitando `round`, `heavy`, `double` che usano altri glifi) + Footer (separatore `─` e shortcut in secondario) **sempre presente**, anche in schermate di errore e progress.

**Convenzioni nuove (da documentare nel design system prima dell'implementazione):**
1. Placeholder negli esempi: testo in accento; nell'esempio selezionato, accento + sottolineato. Rimane un solo colore accento per schermata.
2. Voce selezionata: accento + bold (unico bold ammesso), marcatore `>` in colonna 0 (carattere testuale, non icona).
3. Conferma copia: riga di stato nel footer-area in `#4BE87A`: `copied: <comando>`; la stessa informazione e' sempre testuale (non solo colore).
4. Errori: una riga `#E85B4B`, senza stack trace.
5. Mouse: click sulle righe, sulle schede (tab) e sugli esempi e' supportato; ogni azione col mouse ha un equivalente da tastiera.
6. Lingua dell'interfaccia: inglese (contenuti in inglese).

**Layout responsivo per split** (FR-19): >= 100 colonne due pannelli (lista | scheda); 60-99 colonne pannello singolo con navigazione lista -> scheda; < 60 colonne messaggio "terminal too narrow (min 60 cols)" con footer.

**Syntax**: niente colorazione multi-colore dei comandi: solo testo normale + placeholder in accento.

## Conseguenze

- Azione prima dell'implementazione (task #0): aggiornare `PyDF Tool/CLAUDE.md` con Textual come framework ammesso, le convenzioni 1-6 e l'elenco progetti (`leva-sh`). Questo agente non modifica quel file.
- Test snapshot (SVG) fissano il rispetto della palette: un test verifica che nessun colore fuori palette compaia nello stylesheet.
- Rischio: breaking changes di Textual sulle variabili di tema; mitigato dal pin `<9` e dagli snapshot.

## Alternative

- prompt_toolkit+rich (stack del design system): niente mouse/layout a pannelli comparabili; scartato.
- Tema Textual predefinito (`textual-dark`): viola le regole di palette; scartato.
- Sfondo `$surface` sempre: piu' semplice ma viola la regola "sfondo trasparente"; tenuto solo come fallback.
