"""
Keeps the reception's Google Sheet in step with the bookings made here.

The Sheet (google_sheet/BookingSheet.gs, deployed as an Apps Script web app)
is the lasting record: it lists every booking and cancellation, emails the
doctor, and hands upcoming bookings back when this server restarts. The
Railway server's own database is erased on every redeploy, so without the
Sheet those bookings would be lost.

Railway variables:
    BOOKING_SHEET_URL     the Apps Script web app URL (ends in /exec)
    BOOKING_SYNC_SECRET   the secret printed by setup() in the script
When either is missing, syncing is skipped and the desk works as before.

Until the restore has succeeded, is_ready() is False and the desk takes a
call-back request instead of a booking, so no booking is ever made against
an empty database.
"""

import os
import threading
import time

import requests

_ready = threading.Event()
_failing = False          # True after a Sheet write gave up; cleared by the next success


def _config():
    return (os.environ.get("BOOKING_SHEET_URL", "").strip(),
            os.environ.get("BOOKING_SYNC_SECRET", "").strip())


def enabled():
    url, secret = _config()
    return bool(url and secret)


def is_ready():
    """True once upcoming bookings are loaded (or when no Sheet is set up)."""
    return _ready.is_set() or not enabled()


def status():
    return {"sheet": "configured" if enabled() else "not configured",
            "bookings_ready": is_ready(), "sheet_writes_failing": _failing}


def _post(payload, timeout=30):
    url, secret = _config()
    response = requests.post(url, json={**payload, "secret": secret}, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Sheet refused the request: {data.get('error')}")
    return data


def _send_with_retries(action, booking, attempts=6):
    global _failing
    label = booking.get("booking_id") or "call-back"
    for attempt in range(1, attempts + 1):
        try:
            _post({"action": action, "booking": booking})
            print(f"--- Sheet: {action} {label} ---", flush=True)
            _failing = False
            return
        except Exception as e:                  # network trouble or a Sheet error
            print(f"--- Sheet: {action} {label} failed "
                  f"(attempt {attempt}): {type(e).__name__} ---", flush=True)
            time.sleep(2 ** attempt)            # about 2 minutes in total
    _failing = True
    print(f"--- Sheet: GAVE UP on {action} {label}; "
          "add it to the Sheet by hand ---", flush=True)


def send(action, booking):
    """Record a booking ("booked"), cancellation ("cancelled") or call-back
    request ("callback") in the Sheet and email the doctor / reception.
    Runs in the background so the caller never waits."""
    if not enabled():
        return
    threading.Thread(target=_send_with_retries, args=(action, dict(booking)),
                     daemon=True).start()


def restore(save_appointments, doctors, attempts=None):
    """Give the Sheet the doctor list and load recent and upcoming bookings
    from it into the local database. Called once when the server starts; it
    keeps trying (every minute at most) until it succeeds, and bookings are
    taken only after that."""
    if not enabled():
        print("--- Sheet: not configured; bookings are kept on this server only ---", flush=True)
        _ready.set()
        return 0
    attempt = 0
    while attempts is None or attempt < attempts:
        attempt += 1
        try:
            data = _post({"action": "sync", "doctors": doctors}, timeout=60)
            bookings = data.get("bookings", [])
            save_appointments(bookings)
            _ready.set()
            print(f"--- Sheet: restored {len(bookings)} bookings ---", flush=True)
            return len(bookings)
        except Exception as e:
            print(f"--- Sheet: restore failed (attempt {attempt}): {type(e).__name__} ---", flush=True)
            time.sleep(min(60, 5 * attempt))
    return 0
