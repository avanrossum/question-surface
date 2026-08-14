"""Local HTTP server for one questionnaire.

Deliberately minimal and stdlib-only: this binds to loopback, serves exactly one
questionnaire, and exits when the answers are in. It is a local capture surface,
not a web application — there is no auth, no session, and no multi-tenant path,
because it must never be exposed beyond 127.0.0.1.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import render, store

MAX_BODY = 4 * 1024 * 1024


def serve(
    spec: dict,
    responses_root: Path,
    port: int = 8777,
    open_browser: bool = True,
    stay_open: bool = False,
) -> dict | None:
    """Serve the questionnaire until it is submitted. Returns the written paths."""
    outcome: dict = {}
    done = threading.Event()
    respondent = store.detect_respondent()

    class Handler(BaseHTTPRequestHandler):
        # Quiet by default — the CLI prints what matters.
        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            if self.path.split("?")[0] not in ("/", "/index.html"):
                self._send(404, "text/plain", b"not found")
                return
            draft = store.load_draft(responses_root, spec["id"])
            body = render.render(
                spec, draft=draft, respondent=respondent
            ).encode("utf-8")
            self._send(200, "text/html; charset=utf-8", body)

        def do_POST(self):
            route = self.path.split("?")[0]
            if route not in ("/submit", "/draft"):
                self._send(404, "application/json", b'{"ok":false}')
                return

            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_BODY:
                self._json(400, {"ok": False, "error": "bad content length"})
                return

            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                self._json(400, {"ok": False, "error": f"bad JSON: {exc}"})
                return

            payload = data.get("payload") or {}

            if route == "/draft":
                store.save_draft(responses_root, spec["id"], payload)
                self._json(200, {"ok": True})
                return

            try:
                response = store.build_response(spec, payload)
                paths = store.write(responses_root, spec, response)
            except OSError as exc:
                self._json(500, {"ok": False, "error": str(exc)})
                return

            outcome.update(
                {
                    "json": str(paths["json"]),
                    "markdown": str(paths["markdown"]),
                    "response": response,
                }
            )
            self._json(
                200,
                {"ok": True, "json": str(paths["json"]), "markdown": str(paths["markdown"])},
            )
            if not stay_open:
                done.set()

        def _json(self, code: int, obj: dict):
            self._send(code, "application/json", json.dumps(obj).encode("utf-8"))

        def _send(self, code: int, ctype: str, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_port}/"

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    print(f"  Question Surface → {url}")
    print(f"  {spec['title']}")
    print("  Waiting for submission… (Ctrl-C to stop)\n")

    if open_browser:
        webbrowser.open(url)

    try:
        done.wait()
    except KeyboardInterrupt:
        print("\n  Stopped. Draft (if any) is saved.")
        return None
    finally:
        # shutdown() stops the accept loop; server_close() releases the socket.
        # Without the second call the port stays bound for the life of the
        # process, which matters when serve() is driven in-process rather than
        # from the CLI.
        httpd.shutdown()
        httpd.server_close()

    return outcome or None
