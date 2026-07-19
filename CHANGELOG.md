# Changelog

## v0.25.0 — 2026-07-19
### ✨ Novità
- Aggiunto `gemini-3.5-flash` tra i modelli Gemini selezionabili in GUI

## v0.24.0 — 2026-07-19
### ✨ Novità
- Aggiunto Gemini come provider LLM diretto (senza passare da OpenRouter), con supporto a più chiavi API: quando una esaurisce la quota gratuita, la conversione passa automaticamente alla successiva senza fermarsi
- CLI: `--provider gemini` e `--api-key` (più chiavi separate da virgola)
### 🐛 Correzioni
- Rimosso dall'elenco dei modelli OpenRouter `nemotron-3-ultra` — verificato che non supporta le immagini ed era quindi inutilizzabile per l'estrazione OCR

## v0.23.0 — 2026-07-19
### ✨ Novità
- Adottato il pattern "LLM Wiki" (Karpathy) per la cartella di destinazione: ogni batch mantiene `index.md` (catalogo delle fonti con link e sommario) e `log.md` (registro cronologico di ogni estrazione, append-only)
- I file ottimizzati per second brain includono un seme di wikilink `[[argomento]]` per il graph di Obsidian
- La verifica Second Brain ora accetta anche un'intera cartella: controlla ogni fonte, segnala i file orfani non presenti nell'indice e i titoli duplicati

## v0.22.0 — 2026-07-19
### ✨ Novità
- Ogni file .md riporta ora, in coda al testo, che è stato estratto con pdf2md-pro, con quale motore, in quanto tempo e con quale configurazione avanzata (in sintesi) — anche gli stessi dati nel frontmatter per una ricerca strutturata
- Ogni conversione batch produce un report unico (`pdf2md-report_<data-ora>.md`) nella cartella di destinazione, con l'elenco di tutti i file estratti, pagine, motore usato, tempo, esito ed eventuali errori

## v0.21.0 — 2026-07-19
### ✨ Novità
- Il motore LLM ora mostra il progresso reale, pagina per pagina, invece di restare fermo allo 0% per l'intera durata di un file: banner con "pagina X/N" e tempo stimato rimanente calcolato sui tempi reali
- Nuovo badge "Ollama" nell'header: latenza in tempo reale, avviso se non raggiungibile o se il modello locale non è scaricato — visibile solo quando il motore locale è in uso
- Ogni pagina ha ora un timeout proprio (60s) con 2 tentativi automatici: un crash o blocco del motore locale su una singola pagina non tiene più in ostaggio l'intero file per minuti in silenzio, e il registro mostra i tentativi falliti

## v0.20.0 — 2026-07-19
### ✨ Novità
- Nuova opzione "🧠 Ottimizza per Second Brain" (GUI e CLI `--brain`): heading normalizzati su 4 livelli con un solo titolo H1, testo ricucito tra le pagine (sillabazioni e paragrafi spezzati), intestazioni e numeri di pagina ripetuti rimossi, properties per Obsidian/Logseq (tags, aliases, type) e attribution dello strumento nel file
- Nuova sezione "Second Brain" nella GUI: verifica se un file .md è già ottimizzato o da ottimizzare (8 criteri controllati) e spiega come dev'essere una fonte per un second brain
### 🐛 Correzioni
- Corretto il conteggio delle righe di provenienza quando una pagina non termina con newline
- Il frontmatter ora serializza correttamente le liste (tags, aliases)

## v0.19.0 — 2026-07-19
### ✨ Novità
- Il progetto è ora installabile come pacchetto (`pip install` dalla wheel), con licenza MIT e versione allineata automaticamente al log
- Aggiunta la pipeline CI (GitHub Actions): test su Linux e macOS, audit delle dipendenze e build del pacchetto a ogni push

## v0.18.1 — 2026-07-19
### 🐛 Correzioni
- Il registro della GUI non perde più righe nelle conversioni molto lunghe (oltre 500 eventi)
- I file con estensione maiuscola (`.PDF`) vengono ora riconosciuti
- Gli errori delle API cloud mostrano il messaggio reale invece di un errore criptico
- Eliminata una possibile corsa interna durante la lettura dello stato del job

## v0.18.0 — 2026-07-19
### ✨ Novità
- L'OCR ora funziona davvero: le pagine scansionate vengono lette con Tesseract (italiano + inglese). "Usa OCR solo se necessario" agisce solo sulle pagine senza testo, "Forza OCR" su tutte. Prima le due opzioni non avevano alcun effetto.

## v0.17.4 — 2026-07-19
### 🐛 Correzioni
- Corretto un blocco interno che congelava l'avanzamento dei job al primo evento: la GUI restava per sempre su "job in esecuzione" e serviva riavviare il server
- La chiave API non viene più salvata su disco nel file di ripresa; alla ripresa viene reinserita dal campo della GUI
- Il motore Ibrido ora rispetta le opzioni avanzate (margini, tabelle, DPI) anche sulle pagine native
- "Interrompi" ora completa davvero il file in corso prima di fermarsi, come promesso dalla finestra di conferma

## v0.17.3 — 2026-07-19
### 🐛 Correzioni
- Aggiornato `pip` nell'ambiente di sviluppo per risolvere 4 vulnerabilità note

## v0.17.2 — 2026-07-19
### 🐛 Correzioni
- Rimosso un import inutilizzato e aggiornato lo stato del progetto nel README

## v0.17.1 — 2026-07-19
### 🐛 Correzioni
- Corretto un bug che impediva il riavvio del server (crash all'avvio della GUI)

## v0.17.0 — 2026-07-19
### ✨ Novità
- Aggiunta la gestione avanzata di immagini e grafica: si possono ignorare le immagini, scartare quelle troppo piccole (loghi, icone) e limitare gli elementi vettoriali complessi per evitare blocchi su PDF tecnici/CAD

## v0.16.0 — 2026-07-19
### ✨ Novità
- Aggiunta l'opzione per scegliere se il nome file (in "rinomina per argomento") viene suggerito dall'LLM o da un'euristica sul testo

## v0.15.2 — 2026-07-19
### ♻️ Modifiche
- Migliorati i testi delle Opzioni Avanzate con spiegazioni semplici, senza gergo tecnico

## v0.15.1 — 2026-07-19
### 🐛 Correzioni
- Corretto un bug del banner di avanzamento che restava visibile per via della cache del browser

## v0.15.0 — 2026-07-19
### ✨ Novità
- Integrate le Opzioni Avanzate di estrazione (rimozione margini/cropbox, strategie tabelle, OCR con DPI configurabile)
- Aggiunta guida completa ai campi, blueprint interattivo e demo commerciale

## v0.14.0 — 2026-07-19
### ✨ Novità
- Aggiunto il pulsante "Riavvia Server" per un reset completo, con salvataggio automatico dell'avanzamento prima del riavvio

## v0.13.0 — 2026-07-19
### ✨ Novità
- Aggiunta l'interruzione immediata dei job e la possibilità di riprendere una conversione interrotta a metà

## v0.12.2 — 2026-07-19
### 🐛 Correzioni
- Corretto il pulsante di stop: ora evita doppi click e mostra un messaggio di attesa chiaro

## v0.12.1 — 2026-07-19
### 🐛 Correzioni
- Corretta la gestione dell'errore "un job è già in esecuzione", con riaggancio automatico allo stato corrente

## v0.12.0 — 2026-07-18
### ✨ Novità
- Aggiunta la possibilità di scegliere la cartella dove archiviare i PDF originali dopo il partizionamento

## v0.11.1 — 2026-07-18
### ♻️ Modifiche
- Il partizionamento ora lavora direttamente nella cartella di origine, spostando gli originali in una sottocartella `interi/`

## v0.11.0 — 2026-07-18
### ✨ Novità
- Aggiunta la selezione dei singoli file PDF da convertire in una cartella (checklist tutti/nessuno)
- Aggiunto il numero di versione visibile in GUI

## v0.10.1 — 2026-07-18
### ♻️ Modifiche
- I file convertiti mantengono di default il nome del PDF originale; la rinomina per argomento è ora un'opzione esplicita

## v0.10.0 — 2026-07-18
### ✨ Novità
- Aggiunti i controlli di pausa, ripresa e stop durante una conversione batch

## v0.9.1 — 2026-07-17
### 🐛 Correzioni
- Corretto un errore che bloccava le conversioni su drive esterni per via dei file nascosti macOS (`._nome.pdf`)

## v0.9.0 — 2026-07-17
### ✨ Novità
- Aggiunti gli script per installare la GUI come servizio sempre attivo su macOS, con avvio automatico al login

## v0.8.0 — 2026-07-17
### ✨ Novità
- Le impostazioni della GUI (cartelle, motore, provider, limiti) vengono ora salvate e ricaricate automaticamente
- Aggiunta l'opzione per ricordare la chiave API in modo esplicito (opt-in)

## v0.7.0 — 2026-07-17
### ✨ Novità
- Aggiunto un launcher a doppio click per avviare la GUI senza riga di comando

## v0.6.1 — 2026-07-17
### 🐛 Correzioni
- Corretti i messaggi di errore quando la GUI viene aperta come file locale invece che dal server

## v0.6.0 — 2026-07-17
### ✨ Novità
- Aggiunta l'analisi preliminare della cartella (pagine, MB, limiti superati) prima di convertire
- Aggiunta la selezione di cartelle/file tramite il Finder di macOS

## v0.5.0 — 2026-07-17
### ✨ Novità
- Aggiunta l'analisi automatica della cartella per individuare i PDF che superano i limiti di pagine o dimensione

## v0.4.0 — 2026-07-17
### ✨ Novità
- Aggiunto il supporto al motore LLM locale (GLM-OCR via Ollama) accanto a OpenRouter

## v0.3.0 — 2026-07-17
### ✨ Novità
- Aggiunta la conversione ibrida per pagina (nativa + LLM) e la conversione batch di intere cartelle
- Aggiunta la prima versione della GUI web locale

## v0.2.0 — 2026-07-17
### ✨ Novità
- Prima versione: conversione PDF → Markdown con provenienza per pagina, estrazione immagini e riga di comando
</content>
