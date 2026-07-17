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
import urllib.request
from pathlib import Path

import pymupdf

from pdf2md_pro.core.naming import slugify_topic
from pdf2md_pro.engines.base import PageResult

DEFAULT_MODEL = "z-ai/glm-4.5v"
API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_DEFAULT_MODEL = "glm-ocr:latest"
RENDER_DPI = 150
LLM_CONFIDENCE = 0.8  # trascrizione generativa: mai confidence piena

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
    ) -> list[PageResult]:
        results = []
        with pymupdf.open(pdf_path) as doc:
            numbers = pages or list(range(1, doc.page_count + 1))
            for number in numbers:
                pix = doc[number - 1].get_pixmap(dpi=RENDER_DPI)
                png_b64 = base64.b64encode(pix.tobytes("png")).decode()
                content = [
                    {"type": "text", "text": PAGE_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{png_b64}"},
                    },
                ]
                try:
                    markdown = self._chat(content)
                    results.append(
                        PageResult(
                            page_number=number,
                            markdown=markdown,
                            confidence=LLM_CONFIDENCE,
                            engine=self.name,
                        )
                    )
                except Exception as exc:
                    results.append(
                        PageResult(
                            page_number=number,
                            markdown=FAILED_PAGE_TEMPLATE.format(page=number, error=exc),
                            confidence=0.0,
                            engine=self.name,
                        )
                    )
        return results

    def suggest_topic(self, text: str) -> str:
        content = [{"type": "text", "text": TOPIC_PROMPT + text[:2000]}]
        try:
            raw = self._chat(content, max_tokens=20)
        except Exception:
            return ""
        return slugify_topic(raw)

    def _chat(self, content: list[dict], max_tokens: int = 4096) -> str:
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
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode())
        return data["choices"][0]["message"]["content"]


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
