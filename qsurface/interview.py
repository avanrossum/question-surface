"""Interview mode — one question at a time, with the agent in the loop.

The batch form is right when the agent already knows every question. An
interview is for when each answer determines the next one: the agent asks,
reads what came back, and decides what to ask next. That needs the server alive
across many turns rather than blocking once and exiting, which is why this is a
separate module and a separate lifecycle.

    qsurface interview open <id> --title "..."   starts a detached server
    qsurface interview ask <id> --prompt "..."   pushes one question, waits, prints the answer
    qsurface interview close <id>                writes the transcript and shuts down

The server process is detached so `open` can return and let the agent keep
working. It holds the session in memory and writes the transcript to disk after
every answer, so a crash costs at most the question in flight.

Three things the page must never do: animate forever when the agent has died,
lose an answer someone typed, or leave the respondent unsure whether it is their
turn. Every state below exists to satisfy one of those.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import paths, store

# How long a browser long-poll hangs before returning empty and being retried.
# Short enough that a dead server is noticed, long enough not to spin.
POLL_SECONDS = 20

# The detached server gives up if nothing happens for this long, so an agent
# that dies mid-interview cannot leave a process and a port held forever.
IDLE_SHUTDOWN_SECONDS = 4 * 60 * 60


def sessions_dir() -> Path:
    return paths.state_dir() / "interviews"


def session_file(interview_id: str) -> Path:
    return sessions_dir() / f"{interview_id}.json"


def read_session(interview_id: str) -> dict:
    path = session_file(interview_id)
    if not path.exists():
        raise FileNotFoundError(
            f"no interview {interview_id!r} is open — start one with "
            f"`qsurface interview open {interview_id}`"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def write_session(session: dict) -> Path:
    directory = sessions_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = session_file(session["id"])
    path.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return path


def list_sessions() -> list[dict]:
    directory = sessions_dir()
    if not directory.exists():
        return []
    out = []
    for path in sorted(directory.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --------------------------------------------------------------- transcript --


def transcript_markdown(session: dict) -> str:
    lines = [
        f"# {session['title']} — interview transcript",
        "",
        f"Interview: `{session['id']}`  ",
        f"Started: {session['started_at']}  ",
    ]
    if session.get("ended_at"):
        lines.append(f"Ended: {session['ended_at']}  ")
    lines.append(f"Respondent: {session.get('respondent') or '(unstated)'}  ")
    if session.get("domain"):
        lines.append(f"Conducted as: {session['domain']}  ")
    answered = sum(1 for e in session["exchanges"] if not e.get("skipped"))
    lines += [f"{answered} of {len(session['exchanges'])} questions answered", ""]

    for exchange in session["exchanges"]:
        lines += [f"## {exchange['seq']}. {exchange['prompt']}", ""]
        if exchange.get("why"):
            lines += [f"*{exchange['why']}*", ""]
        if exchange.get("skipped"):
            lines += ["> Skipped.", ""]
        elif exchange.get("answer"):
            lines += [exchange["answer"], ""]
        else:
            lines += ["> No answer recorded.", ""]
    return "\n".join(lines)


def write_transcript(session: dict) -> dict:
    """Write the transcript pair. Called after every answer, not only at the end."""
    directory = store.response_dir(paths.responses_dir(), session["id"])
    directory.mkdir(parents=True, exist_ok=True)
    stamp = session["stamp"]

    document = {
        "interview_id": session["id"],
        "title": session["title"],
        "kind": "interview",
        "domain": session.get("domain", ""),
        "respondent": session.get("respondent", ""),
        "started_at": session["started_at"],
        "ended_at": session.get("ended_at", ""),
        "counts": {
            "asked": len(session["exchanges"]),
            "answered": sum(1 for e in session["exchanges"] if not e.get("skipped")),
            "skipped": sum(1 for e in session["exchanges"] if e.get("skipped")),
        },
        "exchanges": session["exchanges"],
    }

    json_path = directory / f"{stamp}.json"
    json_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md_path = directory / f"{stamp}.md"
    md_path.write_text(transcript_markdown(session), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


# ------------------------------------------------------------------- server --


class Session:
    """In-memory state of a running interview, guarded by one condition."""

    def __init__(self, record: dict):
        self.record = record
        self.cond = threading.Condition()
        self.pending: dict | None = None
        self.closed = False
        self.seq = len(record.get("exchanges", []))
        self.last_activity = time.monotonic()

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def ask(self, question: dict, timeout: float | None) -> dict | None:
        """Push a question and wait for its answer. None if it never arrives."""
        with self.cond:
            if self.closed:
                return None
            self.seq += 1
            question = dict(question, seq=self.seq, asked_at=now_iso())
            self.pending = question
            self.touch()
            self.cond.notify_all()

            deadline = None if not timeout else time.monotonic() + timeout
            while True:
                answered = next(
                    (
                        e
                        for e in self.record["exchanges"]
                        if e["seq"] == question["seq"]
                    ),
                    None,
                )
                if answered is not None:
                    return answered
                if self.closed:
                    return None
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    # Stop presenting a question nobody is going to answer.
                    if self.pending and self.pending["seq"] == question["seq"]:
                        self.pending = None
                        self.cond.notify_all()
                    return None
                self.cond.wait(timeout=remaining if remaining else 1.0)

    def answer(self, seq: int, text: str, skipped: bool) -> bool:
        with self.cond:
            if not self.pending or self.pending["seq"] != seq:
                return False
            exchange = dict(self.pending)
            exchange["answer"] = text.strip()
            exchange["skipped"] = bool(skipped)
            exchange["answered_at"] = now_iso()
            self.record["exchanges"].append(exchange)
            self.pending = None
            self.touch()
            write_transcript(self.record)
            self.cond.notify_all()
            return True

    def wait_for_question(self, after: int) -> dict:
        """Long-poll. Returns the next question, or a waiting/done marker."""
        with self.cond:
            deadline = time.monotonic() + POLL_SECONDS
            while True:
                if self.closed:
                    return {"done": True, "summary": self.record.get("summary", "")}
                if self.pending and self.pending["seq"] > after:
                    return {"question": self.pending}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {"waiting": True}
                self.cond.wait(timeout=remaining)

    def close(self, summary: str = "") -> dict:
        with self.cond:
            if not self.closed:
                self.record["ended_at"] = now_iso()
                if summary:
                    self.record["summary"] = summary
                self.closed = True
                self.pending = None
                paths_written = write_transcript(self.record)
                self.record["transcript"] = {
                    k: str(v) for k, v in paths_written.items()
                }
            self.cond.notify_all()
            return self.record.get("transcript", {})


def serve(record: dict) -> None:
    """Run the interview server until it is closed or goes idle. Blocks."""
    from . import render

    session = Session(record)
    token = record["token"]
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _authorized(self) -> bool:
            return self.headers.get("X-QSurface-Token") == token

        def do_GET(self):
            route = self.path.split("?")[0]
            if route in ("/", "/index.html"):
                session.touch()
                body = render.interview_page(session.record).encode("utf-8")
                self._send(200, "text/html; charset=utf-8", body)
                return
            if route == "/poll":
                session.touch()
                after = 0
                if "?" in self.path:
                    query = self.path.split("?", 1)[1]
                    for part in query.split("&"):
                        if part.startswith("after="):
                            try:
                                after = int(part[6:])
                            except ValueError:
                                after = 0
                self._json(200, session.wait_for_question(after))
                return
            if route == "/control/state":
                if not self._authorized():
                    self._json(403, {"ok": False})
                    return
                self._json(
                    200,
                    {
                        "ok": True,
                        "id": session.record["id"],
                        "asked": session.seq,
                        "answered": len(session.record["exchanges"]),
                        "closed": session.closed,
                    },
                )
                return
            self._send(404, "text/plain", b"not found")

        def do_POST(self):
            route = self.path.split("?")[0]
            payload = self._body()
            if payload is None:
                return

            if route == "/answer":
                session.touch()
                ok = session.answer(
                    int(payload.get("seq") or 0),
                    str(payload.get("answer") or ""),
                    bool(payload.get("skipped")),
                )
                self._json(200 if ok else 409, {"ok": ok})
                return

            if not self._authorized():
                self._json(403, {"ok": False, "error": "bad token"})
                return

            if route == "/control/ask":
                session.touch()
                timeout = payload.get("timeout")
                answer = session.ask(payload.get("question") or {}, timeout)
                if answer is None:
                    self._json(200, {"ok": False, "reason": "no answer"})
                else:
                    self._json(200, {"ok": True, "answer": answer})
                return

            if route == "/control/close":
                written = session.close(str(payload.get("summary") or ""))
                self._json(200, {"ok": True, "transcript": written})
                stop.set()
                return

            self._json(404, {"ok": False})

        def _body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length < 0 or length > 8 * 1024 * 1024:
                self._json(400, {"ok": False, "error": "bad length"})
                return None
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return None

        def _json(self, code: int, obj: dict):
            self._send(code, "application/json", json.dumps(obj).encode("utf-8"))

        def _send(self, code: int, ctype: str, body: bytes):
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # The respondent closed the tab mid-poll. Not an error.
                pass

    httpd = ThreadingHTTPServer(("127.0.0.1", record["port"]), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        while not stop.is_set():
            if stop.wait(timeout=5):
                break
            if time.monotonic() - session.last_activity > IDLE_SHUTDOWN_SECONDS:
                session.close()
                break
    finally:
        httpd.shutdown()
        httpd.server_close()
        session_file(record["id"]).unlink(missing_ok=True)


# ------------------------------------------------------------------- client --


def control(session: dict, route: str, payload: dict, timeout: float | None = None):
    """Call the detached server's control API."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{session['port']}{route}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-QSurface-Token": session["token"],
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def health(session: dict, timeout: float = 2.0) -> dict | None:
    request = urllib.request.Request(
        f"http://127.0.0.1:{session['port']}/control/state",
        headers={"X-QSurface-Token": session["token"]},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def new_record(interview_id: str, title: str, domain: str, port: int) -> dict:
    return {
        "id": interview_id,
        "title": title,
        "domain": domain,
        "token": secrets.token_urlsafe(24),
        "port": port,
        "pid": 0,
        "respondent": store.detect_respondent(),
        "started_at": now_iso(),
        "stamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ"),
        "exchanges": [],
    }
