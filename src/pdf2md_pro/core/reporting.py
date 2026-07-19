"""Sintesi leggibili: footer di attribuzione dentro ogni file, report unico
aggregato di un'intera procedura di estrazione batch."""

from __future__ import annotations

from datetime import datetime

from pdf2md_pro import __version__

REPO_URL = "https://github.com/ConsulenzaContributi/pdf2md-pro"


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
        "| File sorgente | Output | Pagine | Motore | Tempo | Esito |",
        "|---|---|---|---|---|---|",
    ]
    for e in entries:
        esito = "✔" if not e.get("error") else "✘"
        lines.append(
            f"| {e['source']} | {e.get('output', '—')} | {e.get('pages', '—')} "
            f"| {e.get('engine', '—')} | {format_duration(e.get('duration_s', 0))} | {esito} |"
        )

    if failed:
        lines += ["", "## Errori", ""]
        for e in failed:
            lines.append(f"- **{e['source']}**: {e['error']}")

    return "\n".join(lines) + "\n"
