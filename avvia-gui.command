#!/bin/bash
# Doppio click su questo file: apre il Terminale, avvia la GUI di pdf2md-pro
# e apre il browser. Lascia la finestra del Terminale aperta mentre lavori;
# per fermare il server chiudila o premi Ctrl+C.
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/pdf2md" ]; then
  echo "Ambiente non trovato. Prima esegui una volta:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -e ."
  echo ""
  echo "Premi Invio per chiudere."
  read -r
  exit 1
fi

echo "Avvio pdf2md-pro… (chiudi questa finestra per fermare il server)"
exec .venv/bin/pdf2md gui
