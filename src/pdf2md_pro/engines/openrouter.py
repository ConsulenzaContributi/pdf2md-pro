"""Motore LLM su API chat OpenAI-compatibili: pagina come immagine → Markdown.

Due provider:
- ``glmocr``: GLM-OCR locale servito da Ollama (default, gratuito, offline)
- ``openrouter``: modelli cloud via chiave API OpenRouter

Pensato per contenuti tecnico-accademici: tabelle GFM, formule LaTeX,
descrizioni delle figure. La chiave API resta in memoria, mai su disco.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import pymupdf

from pdf2md_pro.core.naming import slugify_topic
from pdf2md_pro.engines.base import PageResult

DEFAULT_MODEL = "z-ai/glm-4.5v"
API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_DEFAULT_MODEL = "glm-ocr:latest"
RENDER_DPI = 150
LLM_CONFIDENCE = 0.8  # trascrizione generativa: mai confidence piena
PAGE_TIMEOUT = 60.0  # timeout per singola pagina: un runner incastrato non deve
                      # bloccare il file per l'intero self.timeout (300s di default)
PAGE_RETRIES = 2
RETRY_BACKOFF = 3.0  # secondi, moltiplicato per il numero del tentativo

ProgressFn = Callable[[dict], None]

PAGE_PROMPT = """Transcribe this document page into GitHub-flavored Markdown.
Rules:
- Preserve the heading hierarchy (#, ##, ...).
- Tables: GFM pipe tables, keep every cell value exactly.
- Math: LaTeX, inline $...$ or display $$...$$.
- Figures, charts, diagrams: insert an italic line *Figura: <detailed description>*.
- Code: fenced blocks with language.
- Academic/technical accuracy over fluency. Do not invent content.
- Output Markdown only, no commentary."""

TOPIC_PROMPT = """Return ONE lowercase topic word (max 10 characters, letters and
digits only) that best describes this document. Output only the word.

Document excerpt:
"""

FAILED_PAGE_TEMPLATE = "> ⚠️ Pagina {page} non convertita (LLM): {error}\n"


class OpenRouterEngine:
    """Client chat-vision OpenAI-compatibile (OpenRouter, Ollama, ...)."""

    def __init__(
        self,
        api_key: str | None,
        model: str = DEFAULT_MODEL,
        timeout: float = 300.0,
        api_url: str = API_URL,
        provider: str = "openrouter",
    ) -> None:
        if provider == "openrouter" and not api_key:
            raise ValueError("chiave API OpenRouter mancante")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.api_url = api_url
        self.provider = provider

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}"

    @property
    def version(self) -> str:
        return self.model

    def convert(
        self,
        pdf_path: Path,
        image_dir: Path | None = None,  # firma comune; il VLM descrive le figure nel testo
        pages: list[int] | None = None,
        progress: ProgressFn | None = None,
    ) -> list[PageResult]:
        """Converte pagina per pagina. Ogni pagina ha un timeout proprio
        (`PAGE_TIMEOUT`, non l'intero `self.timeout`) e `PAGE_RETRIES` tentativi
        con backoff: un runner incastrato o in crash-loop non blocca il file
        per minuti in silenzio, e chi chiama vede l'avanzamento reale via
        `progress` (page_start/page_retry/page_done/page_failed)."""
        results = []
        with pymupdf.open(pdf_path) as doc:
            numbers = pages or list(range(1, doc.page_count + 1))
            total = len(numbers)
            for index, number in enumerate(numbers, start=1):
                pix = doc[number - 1].get_pixmap(dpi=RENDER_DPI)
                png_b64 = base64.b64encode(pix.tobytes("png")).decode()
                content = [
                    {"type": "text", "text": PAGE_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{png_b64}"},
                    },
                ]
                results.append(
                    self._convert_page(number, index, total, content, progress)
                )
        return results

    def _convert_page(
        self, number: int, index: int, total: int, content: list[dict], progress: ProgressFn | None,
    ) -> PageResult:
        if progress:
            progress({"status": "page_start", "page": number, "index": index, "total": total})
        start = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(1, PAGE_RETRIES + 2):  # 1 tentativo + PAGE_RETRIES
            try:
                markdown = self._chat(content, timeout=PAGE_TIMEOUT)
                elapsed = time.monotonic() - start
                if progress:
                    progress({"status": "page_done", "page": number, "index": index,
                               "total": total, "elapsed": round(elapsed, 1)})
                return PageResult(
                    page_number=number, markdown=markdown,
                    confidence=LLM_CONFIDENCE, engine=self.name,
                )
            except Exception as exc:
                last_error = exc
                if attempt <= PAGE_RETRIES:
                    if progress:
                        progress({"status": "page_retry", "page": number, "index": index,
                                   "total": total, "attempt": attempt, "error": str(exc)})
                    time.sleep(RETRY_BACKOFF * attempt)
        elapsed = time.monotonic() - start
        if progress:
            progress({"status": "page_failed", "page": number, "index": index,
                       "total": total, "elapsed": round(elapsed, 1), "error": str(last_error)})
        return PageResult(
            page_number=number,
            markdown=FAILED_PAGE_TEMPLATE.format(page=number, error=last_error),
            confidence=0.0, engine=self.name,
        )

    def suggest_topic(self, text: str) -> str:
        content = [{"type": "text", "text": TOPIC_PROMPT + text[:2000]}]
        try:
            raw = self._chat(content, max_tokens=20)
        except Exception:
            return ""
        return slugify_topic(raw)

    def _chat(self, content: list[dict], max_tokens: int = 4096, timeout: float | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                data = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"API {exc.code}: {_error_detail(exc)}") from exc
        if "choices" not in data:
            raise RuntimeError(f"risposta API senza contenuto: {_api_message(data)}")
        return data["choices"][0]["message"]["content"]


def _api_message(data: dict) -> str:
    """Estrae il messaggio d'errore da una risposta API OpenAI-compatibile."""
    error = data.get("error")
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return str(error or data)[:200]


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        return _api_message(json.loads(exc.read().decode()))
    except Exception:
        return str(exc.reason)


def check_ollama_health(url: str = DEFAULT_OLLAMA_URL, model: str | None = None, timeout: float = 3.0) -> dict:
    """Stato live di Ollama per il badge GUI: raggiungibile, latenza, modello
    caricato. Non solleva mai: l'esito è nel dizionario, sempre."""
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        latency_ms = round((time.monotonic() - start) * 1000)
        models = [m.get("name") for m in data.get("models", [])]
        return {
            "reachable": True,
            "latency_ms": latency_ms,
            "models": models,
            "model_loaded": model in models if model else None,
        }
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def ensure_ollama(url: str = DEFAULT_OLLAMA_URL, timeout: float = 3.0) -> None:
    """Verifica che il server Ollama risponda; errore chiaro se spento."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=timeout):
            pass
    except Exception as exc:
        raise RuntimeError(
            f"Ollama non raggiungibile su {url}: avviare l'app Ollama "
            f"o 'ollama serve' ({exc})"
        ) from exc


def make_llm_engine(
    provider: str,
    api_key: str | None = None,
    model: str | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> OpenRouterEngine:
    """`glmocr` → GLM-OCR locale via Ollama; `openrouter` → cloud con chiave."""
    if provider == "glmocr":
        return OpenRouterEngine(
            api_key=None,
            model=model or OLLAMA_DEFAULT_MODEL,
            api_url=ollama_url.rstrip("/") + "/v1/chat/completions",
            provider="ollama",
        )
    if provider == "openrouter":
        return OpenRouterEngine(api_key=api_key, model=model or DEFAULT_MODEL)
    raise ValueError(f"provider LLM sconosciuto: {provider}")
