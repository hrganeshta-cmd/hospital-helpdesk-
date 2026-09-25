"""
Text-to-speech through Smallest.ai (Lightning), so callers hear a natural
Hindi / Marathi / English voice instead of the phone's built-in one.

The API key stays on the server (SMALLEST_API_KEY environment variable);
the phone only receives audio. Voices are chosen per reply language in
hospital_settings.json under "voice".
"""

import os
import re
import threading
from collections import OrderedDict

import requests

import agent_core

SMALLEST_URL = "https://api.smallest.ai/waves/v1/tts"
MAX_TEXT_CHARS = 1000          # longer requests are refused (cost guard)
CHUNK_CHARS = 240              # the API accepts at most 250 characters per request

_DEFAULT_VOICES = {
    "English": {"voice_id": "meher",   "language": "en", "model": "lightning_v3.1"},
    "Hindi":   {"voice_id": "sunidhi", "language": "hi", "model": "lightning_v3.1"},
    "Marathi": {"voice_id": "rupali",  "language": "mr", "model": "lightning_v3.1"},
}
VOICE_SETTINGS = agent_core.HOSPITAL_SETTINGS.get("voice", {})
VOICES = {lang: {**default, **VOICE_SETTINGS.get(lang, {})}
          for lang, default in _DEFAULT_VOICES.items()}
SPEED = float(VOICE_SETTINGS.get("speed", 1.0))


class TtsError(Exception):
    pass


def api_key():
    return os.environ.get("SMALLEST_API_KEY", "").strip()


def split_text(text, limit=CHUNK_CHARS):
    """Split at sentence ends (. ? ! ।), then at commas or spaces, so every
    piece fits the API's per-request limit."""
    pieces, current = [], ""
    for sentence in re.split(r"(?<=[.?!।])\s+", text.strip()):
        while len(sentence) > limit:
            cut = max(sentence.rfind(", ", 0, limit), sentence.rfind(" ", 0, limit))
            cut = cut if cut > 0 else limit
            if current:
                pieces.append(current); current = ""
            pieces.append(sentence[:cut].strip(" ,"))
            sentence = sentence[cut:].strip(" ,")
        if current and len(current) + 1 + len(sentence) > limit:
            pieces.append(current); current = ""
        current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return [p for p in pieces if p]


def _synthesize_piece(text, voice):
    response = requests.post(
        SMALLEST_URL,
        headers={"Authorization": f"Bearer {api_key()}",
                 "Content-Type": "application/json",
                 "Accept": "audio/mpeg"},
        json={"text": text,
              "voice_id": voice["voice_id"],
              "model": voice["model"],
              "language": voice["language"],
              "sample_rate": 24000,
              "speed": SPEED,
              "output_format": "mp3"},
        timeout=30,
    )
    if response.status_code != 200 or not response.content:
        # Only the status and the start of the message: never the key.
        raise TtsError(f"Smallest.ai {response.status_code}: {response.text[:200]}")
    return response.content


# Short, repeated phrases (greeting, "one moment", goodbye) are kept in
# memory so they play instantly and are not paid for twice.
_cache = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX_ITEMS = 64
_CACHEABLE_CHARS = 120


def synthesize(text, language=None):
    """MP3 bytes for text. language is English / Hindi / Marathi; when not
    given it is detected from the text."""
    text = (text or "").strip()
    if not text:
        raise TtsError("No text to speak.")
    if len(text) > MAX_TEXT_CHARS:
        raise TtsError(f"Text longer than {MAX_TEXT_CHARS} characters.")
    if not api_key():
        raise TtsError("SMALLEST_API_KEY is not set.")
    language = language if language in VOICES else agent_core.detect_language(text)
    voice = VOICES[language]

    key = (language, text)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]

    # MP3 frames can simply be joined, so long replies are made piece by piece.
    audio = b"".join(_synthesize_piece(piece, voice) for piece in split_text(text))

    if len(text) <= _CACHEABLE_CHARS:
        with _cache_lock:
            _cache[key] = audio
            while len(_cache) > _CACHE_MAX_ITEMS:
                _cache.popitem(last=False)
    return audio
