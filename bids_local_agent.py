"""
bids_local_agent.py  --  Local companion agent for brain-network-chart

Run this on your local machine:
    python3 bids_local_agent.py

Listens on http://127.0.0.1:7788 (local only, not exposed to network).
The web frontend will detect it and enable "Run" buttons in the
Post-processing Command panel.

Endpoints:
    GET  /health             -> {"status": "ok", "version": "1.0"}
    POST /run                -> {"cmd": "...", "cwd": "..."}  -> {"job_id": "..."}
    GET  /stream/<job_id>    -> SSE stream of output lines
    POST /cancel/<job_id>    -> cancel running job

Requires Python 3.7+. No external dependencies.
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
import uuid

LOCAL_AGENT_HOST = "127.0.0.1"
LOCAL_AGENT_PORT = 7789
AGENT_VERSION = "1.0"
JOB_TTL = 600  # seconds before a finished job is cleaned up

# Global job registry. Written by worker threads, read by stream handlers.
# Shape: {job_id: {"proc", "lines", "done", "exit_code", "lock", "finished_at"}}
jobs: dict = {}
jobs_lock = threading.Lock()


def _cleanup_old_jobs():
    """Remove finished jobs older than JOB_TTL seconds."""
    now = time.time()
    with jobs_lock:
        to_delete = [
            jid for jid, j in jobs.items()
            if j.get("done") and (now - (j.get("finished_at") or now)) > JOB_TTL
        ]
        for jid in to_delete:
            del jobs[jid]


def _run_job(job_id: str, cmd: str, cwd: str):
    """Worker thread: run cmd, capture output line by line."""
    job = jobs[job_id]
    try:
        with job["lock"]:
            job["lines"].append(f"[agent] cwd: {cwd}")
            job["lines"].append(f"[agent] cmd: {cmd}")
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        job["proc"] = proc
        for line in proc.stdout:
            with job["lock"]:
                job["lines"].append(line.rstrip("\n"))
        proc.wait()
        with job["lock"]:
            job["exit_code"] = proc.returncode
    except Exception as exc:
        with job["lock"]:
            job["lines"].append(f"[agent error] {exc}")
            job["exit_code"] = 1
    finally:
        with job["lock"]:
            job["done"] = True
            job["finished_at"] = time.time()


class AgentHandler(http.server.BaseHTTPRequestHandler):

    # ── CORS ────────────────────────────────────────────────────────────────

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _send_json(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw)

    # ── GET routing ──────────────────────────────────────────────────────────

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self._handle_health()
        elif path == "/info":
            self._handle_info()
        elif path == "/read_file":
            self._handle_read_file()
        elif path.startswith("/stream/"):
            job_id = path[len("/stream/"):]
            self._handle_stream(job_id)
        else:
            self._send_json(404, {"error": "not found"})

    # ── POST routing ─────────────────────────────────────────────────────────

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/run":
            self._handle_run()
        elif path.startswith("/cancel/"):
            job_id = path[len("/cancel/"):]
            self._handle_cancel(job_id)
        else:
            self._send_json(404, {"error": "not found"})

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _handle_health(self):
        self._send_json(200, {"status": "ok", "version": AGENT_VERSION})

    def _handle_info(self):
        """Return agent script directory so the frontend can locate dicom2bids_agent.py."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self._send_json(200, {"dir": script_dir, "python": sys.executable, "version": AGENT_VERSION})

    def _handle_read_file(self):
        """Return contents of a local file as plain text (used to read conversion_report.html)."""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        path = qs.get("path", [""])[0]
        if not path or not os.path.isfile(path):
            self._send_json(404, {"error": "file not found"})
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            data = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _handle_run(self):
        _cleanup_old_jobs()
        try:
            body = self._read_body()
            cmd = body.get("cmd", "").strip()
            cwd = body.get("cwd", os.path.expanduser("~"))
            if not cmd:
                self._send_json(400, {"error": "cmd is required"})
                return
            if not os.path.isdir(cwd):
                cwd = os.path.expanduser("~")
        except Exception as exc:
            self._send_json(400, {"error": f"bad request: {exc}"})
            return

        job_id = str(uuid.uuid4())
        with jobs_lock:
            jobs[job_id] = {
                "proc": None,
                "lines": [],
                "done": False,
                "exit_code": None,
                "lock": threading.Lock(),
                "finished_at": None,
            }

        t = threading.Thread(target=_run_job, args=(job_id, cmd, cwd), daemon=True)
        t.start()

        self._send_json(200, {"job_id": job_id})

    def _handle_stream(self, job_id: str):
        if job_id not in jobs:
            self._send_json(404, {"error": "unknown job"})
            return

        # Send SSE headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._set_cors_headers()
        self.end_headers()

        job = jobs[job_id]
        sent = 0

        try:
            while True:
                with job["lock"]:
                    new_lines = job["lines"][sent:]
                    is_done = job["done"]
                    exit_code = job["exit_code"]

                for line in new_lines:
                    escaped = line.replace("\n", "\\n")
                    self.wfile.write(f"data: {escaped}\n\n".encode())
                    sent += 1

                if new_lines:
                    self.wfile.flush()

                if is_done and sent >= len(job["lines"]):
                    payload = json.dumps({"exit_code": exit_code})
                    self.wfile.write(f"event: done\ndata: {payload}\n\n".encode())
                    self.wfile.flush()
                    break

                time.sleep(0.05)

        except (BrokenPipeError, ConnectionResetError):
            pass  # client disconnected; job continues

    def _handle_cancel(self, job_id: str):
        job = jobs.get(job_id)
        if not job:
            self._send_json(404, {"error": "unknown job"})
            return
        proc = job.get("proc")
        if proc and proc.poll() is None:
            proc.terminate()
            def _force_kill():
                time.sleep(2)
                try:
                    if proc.poll() is None:
                        proc.kill()
                except Exception:
                    pass
            threading.Thread(target=_force_kill, daemon=True).start()
        self._send_json(200, {"status": "cancelled"})

    # ── Logging ──────────────────────────────────────────────────────────────

    def log_message(self, format, *args):
        # Suppress noisy /health polling; log everything else
        msg = format % args if args else format
        if "/health" not in msg:
            sys.stderr.write(f"[agent] {self.address_string()} {msg}\n")


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = http.server.HTTPServer((LOCAL_AGENT_HOST, LOCAL_AGENT_PORT), AgentHandler)
    print(f"Local agent listening on http://{LOCAL_AGENT_HOST}:{LOCAL_AGENT_PORT}")
    print("Keep this window open while running pipeline steps.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()
