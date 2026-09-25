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
POST /api/voice?session_id= -> body: the caller's recorded speech (WAV)
                               returns {"heard": "...", "reply": "..."}; the
                               language (English/Hindi/Marathi) is detected
POST /api/tts               -> body {"text": "...", "language": "Marathi"}
                               returns MP3 audio (Smallest.ai voice)
GET  /api/tts?text=...      -> same, for trying a voice in a browser
GET  /voices                -> page with sample phrases in each language

Run on Windows Server:
    set OPENAI_API_KEY=sk-...        (Command Prompt)
    python app.py
The server listens on port 8000 on all network interfaces.
"""

import os
import threading
import time
import uuid

from html import escape
from urllib.parse import quote

from flask import Flask, Response, jsonify, request, send_from_directory

import agent_core
import booking_sync
import stt
import tts

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
    session_id, reply = _answer(session_id, message)
    return jsonify({"session_id": session_id, "reply": reply})


@app.post("/api/voice")
def voice():
    """One caller turn from recorded audio: speech -> text (Pulse, language
    detected automatically) -> the receptionist's reply."""
    session_id = (request.args.get("session_id") or "").strip()
    try:
        heard = stt.transcribe(request.get_data())
    except Exception as e:                      # Pulse unreachable or refused
        print(f"--- STT error: {type(e).__name__}: {e} ---", flush=True)
        return jsonify({"error": "Could not hear that right now."}), 502
    print(f"--- Heard: {heard!r} ---", flush=True)
    if not heard:
        return jsonify({"session_id": session_id, "heard": "", "reply": ""})
    session_id, reply = _answer(session_id, heard)
    return jsonify({"session_id": session_id, "heard": heard, "reply": reply})


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


@app.route("/api/tts", methods=["GET", "POST"])
def text_to_speech():
    data = (request.get_json(silent=True) or {}) if request.method == "POST" else request.args
    text = (data.get("text") or "").strip()
    language = (data.get("language") or data.get("lang") or "").strip().capitalize() or None
    try:
        audio = tts.synthesize(text, language)
    except tts.TtsError as e:
        print(f"--- TTS error: {e} ---", flush=True)
        return jsonify({"error": "Voice is not available right now."}), 502
    except Exception as e:                        # network trouble reaching Smallest.ai
        print(f"--- TTS error: {type(e).__name__}: {e} ---", flush=True)
        return jsonify({"error": "Voice is not available right now."}), 502
    return Response(audio, mimetype="audio/mpeg")


VOICE_SAMPLES = [
    ("English", GREETING),
    ("English", "Dr. Neha Kapadia is available on Monday from 9 AM to 1 PM."),
    ("Hindi", "नमस्ते, अस्पताल रिसेप्शन डेस्क में आपका स्वागत है। मैं आपकी क्या सहायता कर सकती हूँ?"),
    ("Hindi", "डॉ. विक्रम देसाई सोमवार को उपलब्ध हैं। उनका समय सुबह 9 बजे से दोपहर 1 बजे तक है।"),
    ("Marathi", "नमस्कार, रुग्णालय स्वागत कक्षात आपले स्वागत आहे. मी आपली काय मदत करू शकते?"),
    ("Marathi", "डॉ. नेहा कपाडिया सोमवारी उपलब्ध आहेत. त्यांची वेळ सकाळी ९ ते दुपारी १ पर्यंत आहे."),
]


@app.get("/voices")
def voices_page():
    rows = "".join(
        f"<h3>{escape(lang)} · {escape(tts.VOICES[lang]['voice_id'])}</h3><p>{escape(text)}</p>"
        f"<audio controls preload='none' src='/api/tts?lang={lang}&amp;text={quote(text)}'></audio>"
        for lang, text in VOICE_SAMPLES)
    return (f"<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            f"<title>Voice samples</title><body style='font-family:sans-serif;max-width:640px;"
            f"margin:auto;padding:16px'><h1>Reception desk voices</h1>{rows}</body>")


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
