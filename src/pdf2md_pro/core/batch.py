"""Conversione batch: cartella sorgente → cartella destinazione.

Per ogni PDF: eventuale auto-partizionamento oltre i limiti, conversione,
rinomina per argomento (max 10 caratteri), spostamento di md + sidecar +
immagini nella destinazione. Un file rotto non ferma il lotto.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pdf2md_pro.core.naming import derive_topic, unique_path
from pdf2md_pro.core.pipeline import ConversionError, convert
from pdf2md_pro.core.splitter import needs_split, split_pdf
from pdf2md_pro.engines.openrouter import (
    DEFAULT_OLLAMA_URL,
    OpenRouterEngine,
    ensure_ollama,
    make_llm_engine,
)

ProgressFn = Callable[[dict], None]


@dataclass
class BatchConfig:
    source_dir: Path
    dest_dir: Path
    max_files: int | None = None
    mode: str = "native"  # native | hybrid | llm
    provider: str = "glmocr"  # glmocr (locale via Ollama) | openrouter
    api_key: str | None = None
    model: str | None = None  # None → default del provider
    ollama_url: str = DEFAULT_OLLAMA_URL
    auto_split: bool = False
    split_pages: int | None = 100
    split_mb: float | None = 10.0
    extract_images: bool = True
    llm_topic: bool = True  # con LLM attivo, argomento suggerito dal modello


@dataclass
class _Job:
    config: BatchConfig
    progress: ProgressFn
    llm_engine: OpenRouterEngine | None
    outputs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _emit(job: _Job, **event) -> None:
    job.progress(event)


def _topic_for(job: _Job, markdown: str) -> str:
    if job.llm_engine is not None and job.config.llm_topic:
        topic = job.llm_engine.suggest_topic(markdown)
        if topic:
            return topic
    return derive_topic(markdown)


def _deliver(job: _Job, tmp_out: Path, source_stem: str) -> str:
    """Sposta md/sidecar/assets dalla cartella temporanea alla destinazione,
    rinominando per argomento. Ritorna il nome del md finale."""
    dest = job.config.dest_dir
    dest.mkdir(parents=True, exist_ok=True)
    md_src = tmp_out / f"{source_stem}.md"
    markdown = md_src.read_text(encoding="utf-8")

    topic = _topic_for(job, markdown)
    md_dest = unique_path(dest, topic, ".md")
    final_stem = md_dest.stem
    shutil.move(md_src, md_dest)
    sidecar = tmp_out / f"{source_stem}.provenance.json"
    if sidecar.exists():
        shutil.move(sidecar, dest / f"{final_stem}.provenance.json")

    assets_src = tmp_out / "assets"
    if assets_src.is_dir():
        assets_dest = dest / "assets"
        assets_dest.mkdir(exist_ok=True)
        for asset in assets_src.iterdir():
            shutil.move(asset, unique_path(assets_dest, asset.stem, asset.suffix))
    return md_dest.name


def _convert_one(job: _Job, pdf: Path) -> list[str]:
    """Converte un PDF (eventualmente partizionato). Ritorna i md prodotti."""
    config = job.config
    produced = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        work_pdfs = [pdf]
        if config.auto_split and needs_split(pdf, config.split_pages, config.split_mb):
            work_pdfs = split_pdf(
                pdf, tmp_dir / "parti", config.split_pages, config.split_mb
            )
            _emit(job, status="split", file=pdf.name, parts=len(work_pdfs))

        for work_pdf in work_pdfs:
            tmp_out = tmp_dir / f"out_{work_pdf.stem}"
            convert(
                work_pdf,
                tmp_out,
                extract_images=config.extract_images,
                llm_engine=job.llm_engine,
                mode=config.mode,
            )
            produced.append(_deliver(job, tmp_out, work_pdf.stem))
    return produced


def run_batch(config: BatchConfig, progress: ProgressFn = lambda e: None) -> dict:
    source = Path(config.source_dir)
    if not source.is_dir():
        raise ConversionError(f"cartella sorgente non trovata: {source}")

    llm_engine = None
    if config.mode in ("hybrid", "llm"):
        try:
            if config.provider == "glmocr":
                ensure_ollama(config.ollama_url)
            llm_engine = make_llm_engine(
                config.provider, config.api_key, config.model, config.ollama_url
            )
        except (ValueError, RuntimeError) as exc:
            raise ConversionError(str(exc)) from exc

    pdfs = sorted(source.glob("*.pdf"))[: config.max_files]
    job = _Job(config=config, progress=progress, llm_engine=llm_engine)
    _emit(job, status="batch_start", total=len(pdfs))

    for index, pdf in enumerate(pdfs, start=1):
        _emit(job, status="start", file=pdf.name, index=index, total=len(pdfs))
        try:
            produced = _convert_one(job, pdf)
            job.outputs.extend(produced)
            _emit(
                job,
                status="done",
                file=pdf.name,
                index=index,
                total=len(pdfs),
                outputs=produced,
            )
        except Exception as exc:
            job.errors.append(f"{pdf.name}: {exc}")
            _emit(job, status="error", file=pdf.name, index=index, error=str(exc))

    summary = {
        "converted": len(job.outputs),
        "outputs": job.outputs,
        "errors": job.errors,
        "total_files": len(pdfs),
    }
    _emit(job, status="batch_done", **summary)
    return summary
