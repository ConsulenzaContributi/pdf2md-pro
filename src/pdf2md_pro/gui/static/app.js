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
}

document
  .querySelectorAll('input[name="mode"], input[name="provider"]')
  .forEach((radio) => radio.addEventListener("change", syncConditionalFields));

// --- Persistenza impostazioni (localStorage, per questo browser locale) ---
const CONFIG_KEY = "pdf2md-pro:config:v1";
const TEXT_IDS = [
  "local-model", "ollama-url", "model", "source-dir", "dest-dir", "max-files",
  "split-pages", "split-mb", "split-input", "split-out",
  "tool-max-pages", "tool-max-mb",
];
const CHECK_IDS = ["extract-images", "auto-split", "remember-key", "rename-topic"];
const RADIO_NAMES = ["mode", "provider"];

function saveConfig() {
  const cfg = { text: {}, check: {}, radio: {} };
  TEXT_IDS.forEach((id) => { cfg.text[id] = $(id).value; });
  CHECK_IDS.forEach((id) => { cfg.check[id] = $(id).checked; });
  RADIO_NAMES.forEach((name) => { cfg.radio[name] = checkedValue(name); });
  // la chiave API è un segreto: salvata solo con consenso esplicito
  cfg.text["api-key"] = $("remember-key").checked ? $("api-key").value : "";
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
  if (!$("remember-key").checked) $("api-key").value = "";
  syncConditionalFields();
}

restoreConfig();
// salva a ogni modifica di qualunque campo del form
document.querySelectorAll("input, select").forEach((el) => {
  el.addEventListener("change", saveConfig);
  el.addEventListener("input", saveConfig);
});

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
    case "batch_done": {
      const base = `Completato: ${e.converted} md prodotti, ${e.errors.length} errori`;
      return [e.stopped ? base + " (interrotto)" : base, e.errors.length ? "err" : "ok"];
    }
    case "split_done": {
      const extra = e.skipped != null ? `\n(${e.skipped} file già nei limiti)` : "";
      const errs = (e.errors || []).length ? `\nErrori: ${e.errors.join("; ")}` : "";
      return [`Parti scritte:\n  ${e.parts.join("\n  ")}${extra}${errs}`, errs ? "err" : "ok"];
    }
    default: return [JSON.stringify(e), "dim"];
  }
}

function applyState(state) {
  (state.events || []).slice(renderedEvents).forEach((e) => addLog(...describe(e)));
  renderedEvents = (state.events || []).length;

  if (state.kind === "convert" && state.total > 0) {
    const pct = Math.round((state.done / state.total) * 100);
    bannerFill.style.width = pct + "%";
    bannerCount.textContent = `${state.done}/${state.total} · ${pct}%`;
    if (!state.running) bannerLabel.textContent = "Conversione completata";
    else if (state.paused) bannerLabel.textContent = "In pausa — file in corso completato";
    else bannerLabel.textContent = `Conversione: ${state.current || "…"}`;
    // controlli pausa/stop solo durante una conversione attiva
    bannerControls.hidden = !state.running;
    pauseBtn.hidden = !!state.paused;
    resumeBtn.hidden = !state.paused;
  } else {
    bannerFill.style.width = state.running ? "35%" : "100%";
    bannerLabel.textContent = state.running ? "Partizionamento…" : "Job completato";
    bannerCount.textContent = "";
    bannerControls.hidden = true;
  }

  if (!state.running) {
    if (state.error) addLog("ERRORE: " + state.error, "err");
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
  fetch(path, { method: "POST" }).catch(() => {});
}
pauseBtn.addEventListener("click", () => { sendControl("/api/pause"); pauseBtn.hidden = true; resumeBtn.hidden = false; });
resumeBtn.addEventListener("click", () => { sendControl("/api/resume"); resumeBtn.hidden = true; pauseBtn.hidden = false; });
stopBtn.addEventListener("click", () => {
  if (confirm("Interrompere la conversione dopo il file in corso?")) sendControl("/api/stop");
});

function poll() {
  fetch("/api/state")
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

function buildConvertPayload(sourceDir) {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const provider = document.querySelector('input[name="provider"]:checked').value;
  return {
    source_dir: sourceDir,
    dest_dir: $("dest-dir").value.trim(),
    max_files: num("max-files"),
    mode,
    provider,
    api_key: $("api-key").value.trim(),
    model: provider === "glmocr" ? $("local-model").value.trim() : $("model").value.trim(),
    ollama_url: $("ollama-url").value.trim(),
    auto_split: $("auto-split").checked,
    split_pages: num("split-pages"),
    split_mb: num("split-mb"),
    extract_images: $("extract-images").checked,
    rename_by_topic: $("rename-topic").checked,
  };
}

function submitConvert(payload) {
  if (offlineBlocked()) return;
  if (!payload.source_dir || !payload.dest_dir) {
    addLog("Indicare cartella sorgente e destinazione.", "err");
    return;
  }
  if (payload.mode !== "native" && payload.provider === "openrouter" && !payload.api_key) {
    addLog("Provider OpenRouter: serve la chiave API.", "err");
    return;
  }
  beginJob();
  post("/api/convert", payload).catch((e) => { addLog("ERRORE: " + fetchErrorText(e), "err"); stopPolling(); });
}

startBtn.addEventListener("click", () =>
  submitConvert(buildConvertPayload($("source-dir").value.trim()))
);

// passo 3 del partizionatore: converte la cartella delle parti in Markdown
convertPartsBtn.addEventListener("click", () => {
  const partsDir = $("split-out").value.trim();
  if (!partsDir) {
    addLog("Indicare la cartella di uscita delle parti (passo 2).", "err");
    return;
  }
  submitConvert(buildConvertPayload(partsDir));
});

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
    out_dir: $("split-out").value.trim(),
    max_pages: num("tool-max-pages"),
    max_mb: num("tool-max-mb"),
  };
  if (!payload.input || !payload.out_dir) {
    addLog("Indicare file PDF e cartella di uscita.", "err");
    return;
  }
  if (payload.max_pages === null && payload.max_mb === null) {
    addLog("Impostare almeno un limite (pagine o MB).", "err");
    return;
  }
  beginJob();
  post("/api/split", payload).catch((e) => { addLog("ERRORE: " + fetchErrorText(e), "err"); stopPolling(); });
});

// Avviso immediato se la pagina è stata aperta come file locale.
if (OFFLINE) addLog(OFFLINE_MSG, "err");
