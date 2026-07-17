# pdf2md-pro — Design

Data: 2026-07-17
Stato: approvato dall'utente (brainstorm in chat)

## Obiettivo

Strumento di conversione PDF → Markdown che superi gli strumenti esistenti
(PyMuPDF4LLM GUI, opengovsg/pdf2md, fchavelli/pdf2md) combinando tre cose che
nessun concorrente offre insieme:

1. **Routing ibrido per pagina** — motore scelto pagina per pagina (parser
   nativo / OCR / VLM), qualità da AI a costo da parser.
2. **Provenienza totale** — ogni blocco Markdown tracciato alla pagina (e in
   futuro al bounding box) del PDF sorgente, via sidecar JSON.
3. **Human-in-the-loop** — review UI side-by-side PDF↔MD con confidence per
   blocco (fase successiva).

## Decisioni

| Decisione | Scelta | Motivo |
|---|---|---|
| Forma | GUI locale + CLI, stessa pipeline | batch via CLI, review via GUI; niente SaaS |
| Motori | locale di default (PyMuPDF4LLM, OCR locale, VLM via Ollama); cloud opzionale | privacy-first, nessun lock-in |
| Linguaggio | Python 3.11+ | ecosistema PDF/ML |
| CLI | argparse (stdlib) | zero dipendenze extra |
| Qualità | corpus di test + harness di valutazione automatica | "migliore" deve essere misurabile |

## Architettura

```
pdf2md-pro/
├── src/pdf2md_pro/
│   ├── core/
│   │   ├── pipeline.py      # orchestrazione: classify → extract → assemble → validate
│   │   ├── classifier.py    # per pagina: nativa / scansione / complessa (Fase 2)
│   │   └── provenance.py    # blocco MD → pagina + hash sorgente (sidecar JSON)
│   ├── engines/
│   │   ├── base.py          # interfaccia comune Engine
│   │   ├── native.py        # pymupdf4llm
│   │   ├── ocr.py           # Tesseract/PaddleOCR (Fase 2)
│   │   └── vlm.py           # Ollama locale / Claude cloud (Fase 4)
│   ├── output/
│   │   └── writer.py        # MD + frontmatter YAML + assets immagini
│   └── cli.py               # argparse
├── eval/
│   ├── make_corpus.py       # genera PDF sintetici di test
│   ├── corpus/              # PDF + testo atteso (.expected.txt)
│   └── run_eval.py          # score similarità estratto vs atteso
├── tests/
└── docs/
```

### Interfaccia Engine

Ogni motore implementa: `convert(pdf_path, pages) -> list[PageResult]` dove
`PageResult = {page_number, markdown, images, confidence}`. La pipeline
assembla i PageResult, scrive il Markdown finale e il sidecar di provenienza.

### Sidecar di provenienza (`<nome>.provenance.json`)

```json
{
  "source": {"file": "doc.pdf", "sha256": "...", "pages": 12},
  "engine": {"name": "native", "version": "..."},
  "blocks": [
    {"page": 1, "engine": "native", "confidence": 1.0, "md_start_line": 1, "md_end_line": 40}
  ]
}
```

Fase 1: granularità a livello pagina. Bbox per blocco in fase successiva.

## Roadmap

| Fase | Contenuto | Criterio di uscita |
|---|---|---|
| 0 | Corpus sintetico + harness di valutazione | `run_eval.py` produce score per ogni PDF del corpus |
| 1 | Pipeline nativa + provenienza + immagini + CLI | `pdf2md file.pdf` produce .md + .provenance.json + assets; eval ≥ 0.9 sui PDF nativi |
| 2 | Classificatore pagina + OCR locale | scansioni convertite senza intervento |
| 3 | Layout intelligente (multi-colonna, header/footer, footnote, heading) | eval sui PDF multi-colonna sale |
| 4 | Tabelle doppia validazione + VLM + immagini semantiche | tabelle GFM corrette sul corpus |
| 5 | GUI review side-by-side con confidence | correzione umana per blocco |
| 6 | Batch, watch folder, REST API, template output, packaging | pip install + binario |

## Gestione errori

- PDF cifrato/corrotto → errore chiaro in CLI, exit code ≠ 0.
- Pagina che fallisce → non blocca il documento: blocco segnaposto nel MD,
  `confidence: 0` nel sidecar.
- Output mai sovrascritto silenziosamente: `--force` per sovrascrivere.

## Test

- pytest su core (provenance, writer, pipeline) con PDF generati al volo.
- Harness eval come regression suite: ogni fase deve mantenere o alzare gli score.
