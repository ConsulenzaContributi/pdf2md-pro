"""Sintesi leggibili: footer di attribuzione dentro ogni file, report unico
di batch, catalogo `index.md` e registro cumulativo `log.md` della cartella
di destinazione (pattern LLM Wiki: le fonti si catalogano da sole)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from pdf2md_pro import __version__

REPO_URL = "https://github.com/ConsulenzaContributi/pdf2md-pro"
INDEX_NAME = "index.md"
LOG_NAME = "log.md"
SUMMARY_MAX_CHARS = 120

_INDEX_ENTRY = re.compile(r"^- \[(.+?)\]\((.+?)\) — (.*)$")
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)

MODEL_COSTS = {
    # Cost per 1M tokens (input, output) in USD
    "qwen/qwen2.5-vl-72b-instruct": (0.40, 0.40),
    "qwen/qwen3-vl-32b-instruct": (0.15, 0.15),
    "z-ai/glm-4.5v": (0.0, 0.0), # Assuming free or adjust if known
    "google/gemini-2.5-flash": (0.075, 0.30),
    "anthropic/claude-sonnet-4.5": (3.0, 15.0),
    "google/gemini-3.1-flash-lite": (0.075, 0.30),
    "z-ai/glm-5.2": (0.0, 0.0),
    "minimax/minimax-m3": (0.0, 0.0),
    "google/gemini-3.1-pro-preview": (1.25, 5.0),
    "gemini-3.5-flash": (0.075, 0.30),
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-2.5-pro": (1.25, 5.0),
    "gemini-2.0-flash": (0.10, 0.40),
}

def estimate_cost(engine_str: str, tokens_in: int, tokens_out: int) -> float:
    # engine_str is usually "provider:model", e.g., "openrouter:qwen/qwen2.5-vl-72b-instruct"
    model_name = engine_str.split(":", 1)[-1] if ":" in engine_str else engine_str
    if model_name in MODEL_COSTS:
        cost_in, cost_out = MODEL_COSTS[model_name]
        return (tokens_in / 1_000_000 * cost_in) + (tokens_out / 1_000_000 * cost_out)
    return 0.0


def format_duration(seconds: float) -> str:
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}min"


def build_config_summary(
    mode: str,
    margins: tuple | None = None,
    table_strategy: str = "lines_strict",
    use_ocr: bool = False,
    force_ocr: bool = False,
    dpi: int | None = None,
    ignore_images: bool = False,
    image_size_limit: float | None = None,
    graphics_limit: int | None = None,
) -> str:
    """Sintesi leggibile delle opzioni avanzate realmente attive: solo quelle
    diverse dal default, per non generare rumore su una conversione standard."""
    parts = [f"motore={mode}"]
    if margins:
        parts.append("margini=personalizzati")
    if table_strategy != "lines_strict":
        parts.append(f"tabelle={table_strategy or 'disattivate'}")
    if force_ocr:
        parts.append("ocr=forzato")
    elif use_ocr:
        parts.append("ocr=automatico")
    if dpi:
        parts.append(f"dpi={dpi}")
    if ignore_images:
        parts.append("immagini=ignorate")
    elif image_size_limit is not None:
        parts.append(f"soglia-immagini={image_size_limit}")
    if graphics_limit is not None:
        parts.append(f"limite-vettoriali={graphics_limit}")
    return ", ".join(parts)


def build_footer(engine_label: str, duration_s: float, config_summary: str, second_brain: bool) -> str:
    brain_note = " e ottimizzato per second brain" if second_brain else ""
    return (
        f"\n---\n*Estratto con [pdf2md-pro]({REPO_URL}) v{__version__}{brain_note}.*\n"
        f"*Motore: {engine_label} · Tempo di elaborazione: {format_duration(duration_s)} "
        f"· Configurazione: {config_summary}*\n"
    )


def extract_summary(markdown: str) -> str:
    """Prima riga di contenuto vero del md: niente frontmatter, heading,
    separatori o righe di attribution. Per il catalogo index.md."""
    body = _FRONTMATTER_RE.sub("", markdown)
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "---", "*Estratto con", "|", "!")):
            continue
        return stripped[:SUMMARY_MAX_CHARS] + ("…" if len(stripped) > SUMMARY_MAX_CHARS else "")
    return ""


def update_index(dest_dir: Path, entries: list[dict]) -> None:
    """Crea/aggiorna `index.md`: una riga per fonte convertita, con link e
    sommario. Le voci esistenti di altri file restano; quelle riconvertite
    vengono sovrascritte. Ordine alfabetico, grep-friendly."""
    index_path = Path(dest_dir) / INDEX_NAME
    existing: dict[str, str] = {}
    if index_path.exists():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            m = _INDEX_ENTRY.match(line)
            if m:
                existing[m.group(2)] = line
    for e in entries:
        title = e["output"].removesuffix(".md")
        summary = e.get("summary") or ""
        existing[e["output"]] = f"- [{title}]({e['output']}) — {summary}"
    lines = [
        "# Indice delle fonti",
        "",
        f"Catalogo generato da pdf2md-pro v{__version__}: una riga per documento",
        "convertito, pronto a fare da fonte per un second brain / LLM wiki.",
        "",
        *sorted(existing.values(), key=str.lower),
        "",
    ]
    index_path.write_text("\n".join(lines), encoding="utf-8")


def append_log(dest_dir: Path, entries: list[dict]) -> None:
    """Registro cumulativo `log.md`, append-only: una riga per estrazione con
    timestamp, motore, pagine, tempo ed esito. Parsabile con grep."""
    log_path = Path(dest_dir) / LOG_NAME
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    if not log_path.exists():
        lines += ["# Log delle estrazioni", "",
                  "Registro append-only di ogni conversione (pdf2md-pro).", ""]
    for e in entries:
        if e.get("error"):
            lines.append(f"- {now} · {e['source']} · ✘ errore: {e['error']}")
        else:
            lines.append(
                f"- {now} · {e['source']} → {e.get('output')} · {e.get('engine')} "
                f"· {e.get('pages')} pag · {format_duration(e.get('duration_s', 0))} · ✔"
            )
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def build_batch_report(
    source_dir: str,
    dest_dir: str,
    config_summary: str,
    entries: list[dict],
    total_duration: float,
) -> str:
    """Report unico dell'intera procedura di estrazione batch: un file per
    cartella di destinazione elaborata, non uno per PDF."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ok = [e for e in entries if not e.get("error")]
    failed = [e for e in entries if e.get("error")]

    lines = [
        f"# Report di estrazione — pdf2md-pro v{__version__}",
        "",
        f"- Generato: {now}",
        f"- Cartella sorgente: `{source_dir}`",
        f"- Cartella destinazione: `{dest_dir}`",
        f"- Configurazione: {config_summary}",
        f"- Tempo totale: {format_duration(total_duration)}",
        "",
        "## Riepilogo",
        "",
        f"- File processati: {len(entries)}",
        f"- Convertiti con successo: {len(ok)}",
        f"- Errori: {len(failed)}",
        "",
        "## File estratti",
        "",
        "| File sorgente | Output | Pagine | Motore | Tempo | Token (In/Out) | Costo Stimato | Esito |",
        "|---|---|---|---|---|---|---|---|",
    ]
    
    total_cost = 0.0
    total_tokens_in = 0
    total_tokens_out = 0
    
    for e in entries:
        esito = "✔" if not e.get("error") else "✘"
        t_in = e.get("tokens_in", 0)
        t_out = e.get("tokens_out", 0)
        cost = estimate_cost(e.get("engine", ""), t_in, t_out)
        
        total_tokens_in += t_in
        total_tokens_out += t_out
        total_cost += cost
        
        tokens_str = f"{t_in}/{t_out}" if (t_in > 0 or t_out > 0) else "—"
        cost_str = f"${cost:.4f}" if cost > 0 else "—"
        
        lines.append(
            f"| {e['source']} | {e.get('output', '—')} | {e.get('pages', '—')} "
            f"| {e.get('engine', '—')} | {format_duration(e.get('duration_s', 0))} "
            f"| {tokens_str} | {cost_str} | {esito} |"
        )

    if total_tokens_in > 0 or total_tokens_out > 0:
        lines += [
            "",
            "## Consumi LLM",
            "",
            f"- **Token Input Totali:** {total_tokens_in:,}",
            f"- **Token Output Totali:** {total_tokens_out:,}",
            f"- **Costo Totale Stimato:** ${total_cost:.4f}",
        ]

    if failed:
        lines += ["", "## Errori", ""]
        for e in failed:
            lines.append(f"- **{e['source']}**: {e['error']}")

    return "\n".join(lines) + "\n"
