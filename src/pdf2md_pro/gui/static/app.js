"use strict";

const $ = (id) => document.getElementById(id);
const banner = $("banner");
const bannerFill = $("banner-fill");
const bannerLabel = $("banner-label");
const bannerCount = $("banner-count");
const log = $("log");
const startBtn = $("start");
const splitBtn = $("split-start");
const analyzeBtn = $("analyze-start");
const convertPartsBtn = $("convert-parts");
const bannerControls = $("banner-controls");
const pauseBtn = $("pause-btn");
const resumeBtn = $("resume-btn");
const stopBtn = $("stop-btn");

let pollTimer = null;
let renderedEvents = 0;

// La GUI deve girare tramite il server (`pdf2md gui`): aperta come file
// locale, le chiamate /api/* falliscono con "Failed to fetch".
const OFFLINE = location.protocol === "file:";
const OFFLINE_MSG =
  "Questa pagina è stata aperta come file. Avviala dal terminale con "
  + "'pdf2md gui' (si apre su http://127.0.0.1:8347) — solo così i pulsanti funzionano.";

function offlineBlocked() {
  if (OFFLINE) {
    addLog(OFFLINE_MSG, "err");
    return true;
  }
  return false;
}

// "Failed to fetch" (TypeError) = server non raggiungibile: messaggio utile.
function fetchErrorText(err) {
  if (err instanceof TypeError) {
    return OFFLINE
      ? OFFLINE_MSG
      : "Server non raggiungibile: la finestra 'pdf2md gui' è ancora attiva nel terminale?";
  }
  return err.message;
}

function checkedValue(name) {
  const el = document.querySelector(`input[name="${name}"]:checked`);
  return el ? el.value : null;
}

function syncConditionalFields() {
  $("llm-fields").hidden = checkedValue("mode") === "native";
  const provider = checkedValue("provider");
  $("glmocr-fields").hidden = provider !== "glmocr";
  $("openrouter-fields").hidden = provider !== "openrouter";
  $("gemini-fields").hidden = provider !== "gemini";
  syncOllamaBadge();
}

document
  .querySelectorAll('input[name="mode"], input[name="provider"]')
  .forEach((radio) => radio.addEventListener("change", syncConditionalFields));

// --- Badge salute Ollama: visibile solo quando il motore locale è in gioco ---
const ollamaBadge = $("ollama-badge");
let ollamaPollTimer = null;

function syncOllamaBadge() {
  const usesOllama = checkedValue("mode") !== "native" && checkedValue("provider") === "glmocr";
  if (usesOllama) {
    ollamaBadge.hidden = false;
    if (!ollamaPollTimer) {
      pollOllamaHealth();
      ollamaPollTimer = setInterval(pollOllamaHealth, 5000);
    }
  } else {
    ollamaBadge.hidden = true;
    clearInterval(ollamaPollTimer);
    ollamaPollTimer = null;
  }
}

function pollOllamaHealth() {
  if (OFFLINE) return;
  const url = $("ollama-url").value.trim() || "http://127.0.0.1:11434";
  const model = $("local-model").value.trim();
  fetch(`/api/ollama-health?url=${encodeURIComponent(url)}&model=${encodeURIComponent(model)}`, { cache: "no-store" })
    .then((r) => r.json())
    .then((d) => {
      if (!d.reachable) {
        ollamaBadge.textContent = "⏺ Ollama: non raggiungibile";
        ollamaBadge.style.borderColor = "var(--err)";
        ollamaBadge.style.color = "var(--err)";
        ollamaBadge.title = "Ollama non risponde su " + url + " — verifica che sia avviato ('ollama serve').";
        return;
      }
      const loaded = d.model_loaded;
      ollamaBadge.textContent = `⏺ Ollama ${d.latency_ms}ms${loaded === false ? " · modello assente" : ""}`;
      ollamaBadge.style.borderColor = loaded === false ? "var(--accent)" : "";
      ollamaBadge.style.color = loaded === false ? "var(--accent)" : "";
      ollamaBadge.title = loaded === false
        ? `Ollama attivo, ma il modello '${model}' non risulta scaricato: ollama pull ${model}`
        : `Ollama attivo su ${url}, ${d.models.length} modelli disponibili`;
    })
    .catch(() => {
      ollamaBadge.textContent = "⏺ Ollama: errore verifica";
      ollamaBadge.style.borderColor = "var(--err)";
      ollamaBadge.style.color = "var(--err)";
    });
}

// --- Persistenza impostazioni (localStorage, per questo browser locale) ---
const CONFIG_KEY = "pdf2md-pro:config:v1";
const TEXT_IDS = [
  "local-model", "ollama-url", "model", "gemini-model", "source-dir", "dest-dir", "max-files",
  "split-pages", "split-mb", "split-input", "split-interi",
  "tool-max-pages", "tool-max-mb", "adv-margins", "adv-table-strategy", "adv-dpi",
  "adv-image-size-limit", "adv-graphics-limit", "brain-file"
];
const CHECK_IDS = ["extract-images", "auto-split", "rename-topic", "llm-topic", "adv-use-ocr", "adv-force-ocr", "adv-ignore-images", "brain-optimize"];
const RADIO_NAMES = ["mode", "provider"];

function saveConfig() {
  const cfg = { text: {}, check: {}, radio: {} };
  TEXT_IDS.forEach((id) => { cfg.text[id] = $(id).value; });
  CHECK_IDS.forEach((id) => { cfg.check[id] = $(id).checked; });
  RADIO_NAMES.forEach((name) => { cfg.radio[name] = checkedValue(name); });
  // le chiavi API ora vengono salvate in .env, non più in localStorage
  cfg.text["api-key"] = "";
  cfg.text["gemini-api-key"] = "";
  try {
    localStorage.setItem(CONFIG_KEY, JSON.stringify(cfg));
  } catch { /* storage pieno o disabilitato: si prosegue senza persistenza */ }
}

function restoreConfig() {
  let cfg;
  try {
    cfg = JSON.parse(localStorage.getItem(CONFIG_KEY) || "null");
  } catch { cfg = null; }
  if (!cfg) return;
  Object.entries(cfg.text || {}).forEach(([id, v]) => { if ($(id) != null) $(id).value = v; });
  Object.entries(cfg.check || {}).forEach(([id, v]) => { if ($(id) != null) $(id).checked = v; });
  Object.entries(cfg.radio || {}).forEach(([name, v]) => {
    const el = document.querySelector(`input[name="${name}"][value="${v}"]`);
    if (el) el.checked = true;
  });
  $("api-key").value = "";
  $("gemini-api-key").value = "";
  syncConditionalFields();
}

restoreConfig();
// salva a ogni modifica di qualunque campo del form
document.querySelectorAll("input, select, textarea").forEach((el) => {
  el.addEventListener("change", saveConfig);
  el.addEventListener("input", saveConfig);
});
[$("ollama-url"), $("local-model")].forEach((el) => el.addEventListener("change", syncOllamaBadge));

// carica configurazione .env all'avvio
fetch("/api/load-env")
  .then((r) => r.json())
  .then((env) => {
    if (env.OPENROUTER_API_KEY) $("api-key").value = env.OPENROUTER_API_KEY;
    if (env.OPENROUTER_DEFAULT_MODEL) $("model").value = env.OPENROUTER_DEFAULT_MODEL;
    if (env.GEMINI_API_KEY) $("gemini-api-key").value = env.GEMINI_API_KEY;
    if (env.GEMINI_DEFAULT_MODEL) $("gemini-model").value = env.GEMINI_DEFAULT_MODEL;
  })
  .catch(() => {});

// Pulsanti Salva in .env
$("save-openrouter-env-btn").addEventListener("click", () => {
  const payload = {
    OPENROUTER_API_KEY: $("api-key").value.trim(),
    OPENROUTER_DEFAULT_MODEL: $("model").value.trim()
  };
  fetch("/api/save-env", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
    .then(r => {
      if (r.ok) {
        addLog("Configurazione OpenRouter salvata nel file .env locale.", "ok");
      } else {
        addLog("Errore durante il salvataggio in .env", "err");
      }
    });
});

$("save-gemini-env-btn").addEventListener("click", () => {
  const payload = {
    GEMINI_API_KEY: $("gemini-api-key").value.trim(),
    GEMINI_DEFAULT_MODEL: $("gemini-model").value.trim()
  };
  fetch("/api/save-env", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
    .then(r => {
      if (r.ok) {
        addLog("Configurazione Gemini salvata nel file .env locale.", "ok");
      } else {
        addLog("Errore durante il salvataggio in .env", "err");
      }
    });
});

// versione (log SemVer) accanto al titolo
fetch("/api/version")
  .then((r) => r.json())
  .then((d) => { if (d.version) $("app-version").textContent = "v" + d.version; })
  .catch(() => {});

// riaggancio a job in corso
fetch("/api/state", { cache: "no-store" })
  .then((r) => r.json())
  .then((state) => {
    if (state.running) {
      addLog("Job in esecuzione trovato, riaggancio in corso...", "dim");
      beginJob();
    } else {
      checkResumeState();
    }
  })
  .catch(() => { checkResumeState(); });

let currentResumeState = null;

function checkResumeState() {
  fetch("/api/resume-state", { cache: "no-store" })
    .then((r) => r.json())
    .then((state) => {
      if (state && state.config) {
        currentResumeState = state;
        const total = state.original_total;
        const remaining = total - (state.completed_files || []).length;
        if (remaining > 0) {
          $("resume-total").textContent = total;
          $("resume-remaining").textContent = remaining;
          $("resume-banner").hidden = false;
        }
      }
    })
    .catch(() => {});
}

$("resume-dismiss-btn").addEventListener("click", () => {
  $("resume-banner").hidden = true;
  currentResumeState = null;
});

$("resume-start-btn").addEventListener("click", () => {
  if (!currentResumeState) return;
  $("resume-banner").hidden = true;
  const payload = currentResumeState.config;
  payload.completed_files = currentResumeState.completed_files;
  // la chiave API non viene mai salvata in resume.json: la reinseriamo dal campo
  if (!payload.api_key) payload.api_key = $("api-key").value.trim();
  submitConvert(payload);
});

// --- Selezione dei file da convertire ---
const fileList = $("file-list");
const fileSummary = $("file-select-summary");
const fileActions = $("file-select-actions");

function selectedFiles() {
  // null = nessuna selezione esplicita → tutti i PDF della cartella
  const boxes = fileList.querySelectorAll('input[type="checkbox"]');
  if (boxes.length === 0) return null;
  return [...boxes].filter((b) => b.checked).map((b) => b.value);
}

function updateFileSummary() {
  const sel = selectedFiles();
  if (sel === null) { fileSummary.textContent = "tutti i PDF della cartella"; return; }
  const total = fileList.querySelectorAll('input[type="checkbox"]').length;
  fileSummary.textContent = `${sel.length} di ${total} file selezionati`;
}

$("list-files-btn").addEventListener("click", async () => {
  if (offlineBlocked()) return;
  const source = $("source-dir").value.trim();
  if (!source) { addLog("Indicare prima la cartella sorgente.", "err"); return; }
  try {
    const r = await fetch("/api/list-pdfs?source_dir=" + encodeURIComponent(source));
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || r.statusText);
    if (!d.files.length) { fileSummary.textContent = "nessun PDF nella cartella"; return; }
    fileList.replaceChildren();
    d.files.forEach((name) => {
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox"; box.value = name; box.checked = true;
      box.addEventListener("change", updateFileSummary);
      const span = document.createElement("span");
      span.className = "file-name"; span.textContent = name;
      label.append(box, span);
      fileList.appendChild(label);
    });
    fileList.hidden = false;
    fileActions.hidden = false;
    updateFileSummary();
  } catch (e) {
    addLog("Elenco file: " + fetchErrorText(e), "err");
  }
});

function setAllFiles(checked) {
  fileList.querySelectorAll('input[type="checkbox"]').forEach((b) => { b.checked = checked; });
  updateFileSummary();
}
$("sel-all").addEventListener("click", () => setAllFiles(true));
$("sel-none").addEventListener("click", () => setAllFiles(false));

// pulsanti "Sfoglia…": aprono il Finder lato server (osascript)
document.querySelectorAll("button.browse").forEach((btn) =>
  btn.addEventListener("click", async () => {
    if (offlineBlocked()) return;
    btn.disabled = true;
    try {
      const r = await fetch(`/api/pick?kind=${btn.dataset.pick}`);
      const d = await r.json();
      if (d.path) $(btn.dataset.target).value = d.path;
      else if (d.error) addLog(d.error, "err");
    } catch (e) {
      addLog(fetchErrorText(e), "err");
    } finally {
      btn.disabled = false;
    }
  })
);

function num(id) {
  const v = $(id).value.trim();
  return v === "" ? null : Number(v);
}

function addLog(text, cls) {
  const line = document.createElement("div");
  line.className = "log-line" + (cls ? " " + cls : "");
  line.textContent = text;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

function describe(e) {
  switch (e.status) {
    case "batch_start": return [`Avvio: ${e.total} file da convertire`, "dim"];
    case "start": return [`[${e.index}/${e.total}] ${e.file} …`, null];
    case "split": return [`  ${e.file} partizionato in ${e.parts} parti`, "dim"];
    case "skip": return [`  — ${e.file}: già nei limiti`, "dim"];
    case "done": return [`  ✔ ${e.file} → ${(e.outputs || []).join(", ")}`, "ok"];
    case "error": return [`  ✘ ${e.file}: ${e.error}`, "err"];
    case "paused": return [`⏸ In pausa dopo ${e.index - 1}/${e.total} file.`, "dim"];
    case "resumed": return [`▶ Ripresa.`, "dim"];
    case "stopped": return [`⏹ Interrotto dopo ${e.index - 1}/${e.total} file.`, "err"];
    case "page_start": return null;  // troppo frequente per il log: vedi banner/ETA
    case "page_done": return null;
    case "page_retry":
      return [`  ⟳ ${e.file} pag.${e.page}: tentativo ${e.attempt} fallito (${e.error}), riprovo…`, "dim"];
    case "page_failed":
      return [`  ✘ ${e.file} pag.${e.page}: non convertita, tentativi esauriti (${e.error})`, "err"];
    case "batch_done": {
      let base = `Completato: ${e.converted} md prodotti, ${e.errors.length} errori`;
      if (e.report) base += `\nReport dell'estrazione: ${e.report}`;
      return [e.stopped ? base + " (interrotto)" : base, e.errors.length ? "err" : "ok"];
    }
    case "split_done": {
      const extra = e.skipped != null ? `\n(${e.skipped} file già nei limiti)` : "";
      const errs = (e.errors || []).length ? `\nErrori: ${e.errors.join("; ")}` : "";
      const dest = e.interi_dir ? ` (originali archiviati in ${e.interi_dir})` : "";
      const head = e.parts.length
        ? `Parti create nella cartella${dest}:\n  ${e.parts.join("\n  ")}`
        : "Nessun file da partizionare.";
      return [`${head}${extra}${errs}`, errs ? "err" : "ok"];
    }
    default: return [JSON.stringify(e), "dim"];
  }
}

function formatEta(seconds) {
  if (seconds < 60) return `~${Math.round(seconds)}s`;
  const m = Math.round(seconds / 60);
  return m < 60 ? `~${m} min` : `~${Math.floor(m / 60)}h ${m % 60}min`;
}

function applyState(state) {
  // il server tiene solo gli ultimi 500 eventi: l'offset riallinea il log
  const events = state.events || [];
  const total = state.events_total != null ? state.events_total : events.length;
  const offset = total - events.length;
  events.slice(Math.max(0, renderedEvents - offset)).forEach((e) => {
    const line = describe(e);
    if (line) addLog(...line);
  });
  renderedEvents = total;

  if (state.kind === "convert" && state.total > 0) {
    const pct = Math.round((state.done / state.total) * 100);
    bannerFill.style.width = pct + "%";
    bannerCount.textContent = `${state.done}/${state.total} · ${pct}%`;
    const page = state.llm_page;
    if (!state.running) {
      bannerLabel.textContent = "Conversione completata";
      $("banner-eta").textContent = "";
    } else if (state.paused) {
      bannerLabel.textContent = "In pausa — file in corso completato";
      $("banner-eta").textContent = "";
    } else if (page && page.total) {
      bannerLabel.textContent = `Conversione: ${page.file} — pagina ${page.page} (${page.index}/${page.total})`;
      const durations = state.page_durations || [];
      if (durations.length) {
        const avg = durations.reduce((a, b) => a + b, 0) / durations.length;
        const remaining = Math.max(page.total - page.index, 0);
        $("banner-eta").textContent = remaining > 0
          ? `${formatEta(avg)}/pagina · ${formatEta(avg * remaining)} rimanenti`
          : "";
      } else {
        $("banner-eta").textContent = "";
      }
    } else {
      bannerLabel.textContent = `Conversione: ${state.current || "…"}`;
      $("banner-eta").textContent = "";
    }
    // controlli pausa/stop solo durante una conversione attiva
    bannerControls.hidden = !state.running;
    pauseBtn.hidden = !!state.paused;
    resumeBtn.hidden = !state.paused;
  } else {
    bannerFill.style.width = state.running ? "35%" : "100%";
    bannerLabel.textContent = state.running ? "Partizionamento…" : "Job completato";
    bannerCount.textContent = "";
    $("banner-eta").textContent = "";
    bannerControls.hidden = true;
  }

  if (!state.running) {
    if (state.error) {
      addLog("ERRORE: " + state.error, "err");
    } else if (renderedEvents > 0) {
      const dest = $("dest-dir").value.trim();
      if (dest) {
        const line = document.createElement("div");
        line.className = "log-line stack";
        const btn = document.createElement("button");
        btn.className = "secondary";
        btn.style.width = "auto";
        btn.style.padding = "0.4rem 0.8rem";
        btn.style.marginTop = "0.5rem";
        btn.textContent = "📂 Apri cartella nel Finder";
        btn.onclick = () => {
          fetch("/api/open-folder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder: dest })
          });
        };
        line.appendChild(btn);
        log.appendChild(line);
        log.scrollTop = log.scrollHeight;
      }
    }
    stopPolling();
  }
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
  [startBtn, splitBtn, analyzeBtn, convertPartsBtn].forEach((b) => { b.disabled = false; });
  bannerControls.hidden = true;
  setTimeout(() => { banner.hidden = true; }, 2500);
}

function sendControl(path) {
  return fetch(path, { method: "POST" }).catch(() => {});
}
pauseBtn.addEventListener("click", () => { sendControl("/api/pause"); pauseBtn.hidden = true; resumeBtn.hidden = false; });
resumeBtn.addEventListener("click", () => { sendControl("/api/resume"); resumeBtn.hidden = true; pauseBtn.hidden = false; });
stopBtn.addEventListener("click", () => {
  if (confirm("Interrompere la conversione dopo il file in corso?")) {
    stopBtn.disabled = true;
    addLog("Interruzione programmata: attesa fine del file in corso...", "dim");
    sendControl("/api/stop");
  }
});

function poll() {
  fetch("/api/state", { cache: "no-store" })
    .then((r) => r.json())
    .then(applyState)
    .catch(() => {});
}

function beginJob() {
  renderedEvents = 0;
  log.replaceChildren();
  banner.hidden = false;
  bannerFill.style.width = "0%";
  [startBtn, splitBtn, analyzeBtn, convertPartsBtn].forEach((b) => { b.disabled = true; });
  stopBtn.disabled = false;
  pollTimer = setInterval(poll, 700);
}

function post(url, payload) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(async (r) => {
    if (!r.ok) throw new Error((await r.json()).error || r.statusText);
  });
}

function buildConvertPayload(sourceDir, onlyFiles = null) {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const provider = document.querySelector('input[name="provider"]:checked').value;
  let margins = null;
  const marginsStr = $("adv-margins").value.trim();
  if (marginsStr) {
    const parts = marginsStr.split(",").map(s => parseFloat(s.trim())).filter(n => !isNaN(n));
    if (parts.length === 1) margins = [parts[0], parts[0], parts[0], parts[0]];
    else if (parts.length === 2) margins = [parts[1], parts[0], parts[1], parts[0]]; // left, top, right, bottom da horiz, vert
    else if (parts.length === 4) margins = [parts[3], parts[0], parts[1], parts[2]]; // css -> rect (left, top, right, bottom)
  }

  return {
    source_dir: sourceDir,
    dest_dir: $("dest-dir").value.trim(),
    only_files: onlyFiles,
    max_files: num("max-files"),
    mode,
    provider,
    api_key: provider === "gemini" ? $("gemini-api-key").value.trim() : $("api-key").value.trim(),
    model: provider === "glmocr" ? $("local-model").value.trim()
      : provider === "gemini" ? $("gemini-model").value.trim()
      : $("model").value.trim(),
    ollama_url: $("ollama-url").value.trim(),
    auto_split: $("auto-split").checked,
    split_pages: num("split-pages"),
    split_mb: num("split-mb"),
    extract_images: $("extract-images").checked,
    rename_by_topic: $("rename-topic").checked,
    llm_topic: $("llm-topic").checked,
    margins,
    table_strategy: $("adv-table-strategy").value,
    use_ocr: $("adv-use-ocr").checked,
    force_ocr: $("adv-force-ocr").checked,
    dpi: num("adv-dpi"),
    ignore_images: $("adv-ignore-images").checked,
    image_size_limit: num("adv-image-size-limit"),
    graphics_limit: num("adv-graphics-limit"),
    brain_optimize: $("brain-optimize").checked,
  };
}

function submitConvert(payload) {
  if (offlineBlocked()) return;
  if (!payload.source_dir || !payload.dest_dir) {
    addLog("Indicare cartella sorgente e destinazione.", "err");
    return;
  }
  if (payload.mode !== "native" && (payload.provider === "openrouter" || payload.provider === "gemini") && !payload.api_key) {
    addLog(`Provider ${payload.provider === "gemini" ? "Gemini" : "OpenRouter"}: serve almeno una chiave API.`, "err");
    return;
  }
  beginJob();
  post("/api/convert", payload).catch((e) => {
    addLog("ERRORE: " + fetchErrorText(e), "err");
    if (e.message && e.message.includes("già in esecuzione")) {
      addLog("Riaggancio al job in corso...", "dim");
      // non chiamiamo stopPolling() così continua ad aggiornarsi
    } else {
      stopPolling();
    }
  });
}

startBtn.addEventListener("click", () => {
  const onlyFiles = selectedFiles();
  if (onlyFiles !== null && onlyFiles.length === 0) {
    addLog("Nessun file selezionato: spunta almeno un PDF o usa 'tutti'.", "err");
    return;
  }
  submitConvert(buildConvertPayload($("source-dir").value.trim(), onlyFiles));
});

// passo 3: converte la cartella elaborata (parti + file già nei limiti) in Markdown
convertPartsBtn.addEventListener("click", () => {
  const folder = $("split-input").value.trim();
  if (!folder) {
    addLog("Indicare la cartella elaborata (campo del passo 1).", "err");
    return;
  }
  submitConvert(buildConvertPayload(folder));
});

if ($("restart-server-btn")) {
  $("restart-server-btn").addEventListener("click", () => {
    if (confirm("Sei sicuro di voler riavviare il server? Ogni operazione in corso verrà abbattuta immediatamente e non potrà essere conclusa (ma l'avanzamento verrà salvato).")) {
      addLog("Riavvio hard del server in corso...", "dim");
      $("restart-server-btn").disabled = true;
      fetch("/api/restart", { method: "POST" })
        .then(() => {
          setTimeout(() => { location.reload(); }, 2500);
        })
        .catch(() => {
          setTimeout(() => { location.reload(); }, 2500);
        });
    }
  });
}

// passo 1 del partizionatore: analisi preliminare, nessuna scrittura
analyzeBtn.addEventListener("click", async () => {
  if (offlineBlocked()) return;
  const payload = {
    source_dir: $("split-input").value.trim(),
    max_pages: num("tool-max-pages"),
    max_mb: num("tool-max-mb"),
  };
  if (!payload.source_dir) {
    addLog("Indicare la cartella da analizzare.", "err");
    return;
  }
  if (payload.max_pages === null && payload.max_mb === null) {
    addLog("Impostare almeno un limite (pagine o MB).", "err");
    return;
  }
  log.replaceChildren();
  analyzeBtn.disabled = true;
  try {
    const r = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || r.statusText);
    let over = 0;
    d.files.forEach((f) => {
      if (f.error) { addLog(`✘ ${f.file}: ${f.error}`, "err"); return; }
      if (f.needs_split) {
        over += 1;
        const reasons = [f.over_pages ? "pagine" : null, f.over_mb ? "MB" : null]
          .filter(Boolean).join(" + ");
        addLog(`⚠ ${f.file}: ${f.pages} pagine, ${f.mb} MB — OLTRE (${reasons})`, "err");
      } else {
        addLog(`— ${f.file}: ${f.pages} pagine, ${f.mb} MB — nei limiti`, "dim");
      }
    });
    addLog(`Analisi completata: ${over} file da partizionare su ${d.files.length}.`, over ? "ok" : "dim");
  } catch (e) {
    addLog("ERRORE analisi: " + fetchErrorText(e), "err");
  } finally {
    analyzeBtn.disabled = false;
  }
});

splitBtn.addEventListener("click", () => {
  if (offlineBlocked()) return;
  const payload = {
    input: $("split-input").value.trim(),
    interi_dir: $("split-interi").value.trim() || null,
    max_pages: num("tool-max-pages"),
    max_mb: num("tool-max-mb"),
  };
  if (!payload.input) {
    addLog("Indicare la cartella (o il PDF) da partizionare.", "err");
    return;
  }
  if (payload.max_pages === null && payload.max_mb === null) {
    addLog("Impostare almeno un limite (pagine o MB).", "err");
    return;
  }
  beginJob();
  post("/api/split", payload).catch((e) => {
    addLog("ERRORE: " + fetchErrorText(e), "err");
    if (e.message && e.message.includes("già in esecuzione")) {
      addLog("Riaggancio al job in corso...", "dim");
      // non chiamiamo stopPolling() così continua ad aggiornarsi
    } else {
      stopPolling();
    }
  });
});

// --- Second Brain: verifica ottimizzazione di un file .md ---
$("brain-check-btn").addEventListener("click", async () => {
  if (offlineBlocked()) return;
  const path = $("brain-file").value.trim();
  const report = $("brain-report");
  if (!path) {
    addLog("Indicare il file .md da verificare.", "err");
    return;
  }
  $("brain-check-btn").disabled = true;
  try {
    const r = await fetch("/api/brain-check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || r.statusText);
    report.replaceChildren();
    const addRow = (text, isErr, bold) => {
      const row = document.createElement("div");
      row.className = "note";
      row.style.cssText = `font-size:0.85em;margin:0.15rem 0;${bold ? "font-weight:700;" : ""}`;
      row.textContent = text;
      if (isErr) row.style.color = "var(--err)";
      report.appendChild(row);
    };
    if (d.files) {
      // report aggregato di cartella (lint cross-file)
      const allOk = d.optimized_count === d.total && d.orphans.length === 0
        && Object.keys(d.duplicate_titles).length === 0;
      const verdict = document.createElement("div");
      verdict.style.cssText = "font-weight:700;margin-bottom:0.5rem;";
      verdict.style.color = allOk ? "var(--ok, #3c9)" : "var(--err)";
      verdict.textContent = allOk
        ? `✅ Cartella in ordine: ${d.optimized_count}/${d.total} fonti ottimizzate, indice completo`
        : `⚠️ Cartella da sistemare: ${d.optimized_count}/${d.total} fonti ottimizzate`;
      report.appendChild(verdict);
      if (!d.has_index) addRow("✘ index.md assente (viene creato dalla prossima conversione batch)", true);
      d.orphans.forEach((f) => addRow(`✘ ${f}: non presente in index.md (orfano)`, true));
      Object.entries(d.duplicate_titles).forEach(([t, names]) =>
        addRow(`✘ Titolo duplicato "${t}": ${names.join(", ")}`, true));
      d.files.forEach((f) => {
        if (f.error) { addRow(`✘ ${f.file}: ${f.error}`, true); return; }
        if (f.optimized) addRow(`✔ ${f.file}`);
        else addRow(`✘ ${f.file}: ${f.issues.join("; ")}`, true);
      });
    } else {
      const verdict = document.createElement("div");
      verdict.style.cssText = "font-weight:700;margin-bottom:0.5rem;";
      verdict.style.color = d.optimized ? "var(--ok, #3c9)" : "var(--err)";
      verdict.textContent = d.optimized
        ? `✅ ${d.file}: già ottimizzato per il second brain`
        : `⚠️ ${d.file}: da ottimizzare (riconvertilo con l'opzione 🧠 attiva)`;
      report.appendChild(verdict);
      d.checks.forEach((c) => {
        addRow(`${c.ok ? "✔" : "✘"} ${c.label}${!c.ok && c.detail ? " — " + c.detail : ""}`, !c.ok);
      });
    }
    report.hidden = false;
  } catch (e) {
    addLog("Verifica second brain: " + fetchErrorText(e), "err");
  } finally {
    $("brain-check-btn").disabled = false;
  }
});
// --- Quality Audit ---
$("audit-start-btn").addEventListener("click", async () => {
  if (offlineBlocked()) return;
  const pdfPath = $("audit-pdf").value.trim();
  const mdPath = $("audit-md").value.trim();
  
  if (!pdfPath || !mdPath) {
    addLog("Indicare sia il PDF originale che il Markdown estratto.", "err");
    return;
  }
  
  $("audit-start-btn").disabled = true;
  $("audit-results").hidden = true;
  
  try {
    const r = await fetch("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pdf_path: pdfPath, md_path: mdPath }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || r.statusText);
    
    $("audit-layout-score").textContent = d.layout_score + "%";
    $("audit-typo-score").textContent = d.typography_score + "%";
    
    const fmt = (stats) => `
      <li>Caratteri: ${stats.characters}</li>
      <li>Titoli H1/H2/H3: ${stats.h1} / ${stats.h2} / ${stats.h3}</li>
      <li>Grassetti/Corsivi: ${stats.bold} / ${stats.italic}</li>
      <li>Immagini: ${stats.images}</li>
      <li>Tabelle (stimate): ${stats.tables}</li>
    `;
    
    $("audit-pdf-stats").innerHTML = fmt(d.pdf_stats);
    $("audit-md-stats").innerHTML = fmt(d.md_stats);
    
    $("audit-results").hidden = false;
  } catch (e) {
    addLog("Errore Quality Audit: " + fetchErrorText(e), "err");
  } finally {
    $("audit-start-btn").disabled = false;
  }
});

// Avviso immediato se la pagina è stata aperta come file locale.
if (OFFLINE) addLog(OFFLINE_MSG, "err");
