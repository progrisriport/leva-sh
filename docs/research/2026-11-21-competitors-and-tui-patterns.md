# Ricerca: competitor terminal-native e pattern TUI — 2026-11-21

Fonte: agente di ricerca (Sonnet) + verifiche puntuali. "~" = da conoscenza pregressa, non verificato in sessione.

## Sintesi
- I **man viewer TUI** (qman, lazyman, manora, mantui, mandible, smartman-cli in Textual) mostrano il man page impaginato meglio: niente contenuto curato per principianti, niente note BSD/GNU, niente copia pensata per il pannello affiancato.
- Gli **strumenti di esempi** (tldr/tealdeer/tlrc, navi, cheat, cheat.sh) non hanno copertura enciclopedica né vista man/sottocomandi.
- **Concorrente più vicino**: [lcl — Linux Command Library](https://linuxcommandlibrary.com/man/lcl). TUI interattiva offline, 6200+ comandi, categorie, vim keys. Ma è **Linux/GNU-centrico** (contenuto preconfezionato, non le man page locali del Mac) → flag BSD errati per macOS. Non su Homebrew (verificato 2026-11-21).
- **Differenziazione di Leva confermata**: macOS-native (indice dalle man page locali = flag corretti per la versione installata) + layer curato per principianti + note BSD/GNU e zsh/bash + copia nel flusso shell affiancata.

## Competitor (dettaglio)
| Strumento | UX | Da rubare | Da evitare |
|---|---|---|---|
| tldr (tealdeer, tlrc) ~ | `tldr tar` stampa esempi | Formato descrizione + comando con `{{placeholder}}` | Nessun browse/ricerca per intento |
| tldr++ ~ | TUI, compila placeholder ed esegue | Compilazione placeholder prima della copia | Esecuzione diretta |
| [navi](https://github.com/denisidoro/navi) | Widget fzf, compila argomenti, inserisce in riga di comando | Argomenti dinamici, inserimento shell | Sintassi `.cheat`, curva alta |
| cheat ~ | Cheatsheet personali | Personalizzazione | Nessuna UI |
| cheat.sh ~ | `curl cheat.sh/tar` | Query brevi | Rete, qualità variabile |
| howdoi / how2 ~ | Domanda → risposta web/LLM | Flusso "I forgot how to X" | Non verificato, rete |
| explainshell ~ | Scompone un comando flag per flag | Spiegazione per flag | Web, GNU |
| fzf + man ~ | `man -k . \| fzf --preview` | Velocità, anteprima a lato | Grezzo, nessuna guida |
| Dash ~ | Ricerca docset offline | Ricerca prefix-first istantanea | GUI |
| Warp Workflows ~ | Workflow con argomenti | Placeholder con descrizione/default | Terminale proprietario |
| gh copilot ~ | LLM suggest/explain | "Spiega questo comando" | Non deterministico, allucina flag BSD |

Man viewer TUI trovati: [qman](https://github.com/plp13/qman), [lazyman](https://pkg.go.dev/github.com/shuklasaharsh/lazyman), [manora](https://raw.githubusercontent.com/Antiz96/manora/v2.2.6/README.md), [mantui](https://github.com/preiter93/mantui), [mandible](https://docs.rs/crate/mandible/0.2.0), [smartman-cli](https://dev.to/yash_ambaskar_c13cc5c5f10/i-replaced-the-man-command-with-a-python-tui-and-its-actually-useful-1h7h) (Textual), [mangl](https://github.com/zigalenarcic/mangl), [Mukette](https://github.com/Chubek/Mukette), [ozil](https://github.com/typesanitizer/ozil). Rassegna: [It's FOSS](https://itsfoss.com/man-pages-like-tools/).

## Pattern TUI (~ da lazygit, k9s, btop, yazi, gitui, posting, harlequin, Mole, superfile, Charm)
- Layout: header con contesto/breadcrumb, corpo a pannelli titolati nel bordo, footer con tasti contestuali.
- Tasti: `/` cerca, `?` help, `Ctrl-P` palette, `j/k` + frecce, `Esc` indietro, `Enter` apre, `c` copia, `[`/`]` cronologia.
- Scoperta: footer che cambia col pannello, help overlay ricercabile.
- Stati vuoti: "nessun risultato per X — prova Y".
- Primo avvio: progresso con testo + uso immediato dei curati mentre il resto indicizza.
- Larghezza: due pannelli ≥100 col, stack a pannello singolo sotto.
- Mouse: click seleziona, click su esempio copia, rotella scorre.

## Concept di interazione
1. **Launcher search-first** — input unico, risultati, Enter apre. Veloce, perfetto in stretto; scoperta debole.
2. **Tre pannelli** (categorie / lista / dettaglio) — scoperta ottima; non entra nel pannello affiancato.
3. **Card + cronologia** — scheda a tutta altezza, stack di navigazione, recenti in home. Ottimo per copia.

Raccomandazione agente: 1 come cuore + 3 come destinazione; 2 solo come vista secondaria a larghezza adeguata.

## Idee originali candidate
1. Ricerca per intento con sinonimi curati, offline e deterministica.
2. Marcatura BSD/GNU per ogni esempio con equivalente (`sed -i ''`, `date -d`, `readlink -f`).
3. Placeholder evidenziati e compilabili prima della copia, valori ricordati; mai esecuzione.
4. Avvisi di pericolo sugli esempi distruttivi con spiegazione.
5. "Spiega questo comando": incolli una riga, Leva la scompone con i dati locali (explainshell offline, BSD).

## Limiti
Ricerca web ridotta (3 query). Part B e diversi competitor non verificati in sessione.
