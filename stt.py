"""
Speech-to-text through Smallest.ai Pulse.

The phone records the caller and sends the audio here; Pulse works out
whether it is English, Hindi or Marathi by itself ("multi-indic"), so the
reception desk needs no language setting. Uses the same SMALLEST_API_KEY
as the voice (tts.py).
"""

import os

import requests

# India region: the multi-indic language set is served only there.
PULSE_URL = os.environ.get("SMALLEST_STT_URL", "https://api.india.smallest.ai/waves/v1/stt/")
PULSE_LANGUAGE = os.environ.get("SMALLEST_STT_LANGUAGE", "multi-indic")   # en + hi + mr (+ gu, bn, or)
MAX_AUDIO_BYTES = 5 * 1024 * 1024      # ~2.5 minutes of 16 kHz mono WAV; a caller's turn is far shorter


class SttError(Exception):
    pass


def transcribe(audio):
    """Text of the caller's speech ("" when nothing was said)."""
    if not audio:
        return ""
    if len(audio) > MAX_AUDIO_BYTES:
        raise SttError("Audio too long.")
    key = os.environ.get("SMALLEST_API_KEY", "").strip()
    if not key:
        raise SttError("SMALLEST_API_KEY is not set.")
    response = requests.post(
        PULSE_URL,
        params={"model": "pulse", "language": PULSE_LANGUAGE},
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/octet-stream"},   # raw WAV/MP3 bytes
        data=audio,
        timeout=30,
    )
    if response.status_code != 200:
        # Only the status and the start of the message: never the key.
        raise SttError(f"Pulse {response.status_code}: {response.text[:200]}")
    data = response.json()
    text = (data.get("transcript") or data.get("transcription") or data.get("text") or "").strip()
    if not text:
        print(f"--- Pulse returned no transcript; response keys: {sorted(data)} "
              f"start: {response.text[:300]} ---", flush=True)
    return text
