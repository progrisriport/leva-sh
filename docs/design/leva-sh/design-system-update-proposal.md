# Design-system update proposal (NB-2)

- Project: Leva (`leva-sh`) · Date: 2026-11-22 · Task: T-0.7 · Status: proposal, awaiting U-2
- Related: [ADR-0005](ADR/ADR-0005-tui-textual-design-system.md) · [S-1](spikes/S-1-textual-background.md) · [UX](UX.md) · [DECISIONS](DECISIONS.md) (D-012, D-013, D-028..D-030) · [design system snapshot](../design-system-snapshot.md)

This document is a ready-to-apply proposal for updating the external Flosh TUI design system
(`/Users/flosh/Desktop/Coding.nosync/Progetti/PyDF Tool/CLAUDE.md`) so that it approves Textual
and the visual conventions Leva needs. The autonomous loop never edits that file. In U-2 the
user reviews the blocks below, applies the approved ones, and copies the result to
`docs/design/design-system-snapshot.md`; T-8.11 stays blocked until then.

The proposed text (section "Proposed text") is **Italian**, matching the external file. The
rest of this document is English (D-001). Line numbers refer to the current 118-line snapshot.

## Proposed text

Each block is the exact Markdown to insert or to use as a replacement; "Where to insert" says
where. Blocks P-1, P-2, P-4 and P-5 contain items that the user may approve one by one.

### P-1 Intro sentence (replace)

````markdown
Questo file definisce l'identità visiva e le regole architetturali per tutte le
applicazioni TUI sviluppate con prompt_toolkit e rich oppure con Textual. Va
rispettato in ogni modifica alla TUI, indipendentemente dal progetto.
````

### P-2 Estensioni approvate per Textual (replace)

````markdown
**Estensioni approvate per Textual:** i progetti che usano il framework Textual possono
ottenere lo sfondo in due modi.

- **Sfondo trasparente (preferito; obbligatorio per i progetti Textual nuovi e per
  `leva-sh`)**: lo sfondo resta quello nativo del terminale. Il tema usa `ansi=True` e
  `ansi_default` per `background`, `surface`, `panel` e `boost`; `ansi_default` è un reset,
  non un colore, ed è l'unico valore di `background:` ammesso nello stylesheet. Le variabili
  ausiliarie `$surface` (es. `#1A1A1A`) e `$surface-soft` (es. `#202020`) restano un ripiego
  solo per i widget per cui è dimostrato che non possono essere trasparenti; ogni uso va
  documentato nel progetto con il nome del widget e il motivo.
- **Container con sfondo neutro (approvato per i progetti esistenti, es. `pydf-tool`)**: le
  variabili `$surface` e `$surface-soft` definite nello stylesheet per i container che
  richiedono uno sfondo esplicito. Il progetto che modifica comunque il proprio tema può
  migrare allo sfondo trasparente; la migrazione non è richiesta.

In entrambi i casi le variabili devono restare cromaticamente neutre (grigi scuri) e non
aggiungere nuovi colori semantici alla palette.
````

### P-3 Regole architetturali (Textual) (new section)

````markdown
## Regole architetturali (Textual)

Valgono per i progetti che usano Textual. Le regole 1-4 della sezione prompt_toolkit + rich
non si applicano a Textual (menu, render e keybinding sono gestiti dal framework); la
regola 5 (validazione input) vale sempre.

Ogni regola indica a chi si applica: **[tutti]** = ogni progetto Textual, compresi quelli
esistenti; **[nuovi]** = progetti Textual nuovi e `leva-sh`. Un progetto esistente adotta le
regole [nuovi] solo se migra (vedi le estensioni approvate sopra).

1. **Un solo foglio di stile [tutti]**: un solo file `.tcss`; i colori si definiscono solo
   lì (e, nei progetti con un `Theme` Textual, nel `Theme`); nessun colore inline nei widget
   e nei markup.
2. **Tema con sfondo trasparente [nuovi]**: un solo `Theme` con `ansi=True`; `background`,
   `surface`, `panel` e `boost` valgono `ansi_default`. Le variabili `ansi-background` e
   `ansi-foreground` (`ansi_default`) sono obbligatorie: senza, l'app termina con un errore
   di stylesheet.
3. **Un solo `background:` [nuovi]**: l'unico valore ammesso per `background:` nello `.tcss`
   è `ansi_default`. Il ripiego `$surface` / `$surface-soft` segue quanto scritto nelle
   estensioni approvate sopra.
4. **Bordi `solid` [tutti]**: i bordi sono `border: solid` (disegna `┌ ┐ └ ┘ │ ─`) oppure
   `none` (non disegna nulla). Vietati `tall`, `wide`, `outer`, `round`, `heavy`, `double` e
   la barra `Underline` di `Tabs`, perché disegnano glifi fuori dal set ammesso.
5. **Titoli dei box [nuovi]**: si impostano con `border_title`, in colore accento. Il bold è
   ammesso solo per il titolo dell'header e per la voce selezionata.
6. **Header e footer custom [tutti]**: widget propri, non `Header` e `Footer` di Textual. Il
   feedback sta in una riga di stato o nel corpo della schermata, non nei toast; se un toast
   resta in uso ha bordo `solid` e nessuna barra colorata.
7. **Override dei default di Textual [nuovi]**: i default di alcuni widget introducono colori
   e glifi fuori palette e vanno sovrascritti nello `.tcss` del progetto: `Input` (bordo,
   cursore, placeholder), evidenziazione di `OptionList`, `Tabs` e `Tab` (barra nascosta, tab
   attivo in accento, inattivi in testo secondario), scrollbar (traccia trasparente) e
   `Toast`. Le regole esatte non stanno in questo file: si documentano nel progetto
   (per `leva-sh`: lo spike S-1 e `leva.tcss`).
8. **Nuovo widget, nuova verifica [tutti]**: prima di usare un widget non ancora verificato
   (`DataTable`, `Markdown`, `Select`, ...) si cattura l'output del terminale (sequenze SGR)
   e si controlla che contenga solo colori della palette e glifi ammessi. Il progetto
   mantiene un test automatico di palette e glifi.
9. **Colori hex e terminale [tutti]**: i colori hex richiedono un terminale truecolor
   (`COLORTERM=truecolor`); senza, Rich li degrada a 256 colori e la palette si altera.
   Verificare anche a mano su Terminal.app, iTerm2 e Ghostty con un profilo a sfondo pieno.

---

````

### P-4 Convenzioni visive (new section)

Numbering V-1..V-15 lets the user approve or reject each item individually. Tags: **[comune]**
= cross-project wording that `pydf-tool` already follows or can follow without change (checked
against its `tui.tcss` and `tui.py`); **[Leva]** = documented for `leva-sh` only, because
`pydf-tool` does something different or the item is Leva-specific (the user may prefer to keep
these in Leva's own docs instead). V-1..V-6 are ADR-0005 conventions 1..6; V-14 and V-15 are
the other ADR-0005 layout/syntax rules; V-7..V-13 come from UX.md, D-013 and D-028..D-030.

````markdown
## Convenzioni visive

Le voci marcate [comune] valgono per ogni progetto. Le voci marcate [Leva] descrivono scelte
specifiche di `leva-sh` (o di un progetto Textual nuovo che le adotti) e non vincolano gli
altri progetti.

1. **Segnaposto negli esempi [Leva]**: un segnaposto in un comando di esempio si mostra come
   `<nome>` in colore accento; nell'esempio selezionato è anche sottolineato. Resta un solo
   colore accento per schermata. Il comando copiato contiene il nome senza parentesi.
2. **Voce selezionata [Leva]**: colore accento + bold (unico bold ammesso nel corpo) e
   marcatore `>` in colonna 0. Il `>` è un carattere testuale, non un'icona. Altri progetti
   possono evidenziare la selezione in altro modo (es. bordo in accento).
3. **Conferma di copia [Leva]**: riga di stato vicino al footer, in `#4BE87A`, con
   l'oggetto copiato: `copied: <comando>`. L'informazione è sempre testuale, mai solo colore.
4. **Errori [comune]**: una sola riga in `#E85B4B`, senza stack trace (in `leva-sh`, nella
   riga di stato).
5. **Mouse [comune]**: se un'azione è disponibile col mouse (in `leva-sh`: click su righe,
   schede ed esempi), ha anche un equivalente da tastiera.
6. **Lingua dell'interfaccia [comune]**: è definita per progetto; per `leva-sh` è l'inglese,
   contenuti compresi.
7. **Badge [Leva]**: i badge sono testo tra parentesi quadre (`[curated]`, `[macos]`,
   `[builtin]`, `[tldr]`, `[bsd]`, `[zsh]`) in colore secondario; `(man)` marca una voce senza
   scheda curata. Nessuna icona.
8. **Riga `via:` [Leva]**: nelle righe dei risultati, una seconda riga in colore secondario
   `via: <intento>` spiega perché la voce è stata trovata.
9. **Avviso `[danger]` [Leva]**: sotto un comando pericoloso una riga `[danger] <motivo>` in
   colore accento (il giallo ambrato è già "attenzione attiva", nessun colore nuovo). Copiare
   il comando non è mai bloccato; la riga di stato mostra `copied (danger): <comando>` in
   colore accento invece che in verde. È l'unica eccezione a "successo = riga verde".
10. **Breadcrumb [Leva]**: l'header mostra la cronologia `search › tar`, con `›` come
    carattere testuale.
11. **Informazioni nel bordo superiore [Leva]**: l'header può mostrare a destra, nel bordo
    superiore, un'informazione di contesto in colore secondario (`macOS 27.2 · 2598 entries`);
    il box della scheda mostra il badge a destra nel proprio bordo superiore.
12. **Barra di avanzamento testuale [Leva]**: disegnata con i glifi `█` (accento) e `░`
    (secondario), mai con un colore di sfondo. Non sostituisce la regola `rich` o il
    `ProgressBar` di Textual degli altri progetti.
13. **Conferma leggera [comune]**: per un'operazione non distruttiva ma da non fare per
    sbaglio si preme due volte lo stesso tasto entro 3 secondi, con un suggerimento nella
    riga di stato (es. ricostruire l'indice: `r` due volte). Nessun dialog.
14. **Layout responsivo [Leva]**: a 100 colonne o più, due pannelli (lista e scheda); da 60 a
    99 colonne, un solo pannello con navigazione lista, scheda, `Esc` per tornare; sotto 60
    colonne (o 12 righe) il messaggio `terminal too narrow (min 60 cols)` con header e
    footer.
15. **Niente syntax highlighting [Leva]**: i comandi si mostrano in testo normale; l'unico
    altro colore ammesso è l'accento dei segnaposto (voce 1).

Esempio (Leva): voce selezionata, segnaposto, avviso di pericolo e riga di stato.

```
┌─ Examples ──────────────────────────────────────────────┐
│ > 1 Compress a folder into .tar.gz                      │
│     tar -czf <archive>.tar.gz <folder>                  │
│   4 Delete a folder and everything in it                │
│     rm -rf <folder>                                     │
│     [danger] deletes permanently, no Trash, no undo     │
└─────────────────────────────────────────────────────────┘
copied: tar -czf archive.tar.gz folder
─────────────────────────────────────────────────────────
↑↓ move   Enter open   c copy   q quit
```

---

````

### P-5 Stile interazione (replace the bullet list)

````markdown
- Feedback immediato su ogni azione (anche solo un separatore che appare)
- Messaggi di errore: brevi, in rosso, senza stack trace visibile all'utente
- Messaggi di successo: una riga, in verde, con l'oggetto dell'operazione (path del file
  output, comando copiato). Unica eccezione: l'avviso di pericolo (Convenzioni visive, voce 9)
- Messaggi di stato in una riga; maiuscole e lingua secondo il progetto (`leva-sh`: inglese e
  minuscolo, es. `copied: ls -la`, `clipboard unavailable`)
- Nessun dialog di conferma per operazioni reversibili (vedi anche Convenzioni visive, voce 13)
- Dialog di conferma obbligatorio solo per operazioni distruttive
````

### P-6 Progetti (append)

````markdown
- `leva-sh` — enciclopedia TUI (Textual) dei comandi shell di macOS
````

### P-7 Applicare questo design system (replace item 4, append item 7)

Replacement for item 4:

````markdown
4. Non impostare mai colori di sfondo espliciti — sfondo sempre trasparente (in Textual, nei
   progetti nuovi e in `leva-sh`: nessun `background:` diverso da `ansi_default`; i progetti
   esistenti seguono le estensioni approvate)
````

New item 7, appended after item 6:

````markdown
7. In un progetto Textual verifica che i bordi siano `solid` (o `none`), che i colori
   compaiano solo nello `.tcss` (e nel `Theme`, se presente) e che l'output di ogni widget
   nuovo sia stato controllato (regole Textual 1, 4 e 8)
````

## Where to insert

Target: the external file `.../PyDF Tool/CLAUDE.md` (118 lines at T-0.1; identical to
`docs/design/design-system-snapshot.md`). After applying, U-2 copies the result to
`docs/design/design-system-snapshot.md`.

| Block | Anchor in the external file | Action | Snapshot lines |
|---|---|---|---|
| P-1 | Paragraph starting "Questo file definisce l'identità visiva e le regole architetturali per tutte le" | Replace the paragraph | 3–5 |
| P-2 | Paragraph starting "**Estensioni approvate per Textual:** nei progetti che usano il framework Textual è permesso" | Replace the paragraph | 21–25 |
| P-4 | The blank line after the `---` that closes `## Struttura layout` (just before `## Regole architetturali (prompt_toolkit + rich)`) | Insert after that blank line; the block ends with `---` and a blank line, so the file keeps its `---` / blank / `##` rhythm | after 70 |
| P-3 | The blank line after the `---` that closes `## Regole architetturali (prompt_toolkit + rich)` (just before `## Stile interazione`) | Insert after that blank line; same rhythm | after 91 |
| P-5 | Bullet list under `## Stile interazione`, from "- Feedback immediato su ogni azione" to "- Dialog di conferma obbligatorio solo per operazioni distruttive" | Replace the list | 94–98 |
| P-7 | Item "4. Non impostare mai colori di sfondo espliciti — sfondo sempre trasparente" under `## Applicare questo design system`; and the end of the list, after item 6 ("6. Se aggiungi una nuova convenzione visiva, documentala qui prima di implementarla") | Replace item 4; append item 7 | 109; after 112 |
| P-6 | End of `## Progetti che usano questo design system`, after "- `pydf-tool` — CLI/TUI per OCR e compressione PDF su macOS" | Append | after 118 |

Apply from the bottom up (P-6, P-7, P-5, P-3, P-4, P-2, P-1) so the line numbers above stay
valid. Unchanged: the palette table, the `Sfondo` rule paragraphs (lines 27–33),
`## Tipografia e bordi`, `## Struttura layout`, the prompt_toolkit + rich rules 1–5.

## Diff summary

| Kind | What |
|---|---|
| Changed | Intro now names Textual (P-1); the Textual extension paragraph names two approved approaches: transparent background (preferred, required for new projects and `leva-sh`) and neutral `$surface` containers (kept for existing projects) (P-2); success messages carry the operation's object and status-message case/language is per project (P-5); checklist item 4 gets a Textual clause (P-7) |
| Added | `## Regole architetturali (Textual)` with 9 rules, each tagged [tutti] or [nuovi] (P-3); `## Convenzioni visive` with 15 numbered items tagged [comune] or [Leva] (P-4); checklist item 7 (P-7); `leva-sh` in the project list (P-6) |
| Unchanged | Palette values and roles; "one accent per screen"; box-drawing set and rules in `## Tipografia e bordi`; header/body/footer zones in `## Struttura layout`; prompt_toolkit + rich rules 1–5; "no dialog for reversible operations"; "confirmation dialog only for destructive operations"; checklist items 1–3, 5, 6 |

No colour is added: every hex in the proposed text is one of `#E8B84B`, `#D4D4D4`, `#7A7A7A`,
`#3A3A3A`, `#E85B4B`, `#4BE87A` or the two fallback greys `#1A1A1A`, `#202020`.

### Impact on pydf-tool

`pydf-tool` (`PyDF Tool/src/pydf_tool/`) is already a Textual app: one `tui.tcss` (`CSS_PATH`)
with the palette as stylesheet variables, `$surface`/`$surface-soft` container backgrounds,
`border: solid` plus `border: none`, custom header and footer widgets, a Textual `ProgressBar`,
no `Theme`, no `border_title`, no toasts, no colours inline in `tui.py`. Its selection is an
accent border with a `$surface-soft` fill, and its status messages are Italian and capitalised.
The proposal was scoped so that applying it leaves it compliant.

| Block | Impact on `pydf-tool` |
|---|---|
| P-1 | None |
| P-2 | None: its `$surface` approach is named as an approved existing-project approach; migration to `ansi=True` is optional (see open questions) |
| P-3 | None: rules 1, 4, 6, 8, 9 are [tutti] and it meets them (single `.tcss` with the colours, `solid`/`none` borders, custom header/footer, no toasts); rules 2, 3, 5, 7 are [nuovi] and bind it only if it migrates. Rule 8 and the manual check of rule 9 are forward-looking: they apply to widgets added from now on |
| P-4 | None: only [comune] items bind it (V-4 errors, V-5 mouse, V-6 language per project, V-13 double press, all satisfiable as written); its accent-border selection and `ProgressBar` are no longer contradicted because V-2 and V-12 are [Leva] |
| P-5 | None: success wording generalises "path of the output file" and keeps it as an example; case and language of status messages are per project, so its capitalised Italian messages stay valid |
| P-6 | None |
| P-7 | None: item 4's Textual clause exempts existing projects; item 7 asks for `solid` or `none` borders, colours only in the `.tcss`, and checks on new widgets |

Side note, not part of the proposal: `tui.tcss` also defines an extra `$surface-accent`
variable that is defined but never used. It is a third surface variable outside the two
approved ones; the proposal does not change that, but the next time `pydf-tool`'s stylesheet
is touched it should be removed or documented.

## Rationale

- **Checklist rule 5 (no new graphic dependency without updating this file).** Textual is
  already used (`pydf-tool`) and the file already carries a short Textual extension paragraph,
  but Textual is not yet an approved framework with rules of its own: the intro and the rules
  still name only prompt_toolkit and rich (ADR-0005 Context and Consequences). Leva adds a
  second Textual project with stricter needs, so rule 5 still motivates P-1, P-3 and P-6.
  The proposal is written to extend what `pydf-tool` relies on, not to replace it: see
  "Impact on pydf-tool".
- **Checklist rule 6 (document a new visual convention before implementing it).** ADR-0005
  lists conventions 1–6 as "to document in the design system before implementation"; V-1..V-6
  are those. UX.md and D-028..D-030 added visual elements after the ADR (badges, `via:` line,
  danger line, breadcrumb, top-border info, text progress bar); rule 6 applies to them too, so
  they are V-7..V-12. T-8.11 (placeholder highlighting, `>` marker) cannot start until this is
  applied (U-2). Documenting a convention here does not make it binding on other projects:
  items that `pydf-tool` does differently (V-2 selection marker, V-12 text progress bar) or
  that are plainly Leva's (V-3, V-14, V-15) are tagged [Leva].
- **S-1 evidence for P-2 and P-3.** Finding 1: the `ansi=True` theme with `ansi_default`
  backgrounds passes the palette gate (rules 2, 3). Finding 2: no widget needed the
  `$surface` fallback, so for new projects the design system keeps it as a documented
  fallback only (P-2); for existing projects the neutral-container approach stays approved,
  because `pydf-tool` is built on it.
  Finding 4: `ansi-background` and `ansi-foreground` are mandatory (rule 2). Findings 3, 5,
  6, 7, 8, 9: Textual's own defaults inject ANSI-palette colours, `tall`/`outer` borders and
  `Underline` glyphs, so the overrides are required and the component classes, not
  `$surface`, are the lever (rules 4, 7). Finding 10: colour needs `COLORTERM=truecolor`
  (rule 9). Finding 11: header title as `border_title`, bold only there (rule 5). Rule 8
  rests on the S-1 method (SGR capture plus palette and glyph gate) and on finding 3. S-1
  finding 12 is "not verified here": it is the terminal-rendering check still open as U-1,
  and backs only the manual-check sentence of rule 9. The CSS itself is not copied into the
  design system: it lives in S-1 and in `leva.tcss`, and the design system states rules only.
- **Why rules 1–4 of the prompt_toolkit + rich section are declared not applicable.** They
  prescribe prompt_toolkit/rich components and render cycles (ADR-0005, Context); leaving them
  unqualified would make any Textual project violate the file on day one. Rule 5 is
  framework-independent and stays.
- **Why P-3 and P-4 carry scope tags.** `pydf-tool` is a compliant Textual project today, with
  a different background approach, selection style and progress bar. Tags let the file approve
  Leva's stricter transparent-background approach without declaring the existing project
  non-compliant; only [tutti] and [comune] items bind it, and each of them already holds
  (Diff summary, "Impact on pydf-tool").
- **D-028 and V-1.** ADR-0005 convention 1 said "accent, underlined when selected"; D-028 fixed
  the display as `<name>` while storage stays `{{name}}` and the copy has no brackets.
- **D-029, V-8.** The `via:` line explains an intent match; it uses the secondary role, so it
  adds no colour.
- **D-030, V-9, and why one accent still holds.** The danger line and the `copied (danger):`
  status reuse the accent ("attention") instead of adding a warning colour, so a screen
  still has exactly one accent colour; copy is never blocked. The cost is an exception to
  "success = green line" (P-5), stated explicitly so it is not read as a violation.
- **D-013, V-13, P-5.** Rebuild is non-destructive; the design system forbids confirmation
  dialogs for reversible operations, so the double key press with a status-line hint is
  documented as the approved lightweight pattern.
- **P-5 wording.** The current rule asks for "the path of the output file", which fits PDF
  tools but not a clipboard action; the generalisation to "the object of the operation"
  keeps the path as an example, so `pydf-tool` stays compliant. Lowercase English status
  messages come from the project rule in CLAUDE.md (`copied: ls -la`); `pydf-tool` uses
  capitalised Italian ones, so case and language are left to each project and the example
  names `leva-sh`.
- **ADR-0005 Consequences.** The ADR also states that a palette test pins compliance; rules 7
  and 8 and checklist item 7 are the design-system side of that test.
- **Still pending: U-1.** The automated S-1 checks passed; the manual check in Terminal.app,
  iTerm2 and Ghostty has not been done. Rule 9 asks for it as a standing requirement. If U-1
  shows a widget that cannot be transparent, the P-2 fallback applies and the widget is
  documented in the project, with no change to this proposal.

## Open questions for the user

- **Danger exception (V-9, P-5).** Accept `copied (danger): <cmd>` in the accent colour as the
  one exception to "success = green line"? Alternative: green text with a `(danger)` word
  only, losing the visual cue (UX §3.3 and D-030 chose the accent).
- **Cross-project or Leva-only.** Should the [Leva] items (V-1..V-3, V-7..V-12, V-14, V-15)
  live in the shared design system, or stay in Leva's own docs (ADR-0005, UX.md) with the
  design system keeping only the [comune] ones? Rule 6 asks for documentation "here" before
  implementing, which is why they are proposed; rejecting any of them means T-8.11 must be
  re-planned for it.
- **Language rule (V-6).** Is the wording "defined per project; `leva-sh`: English" acceptable
  as a cross-project rule, given that `pydf-tool` is Italian?
- **Future of pydf-tool's background approach.** Should `pydf-tool` later migrate to the
  transparent `ansi=True` approach (P-2, rules 2–3), or should the neutral `$surface`
  container approach stay a permanent second option? The proposal allows both and requires
  nothing of `pydf-tool` now.
- **Text glyphs.** Are `›` (breadcrumb), `·` (separator in the top-border info) and `█` `░`
  (progress bar) acceptable as "text characters" under "only text and box-drawing"? They are
  not box-drawing, and the design system lists no other glyph than the arrows in its footer
  sample.
- **Extra rules.** V-14 (responsive layout) and V-15 (no syntax highlighting) come from
  ADR-0005 Decision, not from its conventions 1–6; keep them in the design system or drop them?
