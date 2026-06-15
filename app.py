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

app = Flask(__name__)

GREETING = "Hello, welcome to Hospital Reception Desk. How can I assist you today?"

# One agent per caller session, protected by a lock because Flask
# serves requests on multiple threads.
_sessions = {}
_last_used = {}
_lock = threading.Lock()

SESSION_TIMEOUT_SECONDS = 30 * 60  # sessions idle for 30 minutes are removed


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


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


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
    reply = agent.process_user_input(message)
    return jsonify({"session_id": session_id, "reply": reply})


@app.post("/api/session/end")
def session_end():
    data = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    with _lock:
        _sessions.pop(session_id, None)
        _last_used.pop(session_id, None)
    return jsonify({"status": "ended"})


if __name__ == "__main__":
    # For production on Windows Server, run behind waitress:
    #   pip install waitress
    #   waitress-serve --listen=0.0.0.0:8000 app:app
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
