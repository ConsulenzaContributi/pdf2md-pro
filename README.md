# pdf2md-pro

Convertitore PDF → Markdown con routing ibrido per pagina e **provenienza
totale**: ogni blocco Markdown risale alla pagina del PDF sorgente tramite
sidecar JSON. Locale di default, privacy-first.

Stato: **Fase 2** — pipeline nativa + motore LLM ibrido per pagina, batch con
rinomina per argomento, partizionatore PDF, GUI web locale.

Motori LLM (per scansioni e pagine complesse):
- **GLM-OCR locale via Ollama** (default): `ollama pull glm-ocr` — gratuito,
  tutto offline. CLI: `--provider glmocr` (implicito).
- **OpenRouter** (opzionale): `--provider openrouter` + `OPENROUTER_API_KEY`,
  modello a scelta (es. `nvidia/nemotron-3-ultra-550b-a55b:free`).
Roadmap completa in [docs/superpowers/specs/2026-07-17-pdf2md-pro-design.md](docs/superpowers/specs/2026-07-17-pdf2md-pro-design.md).

## Installazione

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Interfaccia grafica

**Doppio click su `avvia-gui.command`**: apre il Terminale, avvia il server e
apre il browser da solo. Lascia quella finestra del Terminale aperta mentre
lavori; per fermare, chiudila o premi Ctrl+C.

In alternativa da terminale:

```bash
.venv/bin/pdf2md gui        # apre http://127.0.0.1:8347/
```

> La GUI funziona **solo** avviata così. Aprire `index.html` col doppio click
> (indirizzo `file://`) non funziona: i pulsanti hanno bisogno del server.
> Se il browser dice "Connessione negata"/`ERR_CONNECTION_REFUSED`, il server
> non è in esecuzione — rilancia `avvia-gui.command`.

## Uso da riga di comando

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
