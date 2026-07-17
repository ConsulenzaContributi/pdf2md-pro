"""Server locale della GUI: stdlib http.server, solo 127.0.0.1.

Un job alla volta (conversione batch o partizionamento), eseguito in un
thread; la pagina interroga /api/state. La chiave API OpenRouter arriva dal
form, vive solo in memoria e non viene mai scritta su disco né loggata.
"""

from __future__ import annotations

import json
import subprocess
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pdf2md_pro.core.batch import BatchConfig, run_batch
from pdf2md_pro.core.splitter import analyze_folder, split_folder, split_pdf

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


def _clean_path(raw: str) -> Path:
    """Normalizza percorsi incollati: rimuove apici e backslash di escape
    shell (`Crucial\\ X9` → `Crucial X9`), che altrimenti non esistono su disco."""
    text = (raw or "").strip().strip("'\"")
    text = text.replace("\\ ", " ")  # spazi shell-escaped incollati a mano
    return Path(text)


def _run_convert(payload: dict) -> None:
    try:
        config = BatchConfig(
            source_dir=_clean_path(payload["source_dir"]),
            dest_dir=_clean_path(payload["dest_dir"]),
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
        target = _clean_path(payload["input"])
        out_dir = _clean_path(payload["out_dir"])
        max_pages = payload.get("max_pages") or None
        max_mb = payload.get("max_mb") or None
        if target.is_dir():
            summary = split_folder(
                target, out_dir, max_pages, max_mb, progress=_progress
            )
            names = [p for parts in summary["split"].values() for p in parts]
            done = {"status": "split_done", "parts": names,
                    "skipped": len(summary["skipped"]), "errors": summary["errors"]}
        else:
            parts = split_pdf(target, out_dir, max_pages, max_mb)
            names = [str(p) for p in parts]
            summary = {"parts": names}
            done = {"status": "split_done", "parts": names}
        with _LOCK:
            _JOB["summary"] = summary
            _JOB["events"].append(done)
    except Exception as exc:
        with _LOCK:
            _JOB["error"] = str(exc)
    finally:
        with _LOCK:
            _JOB["running"] = False


def _pick_path(kind: str) -> dict:
    """Apre il Finder (macOS) per scegliere cartella o PDF. ponytail: solo
    macOS via osascript; su altri OS restare sull'inserimento manuale."""
    if kind == "file":
        script = 'POSIX path of (choose file of type {"com.adobe.pdf"} with prompt "Seleziona un PDF")'
    else:
        script = 'POSIX path of (choose folder with prompt "Seleziona una cartella")'
    try:
        out = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=300,
        )
    except FileNotFoundError:
        return {"error": "selettore disponibile solo su macOS"}
    except subprocess.TimeoutExpired:
        return {"cancelled": True}
    if out.returncode != 0:  # utente ha annullato
        return {"cancelled": True}
    return {"path": out.stdout.strip().rstrip("/")}


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
        parsed = urllib.parse.urlparse(self.path)
        routes = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/style.css": ("style.css", "text/css"),
            "/app.js": ("app.js", "application/javascript"),
        }
        if parsed.path in routes:
            filename, content_type = routes[parsed.path]
            self._send(200, (STATIC_DIR / filename).read_bytes(), content_type)
        elif parsed.path == "/api/state":
            with _LOCK:
                self._send_json(200, dict(_JOB))
        elif parsed.path == "/api/pick":
            kind = urllib.parse.parse_qs(parsed.query).get("kind", ["folder"])[0]
            self._send_json(200, _pick_path(kind))
        else:
            self._send_json(404, {"error": "non trovato"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "JSON non valido"})
            return

        if self.path == "/api/analyze":  # sincrono: sola lettura, veloce
            try:
                report = analyze_folder(
                    _clean_path(payload["source_dir"]),
                    payload.get("max_pages") or None,
                    payload.get("max_mb") or None,
                )
                self._send_json(200, {"files": report})
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
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
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        print(
            f"Impossibile avviare sulla porta {port} ({exc}).\n"
            f"Forse un server è già attivo: apri http://127.0.0.1:{port}/ "
            f"nel browser, oppure riprova con un'altra porta: pdf2md gui --port 8348",
            flush=True,
        )
        return
    url = f"http://127.0.0.1:{port}/"
    print(f"pdf2md-pro GUI attiva su {url}", flush=True)
    print("Lascia aperta questa finestra mentre lavori. Ctrl+C per fermare.", flush=True)
    threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer fermato.", flush=True)
        server.shutdown()
