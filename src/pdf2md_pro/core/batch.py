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


import multiprocessing

class JobControl:
    """Controllo pausa/ripresa/stop di una conversione batch.

    La pausa agisce tra un file e il successivo (il file in corso viene
    completato); lo stop interrompe il lotto dopo il file corrente."""

    def __init__(self) -> None:
        self._running = multiprocessing.Event()
        self._running.set()  # set = in esecuzione, clear = in pausa
        self._stop = multiprocessing.Event()

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        self._running.set()

    def stop(self) -> None:
        self._stop.set()
        self._running.set()  # sblocca l'eventuale attesa in pausa

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def wait_if_paused(self) -> None:
        """Blocca finché in pausa; ritorna subito se in esecuzione o fermato."""
        self._running.wait()

from pdf2md_pro.core.naming import derive_topic, unique_path
from pdf2md_pro.core.pipeline import ConversionError, convert
from pdf2md_pro.core.splitter import list_pdfs, needs_split, split_pdf
from pdf2md_pro.engines.openrouter import (
    DEFAULT_OLLAMA_URL,
    OpenRouterEngine,
    ensure_ollama,
    make_llm_engine,
)
import json
import dataclasses

ProgressFn = Callable[[dict], None]


@dataclass
class BatchConfig:
    source_dir: Path
    dest_dir: Path
    only_files: list[str] | None = None  # None = tutti; altrimenti solo questi nomi
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
    rename_by_topic: bool = False  # default: il md tiene il nome del PDF originale
    llm_topic: bool = True  # con LLM attivo e rinomina per argomento, argomento dal modello
    
    # Opzioni avanzate pymupdf4llm / cropbox
    margins: tuple[float, float, float, float] | None = None  # (left, top, right, bottom)
    table_strategy: str = "lines_strict"  # lines_strict, lines, none
    use_ocr: bool = False
    force_ocr: bool = False
    dpi: int | None = None
    ignore_images: bool = False
    image_size_limit: float | None = None
    graphics_limit: int | None = None


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
    """Sposta md/sidecar/assets dalla cartella temporanea alla destinazione.
    Il md tiene il nome del PDF originale, salvo rinomina per argomento
    esplicita. Ritorna il nome del md finale."""
    dest = job.config.dest_dir
    dest.mkdir(parents=True, exist_ok=True)
    md_src = tmp_out / f"{source_stem}.md"
    markdown = md_src.read_text(encoding="utf-8")

    stem = _topic_for(job, markdown) if job.config.rename_by_topic else source_stem
    md_dest = unique_path(dest, stem, ".md")
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
                margins=config.margins,
                table_strategy=config.table_strategy,
                use_ocr=config.use_ocr,
                force_ocr=config.force_ocr,
                dpi=config.dpi,
                ignore_images=config.ignore_images,
                image_size_limit=config.image_size_limit,
                graphics_limit=config.graphics_limit,
            )
            produced.append(_deliver(job, tmp_out, work_pdf.stem))
    return produced


def run_batch(
    config: BatchConfig,
    progress: ProgressFn = lambda e: None,
    control: JobControl | None = None,
    completed_files: set[str] | None = None,
) -> dict:
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

    pdfs = list_pdfs(source)
    if config.only_files is not None:
        wanted = set(config.only_files)
        pdfs = [p for p in pdfs if p.name in wanted]

    original_total = len(pdfs)
    completed_names = set(completed_files) if completed_files else set()
    if completed_names:
        pdfs = [p for p in pdfs if p.name not in completed_names]

    pdfs = pdfs[: config.max_files]
    job = _Job(config=config, progress=progress, llm_engine=llm_engine)
    _emit(job, status="batch_start", total=len(pdfs))
    
    resume_file = Path.home() / ".pdf2md" / "resume.json"
    
    def save_resume():
        try:
            resume_data = {
                "config": dataclasses.asdict(config),
                "original_total": original_total,
                "completed_files": list(completed_names)
            }
            # Convert Path objects to strings for JSON serialization
            resume_data["config"]["source_dir"] = str(resume_data["config"]["source_dir"])
            resume_data["config"]["dest_dir"] = str(resume_data["config"]["dest_dir"])
            # la chiave API non tocca mai il disco: alla ripresa la GUI la reinserisce
            resume_data["config"]["api_key"] = None
            resume_file.parent.mkdir(parents=True, exist_ok=True)
            resume_file.write_text(json.dumps(resume_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    stopped = False
    for index, pdf in enumerate(pdfs, start=1):
        if control is not None:
            if control.paused:
                _emit(job, status="paused", index=index, total=len(pdfs))
                control.wait_if_paused()
                if not control.stopped:
                    _emit(job, status="resumed", index=index, total=len(pdfs))
            if control.stopped:
                stopped = True
                _emit(job, status="stopped", index=index, total=len(pdfs))
                break
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
        else:
            completed_names.add(pdf.name)
            save_resume()

    summary = {
        "converted": len(job.outputs),
        "outputs": job.outputs,
        "errors": job.errors,
        "total_files": len(pdfs),
        "stopped": stopped,
    }
    
    if not stopped:
        try:
            if resume_file.exists():
                resume_file.unlink()
        except Exception:
            pass

    _emit(job, status="batch_done", **summary)
    return summary
