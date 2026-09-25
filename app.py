"""
Hospital Help Desk — API server.

Runs the receptionist agent behind a small HTTP API so that Android phones
(or any other client) can talk to it.

Endpoints
---------
GET  /api/health            -> {"status": "ok"}
POST /api/session/start     -> {"session_id": "..."} and the greeting text
POST /api/chat              -> body {"session_id": "...", "message": "..."}
                               returns {"reply": "..."}
POST /api/session/end       -> body {"session_id": "..."}; frees the session

Run on Windows Server:
    set OPENAI_API_KEY=sk-...        (Command Prompt)
    python app.py
The server listens on port 8000 on all network interfaces.
"""

import os
import threading
import time
import uuid

from flask import Flask, jsonify, request, send_from_directory

import agent_core
import booking_sync

app = Flask(__name__)

GREETING = "Hello, welcome to Hospital Reception Desk. How can I assist you today?"

# One agent per caller session, protected by a lock because Flask
# serves requests on multiple threads.
_sessions = {}
_last_used = {}
_lock = threading.Lock()

SESSION_TIMEOUT_SECONDS = 30 * 60  # sessions idle for 30 minutes are removed

# This server's database starts empty after every redeploy; reload upcoming
# bookings from the reception's Google Sheet (in the background, so the
# health check is not held up).
_DOCTORS = sorted(
    ({"name": name, "department": info["department"]}
     for day in agent_core.DOCTOR_SCHEDULE.values() for name, info in day.items()),
    key=lambda d: d["name"])
_DOCTORS = [d for i, d in enumerate(_DOCTORS) if i == 0 or d["name"] != _DOCTORS[i - 1]["name"]]
threading.Thread(target=booking_sync.restore,
                 args=(agent_core.save_appointments, _DOCTORS), daemon=True).start()


def _cleanup_idle_sessions():
    now = time.time()
    stale = [sid for sid, t in _last_used.items()
             if now - t > SESSION_TIMEOUT_SECONDS]
    for sid in stale:
        _sessions.pop(sid, None)
        _last_used.pop(sid, None)


@app.get("/")
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "chat.html")


@app.get("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"),
        filename
    )


# Optional device key. When DEVICE_KEY is set (Railway variable), every
# /api/ request except the health check must carry it in the X-Device-Key
# header, so only the reception phones can use the desk and its paid APIs.
DEVICE_KEY = os.environ.get("DEVICE_KEY", "").strip()


@app.before_request
def check_device_key():
    if DEVICE_KEY and request.path.startswith("/api/") and request.path != "/api/health":
        if request.headers.get("X-Device-Key", "") != DEVICE_KEY:
            return jsonify({"error": "Not allowed."}), 401


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", **booking_sync.status()})


@app.post("/api/session/start")
def session_start():
    with _lock:
        _cleanup_idle_sessions()
        session_id = uuid.uuid4().hex
        _sessions[session_id] = agent_core.HospitalReceptionistAgent()
        _last_used[session_id] = time.time()
    return jsonify({"session_id": session_id, "greeting": GREETING})


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "The 'message' field is required."}), 400
    session_id, reply = _answer(session_id, message)
    return jsonify({"session_id": session_id, "reply": reply})


def _answer(session_id, message):
    with _lock:
        agent = _sessions.get(session_id)
        if agent is None:
            # Unknown or expired session: start a fresh one transparently.
            session_id = uuid.uuid4().hex
            agent = agent_core.HospitalReceptionistAgent()
            _sessions[session_id] = agent
        _last_used[session_id] = time.time()

    # The OpenAI call happens outside the lock so one slow call
    # does not block every other caller.
    return session_id, agent.process_user_input(message)


@app.post("/api/session/end")
def session_end():
    data = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    with _lock:
        _sessions.pop(session_id, None)
        _last_used.pop(session_id, None)
    return jsonify({"status": "ended"})


if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 8000))
    serve(app, host="0.0.0.0", port=port)
