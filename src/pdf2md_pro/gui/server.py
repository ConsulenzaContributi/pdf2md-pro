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

import multiprocessing
import queue

from pdf2md_pro.core.batch import BatchConfig, JobControl, run_batch
from pdf2md_pro.core.splitter import (
    analyze_folder,
    list_pdfs,
    needs_split,
    partition_in_place,
    split_folder,
)

STATIC_DIR = Path(__file__).parent / "static"
MAX_EVENTS = 500

_LOCK = threading.Lock()
_JOB: dict = {"running": False, "kind": None, "events": [], "summary": None, "error": None}
_CONTROL_RUNNING: multiprocessing.Event | None = None
_CONTROL_STOP: multiprocessing.Event | None = None
_Q: multiprocessing.Queue | None = None
_PROCESS: multiprocessing.Process | None = None

def _queue_listener() -> None:
    while True:
        if _Q is None:
            import time
            time.sleep(0.5)
            continue
        try:
            msg = _Q.get(timeout=0.5)
            if msg is None:
                continue
            if msg["type"] == "event":
                _progress(msg["data"])  # prende _LOCK internamente: niente nesting (deadlock)
            else:
                with _LOCK:
                    if msg["type"] == "summary":
                        _JOB["summary"] = msg["data"]
                    elif msg["type"] == "error":
                        _JOB["error"] = msg["data"]
                    elif msg["type"] == "done":
                        _JOB["running"] = False
        except queue.Empty:
            continue
        except Exception:
            pass

threading.Thread(target=_queue_listener, daemon=True).start()


def _reset_job(kind: str) -> None:
    _JOB.update(
        running=True, kind=kind, events=[], events_total=0, summary=None,
        error=None, done=0, total=0, current="", paused=False,
    )


def _progress(event: dict) -> None:
    with _LOCK:
        _JOB["events"] = (_JOB["events"] + [event])[-MAX_EVENTS:]
        _JOB["events_total"] = _JOB.get("events_total", 0) + 1
        status = event.get("status")
        if status == "batch_start":
            _JOB["total"] = event.get("total", 0)
        elif status == "start":
            _JOB["current"] = event.get("file", "")
        elif status in ("done", "error"):
            _JOB["done"] = event.get("index", _JOB["done"])
        elif status == "paused":
            _JOB["paused"] = True
        elif status == "resumed":
            _JOB["paused"] = False


def _clean_path(raw: str) -> Path:
    """Normalizza percorsi incollati: rimuove apici e backslash di escape
    shell (`Crucial\\ X9` → `Crucial X9`), che altrimenti non esistono su disco."""
    text = (raw or "").strip().strip("'\"")
    text = text.replace("\\ ", " ")  # spazi shell-escaped incollati a mano
    return Path(text)


def _child_convert(payload: dict, q: multiprocessing.Queue, r_evt: multiprocessing.Event, s_evt: multiprocessing.Event) -> None:
    def child_progress(event):
        q.put({"type": "event", "data": event})
    try:
        config = BatchConfig(
            source_dir=_clean_path(payload["source_dir"]),
            dest_dir=_clean_path(payload["dest_dir"]),
            only_files=payload.get("only_files") or None,
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
            rename_by_topic=bool(payload.get("rename_by_topic")),
            llm_topic=bool(payload.get("llm_topic", True)),
            margins=tuple(payload.get("margins")) if payload.get("margins") else None,
            table_strategy=payload.get("table_strategy", "lines_strict"),
            use_ocr=bool(payload.get("use_ocr")),
            force_ocr=bool(payload.get("force_ocr")),
            dpi=payload.get("dpi"),
            ignore_images=bool(payload.get("ignore_images")),
            image_size_limit=payload.get("image_size_limit"),
            graphics_limit=payload.get("graphics_limit"),
            brain_optimize=bool(payload.get("brain_optimize")),
        )
        control = JobControl()
        control._running = r_evt
        control._stop = s_evt
        completed = set(payload.get("completed_files", []))
        summary = run_batch(config, progress=child_progress, control=control, completed_files=completed)
        q.put({"type": "summary", "data": summary})
    except Exception as exc:
        q.put({"type": "error", "data": str(exc)})
    finally:
        q.put({"type": "done"})


def _child_split(payload: dict, q: multiprocessing.Queue) -> None:
    def child_progress(event):
        q.put({"type": "event", "data": event})
    try:
        target = _clean_path(payload["input"])
        max_pages = payload.get("max_pages") or None
        max_mb = payload.get("max_mb") or None
        interi = _clean_path(payload["interi_dir"]) if payload.get("interi_dir") else None
        if target.is_dir():
            summary = split_folder(
                target, max_pages, max_mb, progress=child_progress, interi_dir=interi
            )
            names = [p for parts in summary["split"].values() for p in parts]
            done = {"status": "split_done", "parts": names, "interi_dir": summary["interi_dir"],
                    "skipped": len(summary["skipped"]), "errors": summary["errors"]}
        elif not needs_split(target, max_pages, max_mb):
            summary = {"parts": [], "interi_dir": None}
            done = {"status": "split_done", "parts": [], "skipped": 1, "errors": []}
        else:
            names = partition_in_place(target, max_pages, max_mb, interi)
            interi_used = str(interi) if interi else str(target.parent / "interi")
            summary = {"parts": names, "interi_dir": interi_used}
            done = {"status": "split_done", "parts": names, "interi_dir": interi_used,
                    "skipped": 0, "errors": []}
        q.put({"type": "summary", "data": summary})
        q.put({"type": "event", "data": done})
    except Exception as exc:
        q.put({"type": "error", "data": str(exc)})
    finally:
        q.put({"type": "done"})


def _pick_path(kind: str) -> dict:
    """Apre il Finder (macOS) per scegliere cartella o PDF. ponytail: solo
    macOS via osascript; su altri OS restare sull'inserimento manuale."""
    if kind == "file":
        script = 'POSIX path of (choose file of type {"com.adobe.pdf"} with prompt "Seleziona un PDF")'
    elif kind == "md":
        script = 'POSIX path of (choose file with prompt "Seleziona un file Markdown (.md)")'
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
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
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
                snapshot = dict(_JOB)
                snapshot["events"] = list(_JOB["events"])  # no riferimento condiviso
            self._send_json(200, snapshot)
        elif parsed.path == "/api/resume-state":
            resume_file = Path.home() / ".pdf2md" / "resume.json"
            if resume_file.exists():
                try:
                    state_data = json.loads(resume_file.read_text(encoding="utf-8"))
                    self._send_json(200, state_data)
                except Exception:
                    self._send_json(200, {})
            else:
                self._send_json(200, {})
        elif parsed.path == "/api/pick":
            kind = urllib.parse.parse_qs(parsed.query).get("kind", ["folder"])[0]
            self._send_json(200, _pick_path(kind))
        elif parsed.path == "/api/version":
            from pdf2md_pro import __version__
            self._send_json(200, {"version": __version__})
        elif parsed.path == "/api/list-pdfs":
            raw = urllib.parse.parse_qs(parsed.query).get("source_dir", [""])[0]
            folder = _clean_path(raw)
            if not folder.is_dir():
                self._send_json(400, {"error": f"cartella non trovata: {folder}"})
            else:
                self._send_json(200, {"files": [p.name for p in list_pdfs(folder)]})
        else:
            self._send_json(404, {"error": "non trovato"})

    def do_POST(self) -> None:  # noqa: N802
        global _Q, _PROCESS, _CONTROL_RUNNING, _CONTROL_STOP
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

        if self.path == "/api/brain-check":  # sincrono: sola lettura del file
            from pdf2md_pro.core.brain import check_markdown
            target = _clean_path(payload.get("path", ""))
            if target.suffix.lower() != ".md":
                self._send_json(400, {"error": "serve un file .md"})
                return
            if not target.is_file():
                self._send_json(400, {"error": f"file non trovato: {target}"})
                return
            try:
                report = check_markdown(target.read_text(encoding="utf-8"))
                report["file"] = target.name
                self._send_json(200, report)
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
            return

        if self.path in ("/api/pause", "/api/resume", "/api/stop", "/api/restart"):
            if self.path == "/api/restart":
                if _PROCESS is not None and _PROCESS.is_alive():
                    _PROCESS.terminate()
                with _LOCK:
                    _JOB["running"] = False
                    _JOB["events"].append({"status": "stopped", "index": _JOB.get("done", 0)})
                    _JOB["events_total"] = _JOB.get("events_total", 0) + 1
                self._send_json(200, {"ok": True})
                import os
                import sys
                import time
                def _do_restart():
                    time.sleep(0.5)
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                threading.Thread(target=_do_restart, daemon=False).start()
                return

            if _PROCESS is None or not _JOB["running"]:
                self._send_json(409, {"error": "nessuna conversione in corso"})
                return
            if self.path == "/api/pause":
                if _CONTROL_RUNNING:
                    _CONTROL_RUNNING.clear()
            elif self.path == "/api/resume":
                if _CONTROL_RUNNING:
                    _CONTROL_RUNNING.set()
            else:
                # stop graceful: il file in corso viene completato, poi run_batch
                # esce ed emette "stopped"/"done" via coda (il terminate hard
                # resta solo in /api/restart)
                if _CONTROL_STOP:
                    _CONTROL_STOP.set()
                if _CONTROL_RUNNING:
                    _CONTROL_RUNNING.set()  # sblocca l'eventuale pausa
            self._send_json(200, {"ok": True})
            return

        targets = {"/api/convert": ("convert", _child_convert), "/api/split": ("split", _child_split)}
        if self.path not in targets:
            self._send_json(404, {"error": "non trovato"})
            return
        kind, runner = targets[self.path]
        with _LOCK:
            if _JOB["running"]:
                self._send_json(409, {"error": "un job è già in esecuzione"})
                return
            _reset_job(kind)
            if _Q is None:
                _Q = multiprocessing.Queue()
            _CONTROL_RUNNING = multiprocessing.Event()
            _CONTROL_RUNNING.set()
            _CONTROL_STOP = multiprocessing.Event()
        
        args = (payload, _Q, _CONTROL_RUNNING, _CONTROL_STOP) if kind == "convert" else (payload, _Q)
        _PROCESS = multiprocessing.Process(target=runner, args=args, daemon=True)
        _PROCESS.start()
        self._send_json(202, {"ok": True})


def serve(port: int = 8347, open_browser: bool = True) -> None:
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
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer fermato.", flush=True)
        server.shutdown()
