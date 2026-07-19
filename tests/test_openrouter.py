import json

import pymupdf
import pytest

from pdf2md_pro.core.pipeline import convert
from pdf2md_pro.engines.openrouter import (
    GEMINI_API_URL,
    OpenRouterEngine,
    check_ollama_health,
    make_llm_engine,
    parse_api_keys,
)


@pytest.fixture
def mixed_pdf(tmp_path):
    """Pagina 1 con testo, pagina 2 solo immagine (finta scansione)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(
        pymupdf.Rect(50, 50, 550, 200),
        "Capitolo primo con testo nativo estraibile dalla pagina.",
        fontsize=12,
        fontname="helv",
    )
    scan = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200))
    pix.clear_with(120)
    scan.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pix)
    path = tmp_path / "misto.pdf"
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def engine(monkeypatch):
    eng = OpenRouterEngine(api_key="sk-test", model="z-ai/glm-4.5v")
    monkeypatch.setattr(
        eng, "_chat", lambda content, max_tokens=4096, timeout=None: "# Pagina trascritta dal VLM"
    )
    return eng


def test_engine_convert_renders_pages(engine, mixed_pdf):
    results = engine.convert(mixed_pdf, pages=[2])

    assert len(results) == 1
    assert results[0].page_number == 2
    assert results[0].engine == "openrouter:z-ai/glm-4.5v"
    assert "trascritta dal VLM" in results[0].markdown
    assert 0 < results[0].confidence < 1


def test_engine_chat_failure_gives_placeholder(mixed_pdf, monkeypatch):
    import pdf2md_pro.engines.openrouter as openrouter_module

    monkeypatch.setattr(openrouter_module, "RETRY_BACKOFF", 0.0)  # niente attesa reale nei retry
    eng = OpenRouterEngine(api_key="sk-test")

    def boom(content, max_tokens=4096, timeout=None):
        raise RuntimeError("rete giù")

    monkeypatch.setattr(eng, "_chat", boom)
    results = eng.convert(mixed_pdf, pages=[1])
    assert results[0].confidence == 0.0
    assert "non convertita" in results[0].markdown


def test_suggest_topic_sanitized(engine, monkeypatch):
    monkeypatch.setattr(
        engine, "_chat", lambda content, max_tokens=4096: "  Fisica Nucleare!  "
    )
    topic = engine.suggest_topic("testo di fisica")
    assert topic == "fisicanucl"
    assert len(topic) <= 10


def test_hybrid_pipeline_routes_scan_pages(engine, mixed_pdf, tmp_path):
    result = convert(
        mixed_pdf, tmp_path / "out", llm_engine=engine, mode="hybrid",
        extract_images=False,
    )

    prov = json.loads(result.provenance_path.read_text(encoding="utf-8"))
    by_page = {b["page"]: b["engine"] for b in prov["blocks"]}
    assert by_page[1] == "native"
    assert by_page[2] == "openrouter:z-ai/glm-4.5v"

    md = result.markdown_path.read_text(encoding="utf-8")
    assert "Capitolo primo" in md
    assert "trascritta dal VLM" in md


def test_llm_mode_uses_llm_for_all_pages(engine, mixed_pdf, tmp_path):
    result = convert(
        mixed_pdf, tmp_path / "out2", llm_engine=engine, mode="llm",
        extract_images=False,
    )
    prov = json.loads(result.provenance_path.read_text(encoding="utf-8"))
    assert all(b["engine"].startswith("openrouter:") for b in prov["blocks"])


def test_factory_glmocr_local_default():
    from pdf2md_pro.engines.openrouter import make_llm_engine

    eng = make_llm_engine("glmocr")
    assert eng.name == "ollama:glm-ocr:latest"
    assert eng.api_url == "http://127.0.0.1:11434/v1/chat/completions"


def test_factory_openrouter_requires_key():
    from pdf2md_pro.engines.openrouter import make_llm_engine

    with pytest.raises(ValueError):
        make_llm_engine("openrouter", api_key=None)
    eng = make_llm_engine("openrouter", api_key="sk-x", model="nvidia/nemotron-3-ultra-550b-a55b:free")
    assert eng.name == "openrouter:nvidia/nemotron-3-ultra-550b-a55b:free"


def test_factory_unknown_provider():
    from pdf2md_pro.engines.openrouter import make_llm_engine

    with pytest.raises(ValueError):
        make_llm_engine("boh")


def test_convert_emette_eventi_di_progresso_per_pagina(engine, mixed_pdf):
    events = []
    engine.convert(mixed_pdf, pages=[1, 2], progress=events.append)

    statuses = [e["status"] for e in events]
    assert statuses == ["page_start", "page_done", "page_start", "page_done"]
    assert events[1]["page"] == 1 and events[1]["index"] == 1 and events[1]["total"] == 2
    assert "elapsed" in events[1]


def test_pagina_fallita_riprova_poi_segnaposto(mixed_pdf, monkeypatch):
    import pdf2md_pro.engines.openrouter as openrouter_module

    monkeypatch.setattr(openrouter_module, "RETRY_BACKOFF", 0.0)
    eng = OpenRouterEngine(api_key="sk-test")
    calls = {"n": 0}

    def boom(content, max_tokens=4096, timeout=None):
        calls["n"] += 1
        raise RuntimeError("crash runner")

    monkeypatch.setattr(eng, "_chat", boom)
    events = []
    results = eng.convert(mixed_pdf, pages=[1], progress=events.append)

    assert calls["n"] == openrouter_module.PAGE_RETRIES + 1  # 1 tentativo + N retry
    assert results[0].confidence == 0.0
    statuses = [e["status"] for e in events]
    assert statuses == ["page_start", "page_retry", "page_retry", "page_failed"]


def test_pagina_recupera_dopo_un_fallimento(mixed_pdf, monkeypatch):
    import pdf2md_pro.engines.openrouter as openrouter_module

    monkeypatch.setattr(openrouter_module, "RETRY_BACKOFF", 0.0)
    eng = OpenRouterEngine(api_key="sk-test")
    calls = {"n": 0}

    def flaky(content, max_tokens=4096, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("crash runner")
        return "# ripreso dopo il retry"

    monkeypatch.setattr(eng, "_chat", flaky)
    events = []
    results = eng.convert(mixed_pdf, pages=[1], progress=events.append)

    assert results[0].confidence > 0
    assert "ripreso dopo il retry" in results[0].markdown
    statuses = [e["status"] for e in events]
    assert statuses == ["page_start", "page_retry", "page_done"]


def test_check_ollama_health_irraggiungibile():
    report = check_ollama_health(url="http://127.0.0.1:1", timeout=0.5)
    assert report["reachable"] is False
    assert "error" in report


def test_check_ollama_health_raggiungibile(monkeypatch):
    import json as json_module
    import urllib.request
    from io import BytesIO

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json_module.dumps({"models": [{"name": "glm-ocr:latest"}]}).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
    report = check_ollama_health(model="glm-ocr:latest")

    assert report["reachable"] is True
    assert report["model_loaded"] is True
    assert "glm-ocr:latest" in report["models"]


def test_parse_api_keys_multilinea_e_virgola():
    assert parse_api_keys("key1\nkey2\n\nkey3") == ["key1", "key2", "key3"]
    assert parse_api_keys("key1, key2 ,key3") == ["key1", "key2", "key3"]
    assert parse_api_keys("") == []
    assert parse_api_keys(None) == []
    assert parse_api_keys(["a", "", " b "]) == ["a", "b"]


def test_gemini_factory_usa_endpoint_e_modello_corretti():
    eng = make_llm_engine("gemini", api_key="k1\nk2", model=None)
    assert eng.api_url == GEMINI_API_URL
    assert eng.model == "gemini-2.5-flash"
    assert eng.name == "gemini:gemini-2.5-flash"


def test_gemini_richiede_almeno_una_chiave():
    with pytest.raises(ValueError):
        make_llm_engine("gemini", api_key=None)


def test_chat_ruota_chiave_su_quota_esaurita(monkeypatch):
    import urllib.error
    import urllib.request

    eng = OpenRouterEngine(api_key="key-scaduta\nkey-buona", model="gemini-2.5-flash",
                            api_url=GEMINI_API_URL, provider="gemini")
    seen_keys = []

    class FakeQuotaError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(GEMINI_API_URL, 429, "Too Many Requests", {}, None)
        def read(self):
            return b'{"error": {"message": "Quota exceeded for this API key"}}'

    class FakeOkResponse:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return b'{"choices": [{"message": {"content": "# ok"}}]}'

    def fake_urlopen(request, timeout=None):
        key = request.headers.get("Authorization", "").removeprefix("Bearer ")
        seen_keys.append(key)
        if key == "key-scaduta":
            raise FakeQuotaError()
        return FakeOkResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = eng._chat([{"type": "text", "text": "ciao"}])

    assert result == "# ok"
    assert seen_keys == ["key-scaduta", "key-buona"]


def test_chat_non_ruota_su_errore_non_di_quota(monkeypatch):
    import urllib.error
    import urllib.request

    eng = OpenRouterEngine(api_key="key1\nkey2", model="gemini-2.5-flash",
                            api_url=GEMINI_API_URL, provider="gemini")
    seen_keys = []

    class FakeAuthError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(GEMINI_API_URL, 401, "Unauthorized", {}, None)
        def read(self):
            return b'{"error": {"message": "Invalid API key"}}'

    def fake_urlopen(request, timeout=None):
        seen_keys.append(request.headers.get("Authorization"))
        raise FakeAuthError()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="401"):
        eng._chat([{"type": "text", "text": "ciao"}])

    assert len(seen_keys) == 1  # nessuna rotazione: errore di credenziali, non di quota
