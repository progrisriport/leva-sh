# DESIGN-STATUS — Leva (leva-sh)

- Data: 2026-11-20 · Versione: 0.1 · Stato: draft
- Doc: [PRD](PRD.md) · [ARCHITECTURE](ARCHITECTURE.md) · [DESIGN-PATTERNS](DESIGN-PATTERNS.md) · [DESIGN-IN-THE-SMALL](DESIGN-IN-THE-SMALL.md) · [TEST-STRATEGY](TEST-STRATEGY.md) · ADR/ADR-0001..0006

## Fasi
- [x] 1. Discovery — done (greenfield)
- [x] 2. Analysis — done
- [x] 3. Stack recommendation — done (ADR-0001)
- [x] 4. Architecture — done
- [x] 5. Design patterns — done
- [x] 6. Design-in-the-small — done
- [x] 7. Test strategy — done
- [x] 8. PRD assembly — done
- [ ] 9. Self-review — doing (eseguita sui doc presenti; fallimento annotato sotto)
- [ ] 10. Report — doing

## Self-review: fallimenti annotati
- `ANALYSIS.md` presente, salvato dopo la sessione di progettazione: i link nei doc non sono piu' pendenti.
- Check meccanici sui doc presenti: nessun marcatore di lavoro incompleto, nessuna sezione vuota, ogni FR/NFR tracciato in ARCHITECTURE sez. 7, nessuna contraddizione residua nota (corretto ADR-0003 vs schema).

## Quality gate
- Mantenibilità — pass (15 moduli a responsabilità singola, errori tipizzati, naming in DESIGN-IN-THE-SMALL)
- Riproducibilità — pass (uv.lock, LEVA_HOME, env fisso, fixture sintetiche, index_digest)
- Modularità — pass (grafo aciclico, Protocol, import-linter)
- Estensibilità — pass (ARCHITECTURE sez. 5)

## Blocking questions
- (nessuna)

## Non-blocking questions
- NB-1 Licenze codice (MIT) e contenuto (CC BY 4.0)
- NB-2 Aggiornare il design system `PyDF Tool/CLAUDE.md` per Textual e nuove convenzioni, prima della UI
- NB-3 Verificare licenza reale di tldr-pages (fonti discordanti BY / BY-SA)
- NB-4 Org/utente GitHub e nome del tap
- NB-5 Conferma lista comandi curati e priorità
- NB-6 Sezioni man oltre 1 e 8 in v1
- NB-7 Supporto Mac Intel
- NB-8 Versioni minime macOS 13 / Python 3.11
- NB-9 Riverificare nome `leva` su PyPI prima della publish
