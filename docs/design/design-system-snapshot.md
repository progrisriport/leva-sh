# TUI Design System — Flosh

Questo file definisce l'identità visiva e le regole architetturali per tutte le
applicazioni TUI sviluppate con prompt_toolkit e rich. Va rispettato in ogni
modifica alla TUI, indipendentemente dal progetto.

---

## Palette colori

| Ruolo             | Valore        | Uso                                              |
|-------------------|---------------|--------------------------------------------------|
| Accento primario  | `#E8B84B`     | Titoli sezioni, voce selezionata, elementi attivi|
| Testo normale     | `#D4D4D4`     | Corpo testo, voci menu non selezionate           |
| Testo secondario  | `#7A7A7A`     | Sottotitoli, hint, descrizioni                   |
| Sfondo            | trasparente   | Mai impostare — usare il colore nativo del terminale |
| Bordi             | `#3A3A3A`     | Bordi box, separatori                            |
| Errore            | `#E85B4B`     | Messaggi di errore                               |
| Successo          | `#4BE87A`     | Conferme, operazioni completate                  |

**Estensioni approvate per Textual:** nei progetti che usano il framework Textual è permesso
definire variabili ausiliarie `$surface` (es. `#1A1A1A`) e `$surface-soft` (es. `#202020`)
per i container che richiedono uno sfondo esplicito a causa del rendering di Textual.
Queste variabili devono restare cromaticamente neutre (grigi scuri) e non aggiungere nuovi
colori semantici alla palette.

Regola: **un solo colore accento per schermata**. Non aggiungere altri colori
decorativi. La palette deve restare sobria — il giallo ambrato è riservato agli
elementi che richiedono attenzione attiva dell'utente.

**Sfondo**: non impostare mai `bg`, `background` o colori di sfondo espliciti
nei FormattedText, style strings, Panel di rich o container di prompt_toolkit.
Lo sfondo deve sempre ereditare dal terminale dell'utente.

---

## Tipografia e bordi

- Usare sempre caratteri box-drawing Unicode per i bordi: `─ │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼`
- I titoli delle sezioni vanno dentro il bordo superiore del box: `┌─ Titolo ─┐`
- Testo normale: nessun bold salvo per la voce attualmente selezionata nel menu
- Separatori orizzontali: `─` ripetuto a larghezza terminale, colore `#3A3A3A`
- Nessun emoji, nessuna icona grafica — solo testo e box-drawing

---

## Struttura layout

Ogni schermata TUI deve seguire questa struttura a zone:

```
┌─ Nome App ──────────────────────────────────────────┐
│ tagline o descrizione breve                          │
└──────────────────────────────────────────────────────┘

┌─ Sezione ────┐
│ contenuto    │
└──────────────┘

─────────────────────────────────────────────────────
↑↓ naviga   Invio conferma   Esc annulla   Q esce
```

- Header: nome app in bold + accento, tagline in testo secondario
- Corpo: uno o più box con bordi, titolo sezione in accento
- Footer: sempre presente, separatore + shortcut in testo secondario
- Mai eliminare il footer — è parte dell'identità visiva

---

## Regole architetturali (prompt_toolkit + rich)

Queste regole derivano dall'architettura esistente e non vanno violate:

1. **Menu e dialog**: sempre prompt_toolkit (`RadioList`, `checkboxlist_dialog`,
   `input_dialog`). Mai sostituire con componenti rich.

2. **Progress bar e output a scorrimento**: sempre rich. Mai usare prompt_toolkit
   per output progressivo.

3. **Non mescolare render**: prompt_toolkit e rich non vanno mai attivi nello
   stesso ciclo di render. Uno termina, l'altro inizia.

4. **Keybinding espliciti**: nessun monkey-patch su metodi interni di
   prompt_toolkit. Usare sempre `@kb.add(...)` con keybinding dichiarati.

5. **Validazione input**: validare sempre il path del file in ingresso prima di
   aprire qualsiasi dialog successivo, non alla fine del wizard.

---

## Stile interazione

- Feedback immediato su ogni azione (anche solo un separatore che appare)
- Messaggi di errore: brevi, in rosso, senza stack trace visibile all'utente
- Messaggi di successo: una riga, in verde, con il path del file output
- Nessun dialog di conferma per operazioni reversibili
- Dialog di conferma obbligatorio solo per operazioni distruttive

---

## Applicare questo design system

Quando modifichi una TUI in qualsiasi progetto:

1. Verifica che la palette rispetti i valori sopra — non inventare nuovi colori
2. Controlla che i bordi usino box-drawing Unicode, non trattini ASCII
3. Assicurati che header e footer siano presenti e coerenti
4. Non impostare mai colori di sfondo espliciti — sfondo sempre trasparente
5. Non introdurre dipendenze grafiche nuove senza aggiornare questo file
6. Se aggiungi una nuova convenzione visiva, documentala qui prima di
   implementarla

---

## Progetti che usano questo design system

- `pydf-tool` — CLI/TUI per OCR e compressione PDF su macOS
