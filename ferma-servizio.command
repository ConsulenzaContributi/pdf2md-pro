#!/bin/bash
# Doppio click: ferma e rimuove il servizio sempre-attivo di pdf2md-pro.
LABEL="pro.pdf2md.gui"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl unload "$PLIST" 2>/dev/null
rm -f "$PLIST"
lsof -ti ":8347" | xargs kill 2>/dev/null
echo "Servizio rimosso. La GUI non partirà più in automatico."
echo ""
echo "Premi Invio per chiudere."
read -r
