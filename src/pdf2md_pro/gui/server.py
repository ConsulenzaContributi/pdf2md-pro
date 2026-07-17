"""Server locale della GUI: stdlib http.server, solo 127.0.0.1.

Un job alla volta (conversione batch o partizionamento), eseguito in un
thread; la pagina interroga /api/state. La chiave API OpenRouter arriva dal
form, vive solo in memoria e non viene mai scritta su disco né loggata.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pdf2md_pro.core.batch import BatchConfig, run_batch
from pdf2md_pro.core.splitter import split_pdf

STATIC_DIR = Path(__file__).parent / "static"
MAX_EVENTS = 500

_LOCK = threading.Lock()
_JOB: dict = {"running": False, "kind": None, "events": [], "summary": None, "error": None}


def _reset_job(kind: str) -> None:
    _JOB.update(
        running=True, kind=kind, events=[], summary=None, error=None,
        done=0, total=0, current="",
    )


def _progress(event: dict) -> None:
    with _LOCK:
        _JOB["events"] = (_JOB["events"] + [event])[-MAX_EVENTS:]
        status = event.get("status")
        if status == "batch_start":
            _JOB["total"] = event.get("total", 0)
        elif status == "start":
            _JOB["current"] = event.get("file", "")
        elif status in ("done", "error"):
            _JOB["done"] = event.get("index", _JOB["done"])


def _run_convert(payload: dict) -> None:
    try:
        config = BatchConfig(
            source_dir=Path(payload["source_dir"]),
            dest_dir=Path(payload["dest_dir"]),
            max_files=payload.get("max_files") or None,
            mode=payload.get("mode", "native"),
            provider=payload.get("provider", "glmocr"),
            api_key=payload.get("api_key") or None,
            model=payload.get("model") or None,
            ollama_url=payload.get("ollama_url") or "http://127.0.0.1:11434",
            auto_split=bool(payload.get("auto_split")),
            split_pages=payload.get("split_pages") or None,
            split_mb=payload.get("split_mb") or None,
            extract_images=bool(payload.get("extract_images", True)),
        )
        summary = run_batch(config, progress=_progress)
        with _LOCK:
            _JOB["summary"] = summary
    except Exception as exc:
        with _LOCK:
            _JOB["error"] = str(exc)
    finally:
        with _LOCK:
            _JOB["running"] = False


def _run_split(payload: dict) -> None:
    try:
        parts = split_pdf(
            Path(payload["input"]),
            Path(payload["out_dir"]),
            payload.get("max_pages") or None,
            payload.get("max_mb") or None,
        )
        names = [str(p) for p in parts]
        with _LOCK:
            _JOB["summary"] = {"parts": names}
            _JOB["events"].append({"status": "split_done", "parts": names})
    except Exception as exc:
        with _LOCK:
            _JOB["error"] = str(exc)
    finally:
        with _LOCK:
            _JOB["running"] = False


class Handler(BaseHTTPRequestHandler):
    server_version = "pdf2md-pro"

    def log_message(self, *args) -> None:  # niente log delle richieste (chiave API)
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, data: dict) -> None:
        self._send(code, json.dumps(data).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802 (API BaseHTTPRequestHandler)
        routes = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/style.css": ("style.css", "text/css"),
            "/app.js": ("app.js", "application/javascript"),
        }
        if self.path in routes:
            filename, content_type = routes[self.path]
            self._send(200, (STATIC_DIR / filename).read_bytes(), content_type)
        elif self.path == "/api/state":
            with _LOCK:
                self._send_json(200, dict(_JOB))
        else:
            self._send_json(404, {"error": "non trovato"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "JSON non valido"})
            return

        targets = {"/api/convert": ("convert", _run_convert), "/api/split": ("split", _run_split)}
        if self.path not in targets:
            self._send_json(404, {"error": "non trovato"})
            return
        kind, runner = targets[self.path]
        with _LOCK:
            if _JOB["running"]:
                self._send_json(409, {"error": "un job è già in esecuzione"})
                return
            _reset_job(kind)
        threading.Thread(target=runner, args=(payload,), daemon=True).start()
        self._send_json(202, {"ok": True})


def serve(port: int = 8347) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"pdf2md-pro GUI su {url} (Ctrl+C per uscire)")
    threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
