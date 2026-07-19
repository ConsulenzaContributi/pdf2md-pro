# pdf2md-pro

![CI](https://github.com/ConsulenzaContributi/pdf2md-pro/actions/workflows/ci.yml/badge.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Version](https://img.shields.io/badge/version-0.19.0-orange)

Convertitore PDF → Markdown con routing ibrido per pagina e **provenienza
totale**: ogni blocco Markdown risale alla pagina del PDF sorgente tramite
sidecar JSON. Locale di default, privacy-first — nessun dato lascia la tua
macchina a meno che tu non scelga esplicitamente un provider cloud.

## ✨ Funzionalità

- **Motore nativo** (PyMuPDF4LLM) per PDF testuali: veloce, gratuito, offline
- **OCR reale** via Tesseract per pagine scansionate (italiano + inglese)
- **Motore LLM ibrido**: routing automatico per pagina fra parser nativo e
  vision-LLM su scansioni/pagine complesse
  - **GLM-OCR locale via Ollama** (default) — gratuito, tutto offline
  - **OpenRouter** (opzionale) — modelli cloud a scelta, con chiave API
- **Provenienza totale**: sidecar `.provenance.json` che lega ogni blocco
  Markdown a pagina sorgente, motore usato e confidence
- **Batch cartella → cartella** con rinomina automatica per argomento
- **Partizionatore PDF**: spezza automaticamente file oltre i limiti di
  pagine/MB richiesti dai motori LLM
- **GUI web locale**: drag & drop, opzioni avanzate di estrazione (cropbox,
  strategia tabelle, DPI, gestione immagini/grafica), pausa/ripresa/stop su
  job lunghi
- **CLI completa** per automazione e scripting

## 📦 Installazione

Da sorgente (sviluppo):

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Da pacchetto (uso):

```bash
python3 -m build                     # produce dist/pdf2md_pro-<ver>-py3-none-any.whl
pip install dist/pdf2md_pro-*.whl    # in qualsiasi ambiente Python >= 3.11
```

Per l'OCR serve [Tesseract](https://github.com/tesseract-ocr/tesseract)
(`brew install tesseract tesseract-lang` su macOS).

## 🚀 Uso

### Riga di comando

```bash
pdf2md documento.pdf -o output/          # converte, estrae immagini in output/assets/
pdf2md documento.pdf --pages 1-3,5       # solo alcune pagine
pdf2md documento.pdf --force             # sovrascrive output esistente
pdf2md documento.pdf --no-images         # solo testo

pdf2md batch cartella_pdf/ cartella_md/ --mode hybrid   # batch con routing ibrido
pdf2md split documento.pdf --max-pages 100              # partiziona un PDF grande
pdf2md gui                                               # avvia la GUI web locale
```

Output per `documento.pdf`:

- `documento.md` — Markdown con frontmatter YAML (sorgente, sha256, motore, data)
- `documento.provenance.json` — sidecar: per ogni blocco, pagina di origine,
  motore usato, confidence, righe nel Markdown
- `assets/` — immagini estratte, linkate in modo relativo

### Interfaccia grafica

La GUI è una pagina servita da un piccolo server locale: **serve un processo
in esecuzione**.

```bash
pdf2md gui                 # apre il browser su http://127.0.0.1:8347
pdf2md gui --no-open       # non apre il browser (uso come servizio)
```

Su macOS sono disponibili anche gli script `avvia-gui.command` (avvio manuale)
e `installa-servizio.command` (servizio sempre attivo, avvio al login).

> Aprire `index.html` col doppio click (indirizzo `file://`) **non** funziona:
> i pulsanti hanno bisogno del server.

## 🗺️ Roadmap

- [x] Pipeline nativa + provenienza + immagini + CLI
- [x] Classificatore pagina + motore LLM ibrido + batch + partizionatore + GUI
- [x] Configurazioni avanzate di estrazione (cropbox, tabelle, OCR reale, immagini/grafica)
- [x] Packaging + CI
- [ ] Layout intelligente (multi-colonna, header/footer, footnote)
- [ ] Tabelle con doppia validazione + immagini semantiche via VLM
- [ ] GUI review side-by-side con confidence

## 🧪 Test

```bash
.venv/bin/python -m pytest              # unit test
.venv/bin/python eval/make_corpus.py    # genera corpus sintetico
.venv/bin/python eval/run_eval.py       # score recall/similarità per documento
```

## ⚠️ Known issues

- Il routing ibrido classifica per pagina su base euristica (presenza di
  testo estraibile): pagine miste testo+scansione nella stessa pagina non
  sono ancora gestite a livello di sotto-blocco.
- I margini/cropbox non si applicano alle pagine instradate su OCR
  (riconoscimento a pagina intera).

## 🤝 Contributing

Issue e PR benvenuti. Prima di una PR: `pytest` verde e nessun secret nel diff.

## 📄 Licenza

MIT — vedi [LICENSE](LICENSE).
