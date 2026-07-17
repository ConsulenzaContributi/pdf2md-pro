#!/bin/bash
# Doppio click: installa pdf2md-pro come servizio sempre attivo (LaunchAgent).
# Da qui in poi la GUI è SEMPRE raggiungibile su http://127.0.0.1:8347/,
# parte da sola al login e si riavvia da sola se si blocca.
# Per fermarla: doppio click su 'ferma-servizio.command'.
cd "$(dirname "$0")" || exit 1
PROJ="$(pwd)"
BIN="$PROJ/.venv/bin/pdf2md"
LABEL="pro.pdf2md.gui"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PORT=8347

if [ ! -x "$BIN" ]; then
  echo "Ambiente non trovato. Prima esegui una volta:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -e ."
  echo ""
  echo "Premi Invio per chiudere."
  read -r
  exit 1
fi

# libera la porta se un server è già in ascolto (verrà rimpiazzato dal servizio)
lsof -ti ":$PORT" | xargs kill 2>/dev/null

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$BIN</string>
    <string>gui</string>
    <string>--port</string><string>$PORT</string>
    <string>--no-open</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJ</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/pdf2md-gui.log</string>
  <key>StandardErrorPath</key><string>/tmp/pdf2md-gui.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null
if launchctl load "$PLIST"; then
  sleep 2
  echo "Servizio installato. GUI sempre attiva su http://127.0.0.1:$PORT/"
  open "http://127.0.0.1:$PORT/"
else
  echo "Errore nel caricare il servizio. Log: /tmp/pdf2md-gui.log"
fi
echo ""
echo "Premi Invio per chiudere."
read -r
