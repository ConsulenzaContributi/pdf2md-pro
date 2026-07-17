# pdf2md-pro

Convertitore PDF → Markdown con routing ibrido per pagina e **provenienza
totale**: ogni blocco Markdown risale alla pagina del PDF sorgente tramite
sidecar JSON. Locale di default, privacy-first.

Stato: **Fase 2** — pipeline nativa + motore LLM via OpenRouter (ibrido per
pagina), batch con rinomina per argomento, partizionatore PDF, GUI web locale.
Roadmap completa in [docs/superpowers/specs/2026-07-17-pdf2md-pro-design.md](docs/superpowers/specs/2026-07-17-pdf2md-pro-design.md).

## Installazione

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Uso

```bash
pdf2md documento.pdf -o output/          # converte, estrae immagini in output/assets/
pdf2md documento.pdf --pages 1-3,5       # solo alcune pagine
pdf2md documento.pdf --force             # sovrascrive output esistente
pdf2md documento.pdf --no-images         # solo testo
```

Output per `documento.pdf`:

- `documento.md` — Markdown con frontmatter YAML (sorgente, sha256, motore, data)
- `documento.provenance.json` — sidecar: per ogni blocco pagina di origine,
  motore usato, confidence, righe nel Markdown
- `assets/` — immagini estratte, linkate in modo relativo

## Test e valutazione

```bash
.venv/bin/python -m pytest              # unit test
.venv/bin/python eval/make_corpus.py    # genera corpus sintetico
.venv/bin/python eval/run_eval.py       # score recall/similarità per documento
```

Ogni fase di sviluppo deve mantenere o alzare gli score dell'harness.
