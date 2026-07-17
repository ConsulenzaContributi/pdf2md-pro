"use strict";

const $ = (id) => document.getElementById(id);
const banner = $("banner");
const bannerFill = $("banner-fill");
const bannerLabel = $("banner-label");
const bannerCount = $("banner-count");
const log = $("log");
const startBtn = $("start");
const splitBtn = $("split-start");

let pollTimer = null;
let renderedEvents = 0;

document.querySelectorAll('input[name="mode"]').forEach((radio) =>
  radio.addEventListener("change", () => {
    const mode = document.querySelector('input[name="mode"]:checked').value;
    $("llm-fields").hidden = mode === "native";
  })
);

document.querySelectorAll('input[name="provider"]').forEach((radio) =>
  radio.addEventListener("change", () => {
    const provider = document.querySelector('input[name="provider"]:checked').value;
    $("glmocr-fields").hidden = provider !== "glmocr";
    $("openrouter-fields").hidden = provider !== "openrouter";
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
    case "batch_done":
      return [`Completato: ${e.converted} md prodotti, ${e.errors.length} errori`, e.errors.length ? "err" : "ok"];
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
    bannerLabel.textContent = state.running
      ? `Conversione: ${state.current || "…"}`
      : "Conversione completata";
  } else {
    bannerFill.style.width = state.running ? "35%" : "100%";
    bannerLabel.textContent = state.running ? "Partizionamento…" : "Job completato";
    bannerCount.textContent = "";
  }

  if (!state.running) {
    if (state.error) addLog("ERRORE: " + state.error, "err");
    stopPolling();
  }
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
  startBtn.disabled = false;
  splitBtn.disabled = false;
  setTimeout(() => { banner.hidden = true; }, 2500);
}

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
  startBtn.disabled = true;
  splitBtn.disabled = true;
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

startBtn.addEventListener("click", () => {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const provider = document.querySelector('input[name="provider"]:checked').value;
  const payload = {
    source_dir: $("source-dir").value.trim(),
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
  };
  if (!payload.source_dir || !payload.dest_dir) {
    addLog("Indicare cartella sorgente e destinazione.", "err");
    return;
  }
  if (mode !== "native" && provider === "openrouter" && !payload.api_key) {
    addLog("Provider OpenRouter: serve la chiave API.", "err");
    return;
  }
  beginJob();
  post("/api/convert", payload).catch((e) => { addLog("ERRORE: " + e.message, "err"); stopPolling(); });
});

splitBtn.addEventListener("click", () => {
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
  post("/api/split", payload).catch((e) => { addLog("ERRORE: " + e.message, "err"); stopPolling(); });
});
