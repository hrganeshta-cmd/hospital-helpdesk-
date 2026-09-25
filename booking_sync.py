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
"""

import os
import threading
import time

import requests


def _config():
    return (os.environ.get("BOOKING_SHEET_URL", "").strip(),
            os.environ.get("BOOKING_SYNC_SECRET", "").strip())


def enabled():
    url, secret = _config()
    return bool(url and secret)


def _post(payload, timeout=30):
    url, secret = _config()
    response = requests.post(url, json={**payload, "secret": secret}, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Sheet refused the request: {data.get('error')}")
    return data


def _send_with_retries(action, booking, attempts=4):
    for attempt in range(1, attempts + 1):
        try:
            _post({"action": action, "booking": booking})
            print(f"--- Sheet: {action} {booking.get('booking_id')} ---", flush=True)
            return
        except Exception as e:                  # network trouble or a Sheet error
            print(f"--- Sheet: {action} {booking.get('booking_id')} failed "
                  f"(attempt {attempt}): {type(e).__name__}: {e} ---", flush=True)
            time.sleep(2 ** attempt)
    print(f"--- Sheet: GAVE UP on {action} {booking.get('booking_id')}; "
          "add it to the Sheet by hand ---", flush=True)


def send(action, booking):
    """Record a booking ("booked") or cancellation ("cancelled") in the Sheet
    and email the doctor. Runs in the background so the caller never waits."""
    if not enabled():
        return
    threading.Thread(target=_send_with_retries, args=(action, dict(booking)),
                     daemon=True).start()


def restore(save_appointments, doctors):
    """Give the Sheet the doctor list and load today's and future bookings
    from it into the local database. Called once when the server starts."""
    if not enabled():
        print("--- Sheet: not configured; bookings are kept on this server only ---", flush=True)
        return 0
    for attempt in range(1, 4):
        try:
            data = _post({"action": "sync", "doctors": doctors}, timeout=60)
            bookings = data.get("bookings", [])
            save_appointments(bookings)
            print(f"--- Sheet: restored {len(bookings)} upcoming bookings ---", flush=True)
            return len(bookings)
        except Exception as e:
            print(f"--- Sheet: restore failed (attempt {attempt}): "
                  f"{type(e).__name__}: {e} ---", flush=True)
            time.sleep(5 * attempt)
    return 0
