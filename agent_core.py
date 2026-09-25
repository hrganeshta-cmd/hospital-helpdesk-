import os
import json
import random
import re
import sqlite3
import sys
import traceback
from datetime import date, datetime

from openai import OpenAI

import booking_flow as bf
import booking_sync

# ---------------------------------------------------------------------------
# 1. API CONFIGURATION
# ---------------------------------------------------------------------------
# The key is read from the environment. Never write keys inside source code.
# On Windows Server (PowerShell):  $env:OPENAI_API_KEY = "sk-..."
# Or set it permanently in System Properties > Environment Variables.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# 1b. HOSPITAL SETTINGS
#     Everything specific to one hospital (name, address, phone, booking ID
#     prefix) lives in hospital_settings.json, so the same code can be
#     installed at another hospital by editing only that file.
#     HOSPITAL_SETTINGS_PATH may point to a different file.
# ---------------------------------------------------------------------------
SETTINGS_PATH = os.environ.get("HOSPITAL_SETTINGS_PATH",
                               os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "hospital_settings.json"))

with open(SETTINGS_PATH, encoding="utf-8") as _f:
    HOSPITAL_SETTINGS = json.load(_f)

HOSPITAL_NAME     = HOSPITAL_SETTINGS["hospital_name"]
RECEPTIONIST_NAME = HOSPITAL_SETTINGS["receptionist_name"]
BOOKING_ID_PREFIX = HOSPITAL_SETTINGS["booking_id_prefix"]
APPOINTMENT_PHONE = HOSPITAL_SETTINGS["appointment_phone"]
LOCATION_ANSWER   = HOSPITAL_SETTINGS["location_answer"]
BOOKING_ID_FORMAT = f"{BOOKING_ID_PREFIX}-4829"          # prefix + 4 digits

# ---------------------------------------------------------------------------
# 3. DOCTOR OPD SCHEDULES  — Monday through Saturday (Sunday: OPD closed)
#    Every doctor keeps one fixed slot on each day they sit; every slot has
#    an end time inside OPD hours (08:30 AM - 05:00 PM); doctors in the same
#    department never overlap on the same day; no two doctors share a first
#    or last name, so a spoken name always resolves to one doctor.
# ---------------------------------------------------------------------------
DOCTOR_SCHEDULE = {
    "MONDAY": {
        "DR. SNEHA IYER":       {"department": "DENTAL",                       "from": "08:30 AM", "to": "12:30 PM"},
        "DR. ROHAN BHATT":      {"department": "DENTAL",                       "from": "01:00 PM", "to": "05:00 PM"},
        "DR. NEHA KAPADIA":     {"department": "DERMATOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. NIKHIL JOSHI":     {"department": "ENDOCRINOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. PRAKASH HEGDE":    {"department": "ENT",                          "from": "09:00 AM", "to": "01:00 PM"},
        "DR. YAMINI GHATGE":    {"department": "ENT",                          "from": "01:30 PM", "to": "04:30 PM"},
        "DR. ARVIND MEHTA":     {"department": "GENERAL MEDICINE",             "from": "08:30 AM", "to": "12:30 PM"},
        "DR. KAVITA RAO":       {"department": "GENERAL MEDICINE",             "from": "01:00 PM", "to": "05:00 PM"},
        "DR. DEEPA REDDY":      {"department": "GYNAECOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. RITU CHAWLA":      {"department": "GYNAECOLOGY",                  "from": "01:30 PM", "to": "05:00 PM"},
        "DR. GAURAV SINHA":     {"department": "INFECTIOUS DISEASES",          "from": "01:00 PM", "to": "03:00 PM"},
        "DR. HARISH MENON":     {"department": "MEDICAL GASTROENTEROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. LAKSHMI SUNDARAM": {"department": "MEDICAL ONCOLOGY",             "from": "03:00 PM", "to": "05:00 PM"},
        "DR. VIKRAM DESAI":     {"department": "NEPHROLOGY",                   "from": "09:00 AM", "to": "01:00 PM"},
        "DR. MEERA PILLAI":     {"department": "NEPHROLOGY",                   "from": "01:30 PM", "to": "05:00 PM"},
        "DR. VARUN KHANNA":     {"department": "NEUROSURGERY",                 "from": "08:30 AM", "to": "12:00 PM"},
        "DR. IMRAN SHAIKH":     {"department": "OPHTHALMOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. FARHAN QURESHI":   {"department": "ORAL & MAXILLOFACIAL SURGERY", "from": "02:30 PM", "to": "04:30 PM"},
        "DR. MOHAN CHANDRA":    {"department": "ORTHOPAEDICS",                 "from": "11:30 AM", "to": "02:30 PM"},
        "DR. TANVI SAXENA":     {"department": "RADIATION ONCOLOGY",           "from": "03:00 PM", "to": "05:00 PM"},
        "DR. MANISH AGARWAL":   {"department": "SPINE SURGERY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. RADHIKA IYENGAR":  {"department": "SUPPORTIVE & ASSISTED CARE",   "from": "11:00 AM", "to": "04:00 PM"},
        "DR. KARAN MALHOTRA":   {"department": "SURGICAL ONCOLOGY",            "from": "10:00 AM", "to": "01:00 PM"},
        "DR. ADITYA KAPOOR":    {"department": "UROLOGY",                      "from": "09:30 AM", "to": "12:30 PM"},
        "DR. SIDDHARTH RANE":   {"department": "UROLOGY",                      "from": "01:00 PM", "to": "04:00 PM"},
    },
    "TUESDAY": {
        "DR. SNEHA IYER":       {"department": "DENTAL",                       "from": "08:30 AM", "to": "12:30 PM"},
        "DR. ROHAN BHATT":      {"department": "DENTAL",                       "from": "01:00 PM", "to": "05:00 PM"},
        "DR. ANKIT TIWARI":     {"department": "DERMATOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. NIKHIL JOSHI":     {"department": "ENDOCRINOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. PRAKASH HEGDE":    {"department": "ENT",                          "from": "09:00 AM", "to": "01:00 PM"},
        "DR. ARVIND MEHTA":     {"department": "GENERAL MEDICINE",             "from": "08:30 AM", "to": "12:30 PM"},
        "DR. KAVITA RAO":       {"department": "GENERAL MEDICINE",             "from": "01:00 PM", "to": "05:00 PM"},
        "DR. DEEPA REDDY":      {"department": "GYNAECOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. RITU CHAWLA":      {"department": "GYNAECOLOGY",                  "from": "01:30 PM", "to": "05:00 PM"},
        "DR. HARISH MENON":     {"department": "MEDICAL GASTROENTEROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. VIKRAM DESAI":     {"department": "NEPHROLOGY",                   "from": "09:00 AM", "to": "01:00 PM"},
        "DR. MEERA PILLAI":     {"department": "NEPHROLOGY",                   "from": "01:30 PM", "to": "05:00 PM"},
        "DR. ISHITA BANERJEE":  {"department": "NEUROLOGY",                    "from": "02:00 PM", "to": "05:00 PM"},
        "DR. VARUN KHANNA":     {"department": "NEUROSURGERY",                 "from": "08:30 AM", "to": "12:00 PM"},
        "DR. SHALINI BOSE":     {"department": "OPHTHALMOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. MOHAN CHANDRA":    {"department": "ORTHOPAEDICS",                 "from": "11:30 AM", "to": "02:30 PM"},
        "DR. AJAY THAKUR":      {"department": "PAEDIATRIC SURGERY",           "from": "10:00 AM", "to": "12:00 PM"},
        "DR. REKHA JAIN":       {"department": "PAIN MANAGEMENT",              "from": "02:00 PM", "to": "04:00 PM"},
        "DR. MANISH AGARWAL":   {"department": "SPINE SURGERY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. RADHIKA IYENGAR":  {"department": "SUPPORTIVE & ASSISTED CARE",   "from": "11:00 AM", "to": "04:00 PM"},
        "DR. KARAN MALHOTRA":   {"department": "SURGICAL ONCOLOGY",            "from": "10:00 AM", "to": "01:00 PM"},
        "DR. ADITYA KAPOOR":    {"department": "UROLOGY",                      "from": "09:30 AM", "to": "12:30 PM"},
        "DR. SIDDHARTH RANE":   {"department": "UROLOGY",                      "from": "01:00 PM", "to": "04:00 PM"},
    },
    "WEDNESDAY": {
        "DR. SNEHA IYER":       {"department": "DENTAL",                       "from": "08:30 AM", "to": "12:30 PM"},
        "DR. ROHAN BHATT":      {"department": "DENTAL",                       "from": "01:00 PM", "to": "05:00 PM"},
        "DR. NEHA KAPADIA":     {"department": "DERMATOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. NIKHIL JOSHI":     {"department": "ENDOCRINOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. PRAKASH HEGDE":    {"department": "ENT",                          "from": "09:00 AM", "to": "01:00 PM"},
        "DR. YAMINI GHATGE":    {"department": "ENT",                          "from": "01:30 PM", "to": "04:30 PM"},
        "DR. ARVIND MEHTA":     {"department": "GENERAL MEDICINE",             "from": "08:30 AM", "to": "12:30 PM"},
        "DR. KAVITA RAO":       {"department": "GENERAL MEDICINE",             "from": "01:00 PM", "to": "05:00 PM"},
        "DR. SURESH NAIDU":     {"department": "GENERAL SURGERY",              "from": "11:00 AM", "to": "01:00 PM"},
        "DR. DEEPA REDDY":      {"department": "GYNAECOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. RITU CHAWLA":      {"department": "GYNAECOLOGY",                  "from": "01:30 PM", "to": "05:00 PM"},
        "DR. SUNITA MATHUR":    {"department": "INFERTILITY",                  "from": "02:00 PM", "to": "05:00 PM"},
        "DR. ABHAY DUTTA":      {"department": "LIVER CLINIC",                 "from": "03:00 PM", "to": "05:00 PM"},
        "DR. HARISH MENON":     {"department": "MEDICAL GASTROENTEROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. LAKSHMI SUNDARAM": {"department": "MEDICAL ONCOLOGY",             "from": "03:00 PM", "to": "05:00 PM"},
        "DR. VIKRAM DESAI":     {"department": "NEPHROLOGY",                   "from": "09:00 AM", "to": "01:00 PM"},
        "DR. MEERA PILLAI":     {"department": "NEPHROLOGY",                   "from": "01:30 PM", "to": "05:00 PM"},
        "DR. ISHITA BANERJEE":  {"department": "NEUROLOGY",                    "from": "02:00 PM", "to": "05:00 PM"},
        "DR. VARUN KHANNA":     {"department": "NEUROSURGERY",                 "from": "08:30 AM", "to": "12:00 PM"},
        "DR. IMRAN SHAIKH":     {"department": "OPHTHALMOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. MOHAN CHANDRA":    {"department": "ORTHOPAEDICS",                 "from": "11:30 AM", "to": "02:30 PM"},
        "DR. KUNAL ARORA":      {"department": "PLASTIC SURGERY",              "from": "02:30 PM", "to": "04:30 PM"},
        "DR. TANVI SAXENA":     {"department": "RADIATION ONCOLOGY",           "from": "03:00 PM", "to": "05:00 PM"},
        "DR. MANISH AGARWAL":   {"department": "SPINE SURGERY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. RADHIKA IYENGAR":  {"department": "SUPPORTIVE & ASSISTED CARE",   "from": "11:00 AM", "to": "04:00 PM"},
        "DR. KARAN MALHOTRA":   {"department": "SURGICAL ONCOLOGY",            "from": "10:00 AM", "to": "01:00 PM"},
        "DR. NANDINI GHOSH":    {"department": "SURGICAL ONCOLOGY",            "from": "02:00 PM", "to": "05:00 PM"},
        "DR. ADITYA KAPOOR":    {"department": "UROLOGY",                      "from": "09:30 AM", "to": "12:30 PM"},
        "DR. SIDDHARTH RANE":   {"department": "UROLOGY",                      "from": "01:00 PM", "to": "04:00 PM"},
    },
    "THURSDAY": {
        "DR. SNEHA IYER":       {"department": "DENTAL",                       "from": "08:30 AM", "to": "12:30 PM"},
        "DR. ROHAN BHATT":      {"department": "DENTAL",                       "from": "01:00 PM", "to": "05:00 PM"},
        "DR. ANKIT TIWARI":     {"department": "DERMATOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. NIKHIL JOSHI":     {"department": "ENDOCRINOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. PRAKASH HEGDE":    {"department": "ENT",                          "from": "09:00 AM", "to": "01:00 PM"},
        "DR. ARVIND MEHTA":     {"department": "GENERAL MEDICINE",             "from": "08:30 AM", "to": "12:30 PM"},
        "DR. KAVITA RAO":       {"department": "GENERAL MEDICINE",             "from": "01:00 PM", "to": "05:00 PM"},
        "DR. DEEPA REDDY":      {"department": "GYNAECOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. GAURAV SINHA":     {"department": "INFECTIOUS DISEASES",          "from": "01:00 PM", "to": "03:00 PM"},
        "DR. HARISH MENON":     {"department": "MEDICAL GASTROENTEROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. VIKRAM DESAI":     {"department": "NEPHROLOGY",                   "from": "09:00 AM", "to": "01:00 PM"},
        "DR. MEERA PILLAI":     {"department": "NEPHROLOGY",                   "from": "01:30 PM", "to": "05:00 PM"},
        "DR. VARUN KHANNA":     {"department": "NEUROSURGERY",                 "from": "08:30 AM", "to": "12:00 PM"},
        "DR. SHALINI BOSE":     {"department": "OPHTHALMOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. FARHAN QURESHI":   {"department": "ORAL & MAXILLOFACIAL SURGERY", "from": "02:30 PM", "to": "04:30 PM"},
        "DR. MOHAN CHANDRA":    {"department": "ORTHOPAEDICS",                 "from": "11:30 AM", "to": "02:30 PM"},
        "DR. REKHA JAIN":       {"department": "PAIN MANAGEMENT",              "from": "02:00 PM", "to": "04:00 PM"},
        "DR. MANISH AGARWAL":   {"department": "SPINE SURGERY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. RADHIKA IYENGAR":  {"department": "SUPPORTIVE & ASSISTED CARE",   "from": "11:00 AM", "to": "04:00 PM"},
        "DR. KARAN MALHOTRA":   {"department": "SURGICAL ONCOLOGY",            "from": "10:00 AM", "to": "01:00 PM"},
        "DR. SIDDHARTH RANE":   {"department": "UROLOGY",                      "from": "01:00 PM", "to": "04:00 PM"},
    },
    "FRIDAY": {
        "DR. SNEHA IYER":       {"department": "DENTAL",                       "from": "08:30 AM", "to": "12:30 PM"},
        "DR. ROHAN BHATT":      {"department": "DENTAL",                       "from": "01:00 PM", "to": "05:00 PM"},
        "DR. NEHA KAPADIA":     {"department": "DERMATOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. NIKHIL JOSHI":     {"department": "ENDOCRINOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. PRAKASH HEGDE":    {"department": "ENT",                          "from": "09:00 AM", "to": "01:00 PM"},
        "DR. ARVIND MEHTA":     {"department": "GENERAL MEDICINE",             "from": "08:30 AM", "to": "12:30 PM"},
        "DR. KAVITA RAO":       {"department": "GENERAL MEDICINE",             "from": "01:00 PM", "to": "05:00 PM"},
        "DR. SURESH NAIDU":     {"department": "GENERAL SURGERY",              "from": "11:00 AM", "to": "01:00 PM"},
        "DR. DEEPA REDDY":      {"department": "GYNAECOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. HARISH MENON":     {"department": "MEDICAL GASTROENTEROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. VIKRAM DESAI":     {"department": "NEPHROLOGY",                   "from": "09:00 AM", "to": "01:00 PM"},
        "DR. MEERA PILLAI":     {"department": "NEPHROLOGY",                   "from": "01:30 PM", "to": "05:00 PM"},
        "DR. ISHITA BANERJEE":  {"department": "NEUROLOGY",                    "from": "02:00 PM", "to": "05:00 PM"},
        "DR. VARUN KHANNA":     {"department": "NEUROSURGERY",                 "from": "08:30 AM", "to": "12:00 PM"},
        "DR. IMRAN SHAIKH":     {"department": "OPHTHALMOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. MOHAN CHANDRA":    {"department": "ORTHOPAEDICS",                 "from": "11:30 AM", "to": "02:30 PM"},
        "DR. AJAY THAKUR":      {"department": "PAEDIATRIC SURGERY",           "from": "10:00 AM", "to": "12:00 PM"},
        "DR. KUNAL ARORA":      {"department": "PLASTIC SURGERY",              "from": "02:30 PM", "to": "04:30 PM"},
        "DR. RADHIKA IYENGAR":  {"department": "SUPPORTIVE & ASSISTED CARE",   "from": "11:00 AM", "to": "04:00 PM"},
        "DR. KARAN MALHOTRA":   {"department": "SURGICAL ONCOLOGY",            "from": "10:00 AM", "to": "01:00 PM"},
        "DR. ADITYA KAPOOR":    {"department": "UROLOGY",                      "from": "09:30 AM", "to": "12:30 PM"},
    },
    "SATURDAY": {
        "DR. SNEHA IYER":       {"department": "DENTAL",                       "from": "08:30 AM", "to": "12:30 PM"},
        "DR. POOJA NAIR":       {"department": "DENTAL",                       "from": "01:00 PM", "to": "05:00 PM"},
        "DR. ANKIT TIWARI":     {"department": "DERMATOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. PRAKASH HEGDE":    {"department": "ENT",                          "from": "09:00 AM", "to": "01:00 PM"},
        "DR. ARVIND MEHTA":     {"department": "GENERAL MEDICINE",             "from": "08:30 AM", "to": "12:30 PM"},
        "DR. KAVITA RAO":       {"department": "GENERAL MEDICINE",             "from": "01:00 PM", "to": "05:00 PM"},
        "DR. DEEPA REDDY":      {"department": "GYNAECOLOGY",                  "from": "09:00 AM", "to": "01:00 PM"},
        "DR. HARISH MENON":     {"department": "MEDICAL GASTROENTEROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. VIKRAM DESAI":     {"department": "NEPHROLOGY",                   "from": "09:00 AM", "to": "01:00 PM"},
        "DR. ISHITA BANERJEE":  {"department": "NEUROLOGY",                    "from": "02:00 PM", "to": "05:00 PM"},
        "DR. VARUN KHANNA":     {"department": "NEUROSURGERY",                 "from": "08:30 AM", "to": "12:00 PM"},
        "DR. SHALINI BOSE":     {"department": "OPHTHALMOLOGY",                "from": "09:00 AM", "to": "01:00 PM"},
        "DR. TEJAS PANDE":      {"department": "ORTHOPAEDICS",                 "from": "09:00 AM", "to": "12:00 PM"},
        "DR. NANDINI GHOSH":    {"department": "SURGICAL ONCOLOGY",            "from": "02:00 PM", "to": "05:00 PM"},
    },
}

# ---------------------------------------------------------------------------
# 4. APPOINTMENT STORAGE — SQLite database
#    The Railway disk is wiped on every redeploy; booking_sync reloads the
#    bookings from the reception's Google Sheet when the server starts.
#    One confirmed booking per doctor per 30-minute slot is enforced by the
#    database itself, so two callers can never get the same slot.
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get("HOSPITAL_DB_PATH",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "appointments.db"))


def _get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            booking_id      TEXT NOT NULL,
            patient_name    TEXT NOT NULL,
            phone_number    TEXT NOT NULL,
            date            TEXT NOT NULL,
            time            TEXT NOT NULL,
            purpose         TEXT,
            consultant_name TEXT NOT NULL,
            department      TEXT,
            status          TEXT NOT NULL DEFAULT 'Confirmed',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (booking_id, date)
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_slot
        ON appointments (consultant_name, date, time) WHERE status = 'Confirmed'
    """)
    return conn


_COLUMNS = ["booking_id", "patient_name", "phone_number", "date", "time",
            "purpose", "consultant_name", "department", "status"]


def load_appointments():
    conn = _get_db()
    try:
        rows = conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM appointments").fetchall()
        return [dict(zip(_COLUMNS, row)) for row in rows]
    finally:
        conn.close()


def save_appointments(appointments):
    """Insert any appointment not yet stored (used to restore from the Sheet)."""
    conn = _get_db()
    try:
        for a in appointments:
            conn.execute(
                f"INSERT OR IGNORE INTO appointments ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
                [a.get(c, "") for c in _COLUMNS],
            )
    finally:
        conn.close()


def booked_times(doctor_key, iso_date):
    """Times ('11:00 AM') already booked with this doctor on this date."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT time FROM appointments WHERE consultant_name = ? AND date = ? "
            "AND status = 'Confirmed'", (doctor_key, iso_date)).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def _new_booking_id(conn, iso_date):
    """PREFIX + 4 digits, not used by any booking on record. With about 50
    bookings a day the 9,000 numbers repeat only after several months, and a
    booking is always identified together with its date and mobile number."""
    for _ in range(200):
        bid = f"{BOOKING_ID_PREFIX}-{random.randint(1000, 9999)}"
        if not conn.execute("SELECT 1 FROM appointments WHERE booking_id = ?", (bid,)).fetchone():
            return bid
    raise RuntimeError("No free booking ID")


def book_slot(name, phone, day, t, reason, doctor_key):
    """Book atomically. Returns the stored record, or None if the slot was
    taken in the meantime."""
    iso, hhmm = day.isoformat(), t.strftime("%I:%M %p")
    conn = _get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM appointments WHERE consultant_name = ? AND date = ? "
                        "AND time = ? AND status = 'Confirmed'", (doctor_key, iso, hhmm)).fetchone():
            conn.execute("ROLLBACK")
            return None
        record = {
            "booking_id": _new_booking_id(conn, iso), "patient_name": name, "phone_number": phone,
            "date": iso, "time": hhmm, "purpose": reason, "consultant_name": doctor_key,
            "department": bf.doctor_department(sys.modules[__name__], doctor_key), "status": "Confirmed",
        }
        conn.execute(f"INSERT INTO appointments ({', '.join(_COLUMNS)}) "
                     f"VALUES ({', '.join('?' for _ in _COLUMNS)})", [record[c] for c in _COLUMNS])
        conn.execute("COMMIT")
    except sqlite3.IntegrityError:
        conn.execute("ROLLBACK")
        return None
    finally:
        conn.close()
    print(f"--- System: booked {record['booking_id']} ({doctor_key}, {iso} {hhmm}) ---", flush=True)
    booking_sync.send("booked", record)          # Sheet row + email to the doctor
    return record


def normalize_booking_id(text):
    """'S U H 4 8 2 9', 'suh 4829', 'एस यू एच चार आठ दो नौ' -> 'SUH-4829'."""
    s = bf.to_devanagari(text or "")
    old = re.search(r"[A-Z]+-\d{8}-[0-9A-Z]{5}", s.upper())
    if old:
        return old.group(0)
    tokens = re.findall(r"[0-9]+|[a-z]+|[\u0900-\u097F]+", bf._norm(s))
    digits = "".join(t if t.isdigit() else bf._PHONE_DIGIT_WORDS.get(t, "") for t in tokens)
    return f"{BOOKING_ID_PREFIX}-{digits}" if len(digits) == 4 else None


def find_booking(booking_id, phone):
    """The booking with this ID *and* this mobile number, or None."""
    bid, digits = normalize_booking_id(booking_id), bf.phone_digits(phone)
    if not bid or not digits:
        return None
    for a in load_appointments():
        if a["booking_id"] == bid and a["phone_number"] == digits and a["date"] >= bf.today_ist().isoformat():
            return a
    return None


def cancel_booking(booking_id, phone):
    """'cancelled', 'already' (already cancelled) or 'not_found'."""
    record = find_booking(booking_id, phone)
    if not record:
        return "not_found", None
    if record["status"] != "Confirmed":
        return "already", record
    conn = _get_db()
    try:
        conn.execute("UPDATE appointments SET status = 'Cancelled' WHERE booking_id = ? AND date = ?",
                     (record["booking_id"], record["date"]))
    finally:
        conn.close()
    record = {**record, "status": "Cancelled"}
    print(f"--- System: cancelled {record['booking_id']} ---", flush=True)
    booking_sync.send("cancelled", record)
    return "cancelled", record


def record_callback(fields):
    """Ask reception to call the patient back (the booking could not be finished)."""
    booking_sync.send("callback", {
        "patient_name": fields.get("name", ""), "phone_number": fields.get("phone", ""),
        "consultant_name": fields.get("doctor", ""),
        "department": bf.doctor_department(sys.modules[__name__], fields["doctor"]) if fields.get("doctor") else "",
        "date": fields["date"].isoformat() if fields.get("date") else "",
        "time": fields["time"].strftime("%I:%M %p") if fields.get("time") else "",
        "purpose": fields.get("reason", ""),
    })
    print("--- System: call-back request recorded ---", flush=True)


def bookings_ready():
    """False until today's bookings have been reloaded from the Sheet."""
    return booking_sync.is_ready()

# ---------------------------------------------------------------------------
# 5. SCHEDULE LOOK-UPS FOR THE LANGUAGE MODEL
#    Every answer is written in the caller's language, with doctors, days,
#    dates and times already in their spoken form, so the model repeats them
#    instead of inventing its own wording.
# ---------------------------------------------------------------------------
_CORE = sys.modules[__name__]


def _resolve_day(day):
    d = bf.parse_date(day or "")
    return d


def get_doctors_on_day(day: str, department: str = "", language: str = "English") -> str:
    """Doctors sitting on one day, for one department (or the departments
    open that day when no department is given)."""
    d = _resolve_day(day)
    if not d:
        return "The day was not understood. Ask the caller for a day such as Monday or a date such as 2 October."
    weekday = bf.WEEKDAYS[d.weekday()]
    when = bf.say_date(d, language)
    if weekday == "SUNDAY" or weekday not in DOCTOR_SCHEDULE:
        return f"{when}: the OPD is closed on Sundays. Emergency services are open 24 hours."
    doctors = DOCTOR_SCHEDULE[weekday]
    if not (department or "").strip():
        depts = sorted({info["department"] for info in doctors.values()})
        names = ", ".join(bf.say_department(x, language) for x in depts)
        return (f"On {when} the OPD has these departments: {names}. "
                "Do not read this list out; ask the caller which department or doctor they need.")
    wanted = bf.find_departments(department) or [
        k for k in bf.DEPARTMENT_NAMES
        if bf._norm(department) in (k.lower(), bf.say_department(k, "English").lower())]
    if not wanted:
        return f"'{department}' is not a department in our OPD schedule."
    found = [(k, v) for k, v in doctors.items() if v["department"] in wanted]
    if not found:
        days = [w for w, docs in DOCTOR_SCHEDULE.items()
                if any(v["department"] in wanted for v in docs.values())]
        return (f"No {bf.say_department(wanted[0], language)} doctor sits on {when}. "
                f"That department runs on {bf.say_days(days, language)}.")
    parts = [f"{bf.say_doctor(k, language)} ({bf.say_department(v['department'], language)}), "
             f"{bf.say_window(bf._t(v['from']), bf._t(v['to']), language)}" for k, v in found]
    return f"On {when}: " + "; ".join(parts) + "."


def get_doctor_schedule(doctor: str, language: str = "English") -> str:
    """The days and hours one doctor sits, across the whole week."""
    keys = bf.find_doctors(doctor)
    if not keys:
        return f"No doctor named '{doctor}' is in the schedule. Ask the caller to repeat the name or give the department."
    if len(keys) > 1:
        return "More than one doctor matches: " + ", ".join(bf.say_doctor(k, language) for k in keys) + ". Ask which one."
    key = keys[0]
    days = bf.doctor_days(_CORE, key)
    window = bf.say_window(*next(iter(days.values())), language)
    return (f"{bf.say_doctor(key, language)} ({bf.say_department(bf.doctor_department(_CORE, key), language)}) "
            f"sits on {bf.say_days(days, language)}, {window}.")


def get_free_slots(doctor: str, day: str, language: str = "English") -> str:
    """Free 30-minute appointment times with one doctor on one day."""
    keys = bf.find_doctors(doctor)
    if len(keys) != 1:
        return get_doctor_schedule(doctor, language)
    key, d = keys[0], _resolve_day(day)
    if not d:
        return "The day was not understood. Ask the caller for a day such as Monday or a date such as 2 October."
    days = bf.doctor_days(_CORE, key)
    if bf.WEEKDAYS[d.weekday()] not in days:
        return (f"{bf.say_doctor(key, language)} does not sit on {bf.say_date(d, language)}. "
                + get_doctor_schedule(doctor, language))
    slots = bf.free_slots(_CORE, key, d)
    if not slots:
        return f"{bf.say_doctor(key, language)} has no free time on {bf.say_date(d, language)}."
    return (f"Free times with {bf.say_doctor(key, language)} on {bf.say_date(d, language)}: "
            f"{bf.say_slots(slots[:6], language)}"
            + (" and more." if len(slots) > 6 else "."))


def describe_booking(record, language):
    key = record["consultant_name"]
    d = date.fromisoformat(record["date"])
    t = datetime.strptime(record["time"], "%I:%M %p").time()
    status = {"Confirmed": "confirmed", "Cancelled": "cancelled"}.get(record["status"], record["status"])
    return (f"Booking {bf.say_booking_id(record['booking_id'])} is {status}: {record['patient_name']}, "
            f"with {bf.say_doctor(key, language)} on {bf.say_date(d, language)} at {bf.say_time(t, language)}.")


def get_my_appointment(booking_id: str, phone: str, language: str = "English") -> str:
    record = find_booking(booking_id, phone)
    if not record:
        return "No upcoming booking was found with that booking ID and mobile number. Ask the caller to check both."
    return describe_booking(record, language)

# ---------------------------------------------------------------------------
# 6. HOSPITAL FAQ KNOWLEDGE BASE
# ---------------------------------------------------------------------------
hospital_faqs = f"""
Based on the provided FAQ document for the hospital, here are the questions and answers arranged in English, Hindi, and Marathi:
1.	Hospital Location
o	English Q: Where is the Hospital located?
	A: {LOCATION_ANSWER['en']}
o	Hindi Q: हॉस्पिटल कहाँ स्थित है?
	A: {LOCATION_ANSWER['hi']}
o	Marathi Q: हॉस्पिटल कोठे आहे?
	A: {LOCATION_ANSWER['mr']}
2.	OPD Timings
o	English Q: What are the OPD timings?
	A: Our OPD services are available from 8:30 am to 5:00 pm.
o	Hindi Q: ओपीडी (OPD) का समय क्या है?
	A: हमारी ओपीडी सेवाएं सुबह 8:30 बजे से शाम 5:00 बजे तक उपलब्ध हैं।
o	Marathi Q: ओपीडी (OPD) ची वेळ काय आहे?
	A: आमची ओपीडी सेवा सकाळी ८:३० ते संध्याकाळी ५:०० वाजेपर्यंत सुरू असते.
3.	Government Health Schemes
o	English Q: Do you support Government health schemes?
	A: Yes, we support all major Government Schemes (like MPJAY/PMJAY) and have dedicated registration counters for them.
o	Hindi Q: क्या यहाँ आयुष्मान भारत योजना चलती है?
	A: जी हाँ, यहाँ PMJAY और सभी प्रमुख सरकारी योजनाएं मान्य हैं।
o	Marathi Q: सरकारी योजना लागू आहेत का?
	A: होय, येथे MPJAY आणि सर्व प्रमुख सरकारी योजना लागू आहेत; त्यासाठी स्वतंत्र खिडक्या उपलब्ध आहेत.
4.	Appointment Booking
o	English Q: How can I book an appointment?
	A: Paid patients can book appointments in advance telephonically at {APPOINTMENT_PHONE}.
o	Hindi Q: क्या एडवांस अपॉइंटमेंट ले सकते हैं?
	A: जी हाँ, आप {APPOINTMENT_PHONE} पर कॉल करके अपॉइंटमेंट बुक कर सकते हैं।
o	Marathi Q: अपॉइंटमेंट फोनवर बुक करता येते का?
	A: होय, सशुल्क रुग्ण {APPOINTMENT_PHONE} वर संपर्क करून आगाऊ वेळ घेऊ शकतात.
5.	Cashless Treatment
o	English Q: Do you offer cashless treatment?
	A: Yes, we have all major TPAs registered for cashless insurance processing.
o	Hindi Q: क्या कैशलेस इलाज की सुविधा है?
	A: जी हाँ, हमारे पास सभी प्रमुख टीपीए (TPA) पंजीकृत हैं।
o	Marathi Q: कॅशलेस सुविधा उपलब्ध आहे का?
	A: होय, आमच्याकडे सर्व प्रमुख टीपीए (TPA) नोंदणीकृत असून कॅशलेस उपचार मिळतात.
6.	Key Specialties
o	English Q: Which key specialties are available?
	A: We offer major specialties, including Cardiology, Oncology, and Neurology.
o	Hindi Q: क्या यहाँ हृदय रोग का इलाज होता है?
	A: जी हाँ, कार्डियोलॉजी, ऑन्कोलॉजी और न्यूरोलॉजी हमारे प्रमुख विभाग हैं।
7.	Pharmacy and Blood Bank
o	Marathi Q: औषधांचे दुकान २४ तास उघडे असते का?
	A: होय, आमच्या रुग्णालयात २४ तास फार्मसी आणि ब्लड बँक उपलब्ध आहे.
o	English Q: Is there a pharmacy on-site? / Do you have a blood bank?
	A: Yes, we have a 24/7 in-house pharmacy and a 24/7 Blood Centre available within the hospital premises.
8.	Visiting Hours
o	English Q: What are the IPD visiting hours?
	A: General visiting hours are 11:00 am to 1:00 pm and 4:00 pm to 6:00 pm.
o	Marathi Q: पेशंटला भेटण्याची वेळ काय आहे?
	A: भेटण्याची वेळ सकाळी ११ ते १ आणि संध्याकाळी ४ ते ६ आहे.
9.	Diabetes Clinic
o	English Q: Do you have a Diabetes Clinic?
	A: Yes, we have specialized clinics for Diabetes, Pain Management, and Women's Health.
o	Marathi Q: मधुमेहासाठी विशेष क्लिनिक आहे का?
	A: होय, आमच्याकडे तज्ज्ञ डॉक्टरांच्या मार्गदर्शनाखाली विशेष मधुमेह क्लिनिक चालवले जाते.
10.	Health Check-up
o	English Q: How do I book a Health Check-up?
	A: You can book various health packages by calling {APPOINTMENT_PHONE}. Please arrive fasting for 10-12 hours.
11.	Ambulance Services
o	English Q: Do you provide ambulance services?
	A: Yes, we provide 24/7 fully-equipped ambulance services.
o	Hindi Q: क्या अस्पताल की एम्बुलेंस सेवा उपलब्ध है?
	A: जी हाँ, हमारी एम्बुलेंस सेवा 24/7 उपलब्ध है।
o	Marathi Q: रुग्णालयाची रुग्णवाहिका (Ambulance) सेवा उपलब्ध आहे का?
	A: होय, आमची अद्ययावत रुग्णवाहिका सेवा २४ तास उपलब्ध आहे.
12.	Wheelchair Assistance
o	English Q: Are wheelchairs available at the entrance?
	A: Yes, wheelchairs and stretchers, along with assisting staff, are readily available at the main entrance and emergency drop-off.
o	Hindi Q: क्या प्रवेश द्वार पर व्हीलचेयर मिलेगी?
	A: जी हाँ, मुख्य द्वार और आपातकालीन प्रवेश पर व्हीलचेयर, स्ट्रेचर और वॉर्ड बॉय की सुविधा उपलब्ध है।
13.	Patient Attendant Policy
o	English Q: Can a family member stay overnight with the patient?
	A: Yes, one attendant is allowed to stay overnight with patients admitted in private or semi-private rooms. A valid attendant pass is required.
14.	Payment Modes
o	English Q: Do you accept UPI or credit cards?
	A: Yes, we accept Credit/Debit Cards, UPI (Google Pay, PhonePe, Paytm), and Net Banking at all our billing counters.
o	Hindi Q: क्या आप UPI या क्रेडिट कार्ड से पेमेंट लेते हैं?
	A: जी हाँ, हम क्रेडिट/डेबिट कार्ड, UPI और नेट बैंकिंग के माध्यम से भुगतान स्वीकार करते हैं।
o	Marathi Q: बिलासाठी UPI किंवा क्रेडिट कार्ड चालते का?
	A: होय, आमच्याकडे क्रेडिट/डेबिट कार्ड, UPI आणि नेट बँकिंग द्वारे पेमेंट स्वीकारले जाते.
15.	Types of Rooms
o	English Q: What types of wards or rooms are available for admission?
	A: We offer General Wards, Semi-Private Rooms, Private Rooms, and ICU/NICU based on patient needs.
16.	Insurance / TPA
o	English Q: Where can I get my documents attested for insurance?
	A: You can visit the TPA/Insurance Desk on the Ground Floor for document attestation and claim processing.
o	Hindi Q: बीमा के लिए मैं अपने दस्तावेजों को कहाँ प्रमाणित करवा सकता हूँ?
	A: दस्तावेजों के सत्यापन और क्लेम प्रोसेसिंग के लिए आप ग्राउंड फ्लोर पर स्थित टीपीए/बीमा डेस्क पर जा सकते हैं।
17.	Online Registration
o	English Q: Can I register as a new patient online?
	A: Currently, new patient registration is done at the reception counter. However, you can book an appointment via phone to save time.
18.	Maternity Packages
o	English Q: Do you offer maternity packages for delivery?
	A: Yes, we offer comprehensive maternity packages for both Normal and Cesarean deliveries. Please visit the billing desk for the package list.
19.	Neonatal ICU (NICU)
o	English Q: Is there a Neonatal ICU (NICU) available?
	A: Yes, we have a state-of-the-art NICU to provide specialized care for newborns and premature babies.
20.	Child Vaccinations
o	English Q: Are vaccinations for children available daily?
	A: Vaccinations are available during OPD hours. Please contact the Pediatrics department to confirm specific vaccine availability.
21.	Labor Room Policy
o	English Q: Can the father stay in the labor room?
	A: As per hospital policy, only female relatives are permitted in the labor room area to maintain privacy.
22.	Lactation Consultant
o	English Q: Do you have a lactation consultant?
	A: Yes, our nursing experts and pediatricians provide professional lactation counseling to new mothers.
23.	Visitor Parking
o	English Q: Is there a dedicated parking area for visitors?
	A: Yes, we have ample parking space for two-wheelers and four-wheelers within the hospital premises.
24.	Nearby Hotels
o	English Q: Are there any hotels nearby for outstation relatives?
	A: {HOSPITAL_SETTINGS['nearby_hotels_answer']}
25.	Bus Connectivity
o	English Q: Does the city bus service reach the hospital?
	A: {HOSPITAL_SETTINGS['bus_answer']}
26.	ATM Facility
o	English Q: Is there an ATM inside the hospital campus?
	A: Yes, there is an ATM facility available within the hospital campus.
27.	Distance from Railway Station
o	English Q: How far is the hospital from the railway station?
	A: {HOSPITAL_SETTINGS['railway_station_answer']}
28.	Walk-in Blood Tests
o	English Q: Can I get my blood tests done without an appointment?
	A: Yes, pathology lab services are available for walk-in patients during laboratory hours.
29.	MRI/CT Scan Availability
o	English Q: Are MRI and CT scan facilities available 24/7?
	A: Radiology services for emergencies are available 24/7. For routine scans, booking during day hours is preferred.
30.	Digital Reports
o	English Q: Can I receive my lab reports via WhatsApp or Email?
	A: Yes, we provide digital reports via email or through our patient portal. Please register your correct details at the counter.
31.	Biopsy Report Timeline
o	English Q: How long does it take to get a biopsy report?
	A: A standard biopsy report usually takes 5 to 7 working days, depending on the complexity of the test.
32.	Home Sample Collection
o	English Q: Do you provide home sample collection services?
	A: Yes, home collection services are available for nearby areas. Please call the lab helpdesk to schedule a visit.
33.	Physiotherapy Department
o	English Q: Do you have a physiotherapy department?
	A: Yes, we have a fully equipped physiotherapy and rehabilitation center for post-surgery and pain management.
34.	Dialysis Availability
o	English Q: Is dialysis available at the hospital?
	A: Yes, dialysis services are available. Please contact the Nephrology department for scheduling.
35.	Hospital open on Sundays
o	English Q: Is the hospital open on Sundays?
	A: The Emergency and Pharmacy are open 24/7. Regular OPDs are usually closed on Sundays.
36.	Kidney Stones / Urology
o	English Q: Do you have a specialized department for Kidney Stones?
	A: Yes, we offer advanced laser treatments for kidney stones and other urological issues.
37.	Cancer Support Group
o	English Q: Is there a support group for Cancer patients?
	A: Yes, we organize support group meetings and counseling sessions for oncology patients and their families.
38.	Foreign Currency Payment
o	English Q: Can I pay using a Foreign Currency?
	A: No, we accept payments only in Indian Rupees (INR). Currency exchange services are available in the city.
39.	Asthma and Allergy Clinic
o	English Q: Do you have a specialized clinic for Asthma and Allergy?
	A: Yes, our Pulmonology department handles specialized clinics for asthma, allergy, and lung disorders.
40.	Generic Medicine Counter
o	English Q: Is there a generic medicine counter in the hospital?
	A: Our pharmacy stocks a wide range of medicines, including quality generics. Please ask the pharmacist for options.
41.	Daycare Cashless Insurance
o	English Q: Can I get my insurance cashless approved for a Daycare procedure?
	A: Yes, many daycare procedures are covered under cashless insurance. Please check with the TPA desk.
42.	Long-distance Ambulance
o	English Q: Do you provide ambulance services for long-distance inter-city transfer?
	A: Yes, we provide long-distance ambulance transfers with medical supervision. Charges are based on distance.
43.	Smoke-free Campus
o	English Q: Is the hospital campus smoke-free?
	A: Yes, smoking and the use of tobacco products are strictly prohibited within the entire hospital campus.
44.	Speech Therapy
o	English Q: Do you have a Speech Therapist?
	A: Yes, speech therapy services are available, especially for post-stroke recovery and pediatric cases.
45.	Interim Bill
o	English Q: Can I get a summary of my daily expenses during my stay?
	A: Yes, you can request an Interim Bill from the billing counter to track your current expenses.
"""

# ---------------------------------------------------------------------------
# 7. SYSTEM PROMPT
#     Built fresh for every new call so today's date is always current.
#     The booking conversation itself is run by booking_flow in code; the
#     model answers questions and starts a booking with start_booking.
# ---------------------------------------------------------------------------
DEPARTMENT_LIST = ", ".join(sorted(bf.say_department(k, "English") for k in bf.DEPARTMENT_NAMES))


def build_system_prompt():
    today = bf.today_ist()
    return f"""
You are {RECEPTIONIST_NAME}, the receptionist at the {HOSPITAL_NAME}. You answer
callers' questions and help them book, check or cancel OPD appointments.
Today is {bf.say_date(today, "English")} {today.year}.

RULES:
1. Reply in the language named in the "Reply language" note that comes with
   each caller message (English, Hindi or Marathi) and only in that language.
   Hindi and Marathi replies are always written in Devanagari.
2. Keep every reply to at most two short sentences. Never use lists,
   numbering or bullet points. If there are many options, mention at most
   three and ask which one the caller wants.
3. Always say "Doctor" (English) or "डॉक्टर" (Hindi and Marathi) before a
   doctor's name, never "Dr." or "डॉ.". Use doctor names, days, dates and
   times exactly as the tools write them.
4. Doctors, their days, hours and free times come only from the tools
   get_doctors_on_day, get_doctor_schedule and get_free_slots, never from
   memory.
5. When the caller wants to book an appointment, call start_booking at once,
   passing any doctor, department, day or time they already mentioned. Do
   not ask for the name, mobile number or other details yourself; the
   booking steps ask for them.
6. To check or cancel a booking you need both the booking ID (for example
   {BOOKING_ID_FORMAT}) and the mobile number. Before cancelling, read the
   booking back and ask yes or no; call cancel_my_appointment only after the
   caller says yes.
7. Never give medical advice. If something is not covered by the FAQ or the
   tools, give our appointment desk number {APPOINTMENT_PHONE}.
8. The caller was already welcomed; never greet them again.
9. In Hindi and Marathi speak of a doctor respectfully: "डॉक्टर ... उपलब्ध
   हैं" (Hindi), "डॉक्टर ... उपलब्ध आहेत" (Marathi).

Departments in our OPD: {DEPARTMENT_LIST}.

{hospital_faqs}
"""

# ---------------------------------------------------------------------------
# 8. LANGUAGE AND SPEAKING STANDARDS
# ---------------------------------------------------------------------------
_MARATHI_WORDS = {"आहे", "आहेत", "कोण", "काय", "मला", "तुम्हाला", "आम्हाला", "कधी", "नाही", "हवे",
                  "हवी", "हवा", "पाहिजे", "करायची", "करायचे", "करायचा", "सांगा", "माझे", "माझा",
                  "माझी", "तुमचा", "तुमचे", "तुमची", "आणि", "किंवा", "होय", "आहात", "कुठे", "कसे"}
_MARATHI_PARTS = ("च्या", "ळ", "वारी", "ला ", "ऊ")
_HINDI_WORDS = {"है", "हैं", "नहीं", "मुझे", "क्या", "कौन", "कब", "को", "के", "की", "से", "में",
                "चाहिए", "बजे", "मेरा", "मेरी", "मेरे", "आप", "आपका", "हूँ", "हूं", "और", "या",
                "कहाँ", "कहां", "कैसे", "दीजिए", "बताइए", "करना", "करनी", "था", "थी", "गया"}
_ROMAN_HINDI_WORDS = {
    "hai", "hain", "hoon", "hun", "kya", "kaun", "kab", "kahan", "kaise", "kyun", "mujhe", "muje",
    "mera", "meri", "mere", "aap", "aapka", "aapko", "hum", "humein", "karna", "karni", "karo",
    "karein", "chahiye", "chahie", "ko", "ke", "ki", "se", "tak", "nahin", "haan", "dijiye",
    "batao", "bataiye", "milenge", "milega", "wale", "wala", "kitne",
}
_ROMAN_MARATHI_WORDS = {
    "aahe", "ahe", "aahet", "ahet", "aahes", "kon", "kay", "kasa", "kashi", "kadhi", "kuthe", "mala",
    "mla", "amhi", "tumhi", "tumhala", "pahije", "havi", "hava", "karaychi", "karaycha", "karayche",
    "sanga", "sangal", "dya", "ahat", "aahat", "cha", "chi", "che", "chya", "la", "madhe", "madhye",
    "hoil", "somvari", "mangalvari", "budhvari", "guruvari", "shukravari", "shanivari", "ravivari",
    "udya", "kiti", "yetil", "vajta", "vajata", "bheta", "bhetel", "bhetatil",
}
_ENGLISH_WORDS = {
    "the", "is", "are", "am", "was", "what", "which", "who", "when", "where", "how", "why", "can",
    "could", "would", "will", "do", "does", "i", "my", "me", "you", "your", "an", "of", "for",
    "to", "on", "in", "at", "there", "this", "that", "it", "please", "want", "need", "have",
    "has", "with", "from", "and", "or", "yes", "no", "thank", "thanks", "tell", "give",
}


def detect_language(text, previous="English"):
    """English, Hindi or Marathi, from the caller's words.
    Devanagari: Marathi when Marathi words outnumber Hindi ones, Hindi when
    the reverse, otherwise the call's language so far (a name like
    'गणेश शिंदे' says nothing about the language). English letters:
    romanised Hindi/Marathi needs two of its common words; English needs two
    everyday English words; anything else keeps the call's language."""
    text = bf.to_devanagari(text or "")
    if re.search(r"[ऀ-ॿ]", text):
        words = set(re.findall(r"[ऀ-ॿ]+", text))
        marathi = len(words & _MARATHI_WORDS) + sum(1 for p in _MARATHI_PARTS if p in text + " ")
        hindi = len(words & _HINDI_WORDS)
        if marathi > hindi:
            return "Marathi"
        if hindi > marathi:
            return "Hindi"
        return previous if previous in ("Hindi", "Marathi") else "Hindi"
    words = re.findall(r"[a-z]+", text.lower())
    hindi = sum(1 for w in words if w in _ROMAN_HINDI_WORDS)
    marathi = sum(1 for w in words if w in _ROMAN_MARATHI_WORDS)
    if max(hindi, marathi) >= 2:
        return "Marathi" if marathi >= hindi else "Hindi"
    if sum(1 for w in words if w in _ENGLISH_WORDS) >= 2:
        return "English"
    return previous


_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_CLOCK = re.compile(r"\b0?(\d{1,2}):(\d{2})\s?(AM|PM)\b")


def standardize_reply(text, language):
    """Make every spoken reply follow the same standards, whatever the model
    wrote: 'Doctor'/'डॉक्टर' in full, one spelling per doctor, no ISO dates,
    no lists, never Gujarati letters."""
    s = bf.to_devanagari(text or "").strip()
    s = s.replace("डोक्टर", "डॉक्टर").replace("डाक्टर", "डॉक्टर")
    s = s.replace("**", "").replace("__", "")
    lines = [re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", l).strip() for l in s.splitlines()]
    s = "; ".join(l.rstrip(";") for l in lines if l)
    for key, dev in bf.DOCTOR_NAMES_DEVANAGARI.items():
        latin = key.replace("DR. ", "")
        pattern = re.compile(r"(?:\b(?:dr|doctor)\.?\s+)?" + re.escape(latin), re.IGNORECASE)
        s = pattern.sub(bf.say_doctor(key, "English" if language == "English" else language), s)
        if language != "English":
            s = re.sub(r"(?:डॉ\.?|डा\.|डॉक्टर)\s*" + re.escape(dev), "डॉक्टर " + dev, s)
    s = re.sub(r"\b[Dd][Rr]\.?\s+(?=[A-Za-z])", "Doctor ", s)
    s = re.sub(r"डॉ\.\s*|डॉ\s+(?=[ऀ-ॿ])|डा\.\s*", "डॉक्टर ", s)
    s = re.sub(r"डॉक्टर\s+डॉक्टर", "डॉक्टर", s)
    # Any doctor the model named with its own spelling gets the one official
    # spelling ("डॉक्टर मीरा पिल्लई" -> "डॉक्टर मीरा पिल्लै").
    def _canonical(m):
        keys = bf.find_doctors(m.group(2))
        return bf.say_doctor(keys[0], language) if len(keys) == 1 else m.group(0)
    if language == "English":
        s = re.sub(r"\b(Doctor)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", _canonical, s)
    else:
        s = re.sub(r"(डॉक्टर)\s+([ऀ-ॿ]+(?:\s+[ऀ-ॿ]+)?)", _canonical, s)
    s = re.sub(r"\bDoctor\s+Doctor\b", "Doctor", s)
    s = _ISO_DATE.sub(lambda m: bf.say_date(date(int(m[1]), int(m[2]), int(m[3])), language), s)
    if language == "English":
        s = _CLOCK.sub(lambda m: bf.say_time(datetime.strptime(f"{m[1]}:{m[2]} {m[3]}", "%I:%M %p").time(), "English"), s)
    return re.sub(r"\s{2,}", " ", s).strip()


_ERROR_REPLY = {
    "English": "I'm sorry, I'm having a little trouble right now. Please try again in a moment.",
    "Hindi": "माफ़ कीजिए, अभी थोड़ी दिक्कत आ रही है। कृपया थोड़ी देर में फिर से कोशिश कीजिए।",
    "Marathi": "माफ करा, सध्या थोडी अडचण येत आहे. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
}

# ---------------------------------------------------------------------------
# 9. AGENT CLASS
# ---------------------------------------------------------------------------
_TOOLS = [
    {"type": "function", "function": {
        "name": "get_doctors_on_day",
        "description": "Doctors sitting on one day for one department, with their hours. Without a department it returns the departments open that day.",
        "parameters": {"type": "object", "properties": {
            "day": {"type": "string", "description": "The day as the caller said it: today, tomorrow, a weekday (Tuesday), next Friday, or a date such as 2 October."},
            "department": {"type": "string", "description": "Department in English, or the caller's own words for it (skin, teeth, kidney, bones...). Empty for all."},
        }, "required": ["day"]}}},
    {"type": "function", "function": {
        "name": "get_doctor_schedule",
        "description": "The days of the week and hours one doctor sits. Use for 'when / on which days is Doctor X available'.",
        "parameters": {"type": "object", "properties": {
            "doctor": {"type": "string", "description": "The doctor's name as the caller said it."},
        }, "required": ["doctor"]}}},
    {"type": "function", "function": {
        "name": "get_free_slots",
        "description": "Free 30-minute appointment times with one doctor on one day.",
        "parameters": {"type": "object", "properties": {
            "doctor": {"type": "string"},
            "day": {"type": "string", "description": "The day as the caller said it."},
        }, "required": ["doctor", "day"]}}},
    {"type": "function", "function": {
        "name": "start_booking",
        "description": "Start booking an appointment. Call as soon as the caller wants to book. Pass anything already mentioned; leave the rest empty.",
        "parameters": {"type": "object", "properties": {
            "doctor": {"type": "string"}, "department": {"type": "string"},
            "day": {"type": "string"}, "time": {"type": "string"},
        }, "required": []}}},
    {"type": "function", "function": {
        "name": "get_my_appointment",
        "description": "Look up one booking. Needs both the booking ID and the mobile number.",
        "parameters": {"type": "object", "properties": {
            "booking_id": {"type": "string"}, "phone": {"type": "string"},
        }, "required": ["booking_id", "phone"]}}},
    {"type": "function", "function": {
        "name": "cancel_my_appointment",
        "description": "Cancel one booking after the caller has said yes to cancelling it. Needs both the booking ID and the mobile number.",
        "parameters": {"type": "object", "properties": {
            "booking_id": {"type": "string"}, "phone": {"type": "string"},
        }, "required": ["booking_id", "phone"]}}},
]

_EXTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": ["answer", "question", "stop"]},
        "name": {"type": "string"}, "phone": {"type": "string"},
        "doctor": {"type": "string", "enum": [""] + list(bf.DOCTOR_NAMES_DEVANAGARI)},
        "date": {"type": "string"}, "time": {"type": "string"}, "reason": {"type": "string"},
    },
    "required": ["intent", "name", "phone", "doctor", "date", "time", "reason"],
}


class HospitalReceptionistAgent:
    _MAX_HISTORY = 50   # max non-system messages to keep; ~25 full call turns
    _MAX_TOOL_ROUNDS = 3

    def __init__(self, model="gpt-4o-mini"):
        if not OPENAI_API_KEY.strip():
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is not set. "
                "Set it before starting the server."
            )
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = model
        self.conversation_history = [{"role": "system", "content": build_system_prompt()}]
        self.language = "English"   # the call's language so far; see detect_language
        self.booking = None         # a BookingFlow while a booking is in progress

    def _trim_history(self):
        """Drop oldest non-system messages once the history exceeds _MAX_HISTORY.
        Starts the trimmed tail at a user-turn boundary to avoid splitting a
        tool-call chain mid-sequence."""
        rest = self.conversation_history[1:]
        if len(rest) <= self._MAX_HISTORY:
            return
        tail = rest[-self._MAX_HISTORY:]
        i = next((j for j, m in enumerate(tail) if isinstance(m, dict) and m.get("role") == "user"), 0)
        self.conversation_history = [self.conversation_history[0]] + tail[i:]

    # -- the model as a fallback to read one booking detail -------------------
    def _extract(self, text, expect, language):
        today = bf.today_ist()
        days = "; ".join(f"{bf.say_date(today + bf.timedelta(days=i), 'English')} = "
                         f"{(today + bf.timedelta(days=i)).isoformat()}" for i in range(0, 15))
        doctors = "; ".join(f"{k} = {bf.DOCTOR_NAMES_DEVANAGARI[k]}" for k in bf.DOCTOR_NAMES_DEVANAGARI)
        instructions = (
            "Extract appointment details from one thing a hospital caller said. "
            f"The receptionist had just asked for: {expect}. Today is {today.isoformat()}; "
            f"the next days are: {days}. Doctors (key = Devanagari name): {doctors}. "
            "Return empty strings for anything not said. date as YYYY-MM-DD, time as 24-hour HH:MM, "
            "phone as digits only, doctor as one of the keys. intent is 'question' if the caller asked "
            "something instead of answering, 'stop' if they do not want to book, else 'answer'.")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": instructions},
                          {"role": "user", "content": text}],
                response_format={"type": "json_schema", "json_schema": {
                    "name": "booking_details", "strict": True, "schema": _EXTRACT_SCHEMA}},
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            traceback.print_exc()
            sys.stderr.flush()
            return {}

    # -- tools ----------------------------------------------------------------
    def _run_tool(self, name, args, user_input, language):
        if name == "get_doctors_on_day":
            return get_doctors_on_day(args.get("day", ""), args.get("department", ""), language)
        if name == "get_doctor_schedule":
            return get_doctor_schedule(args.get("doctor", ""), language)
        if name == "get_free_slots":
            return get_free_slots(args.get("doctor", ""), args.get("day", ""), language)
        if name == "get_my_appointment":
            return get_my_appointment(args.get("booking_id", ""), args.get("phone", ""), language)
        if name == "cancel_my_appointment":
            if bf.classify_yes_no(user_input, ignore=("cancel", "कैंसल", "रद्द")) != "yes":
                return ("Not cancelled yet. Read the booking back to the caller and ask yes or no; "
                        "call cancel_my_appointment only after they say yes.")
            status, record = cancel_booking(args.get("booking_id", ""), args.get("phone", ""))
            if status == "not_found":
                return "No upcoming booking was found with that booking ID and mobile number."
            if status == "already":
                return "That booking was already cancelled."
            return "Cancelled. " + describe_booking(record, language)
        return f"Error: Tool '{name}' is not registered."

    def _start_booking(self, args, user_input, language):
        flow = bf.BookingFlow(_CORE, extractor=self._extract)
        hint = " ".join(v for v in (args.get("doctor"), args.get("department")) if v) or user_input
        keys = bf.find_doctors(hint)
        if len(keys) != 1:
            depts = bf.find_departments(hint)
            keys = bf.doctors_in_departments(_CORE, depts) if depts and not keys else keys
        if len(keys) == 1:
            flow.f["doctor"] = keys[0]
            day = bf.parse_date(args.get("day") or "") or bf.parse_date(user_input)
            if day:
                flow._set_date(day, language)
                if "date" in flow.f:
                    t = bf.parse_time(args.get("time") or "")
                    if t:
                        flow._set_time(t, language)
        elif len(keys) > 1:
            flow.options = keys
        self.booking = flow
        return flow.prompt(language)

    # -- one caller turn ------------------------------------------------------
    def process_user_input(self, user_input: str) -> str:
        # Remember where this turn starts so a failure can be rolled back.
        # Otherwise a half-finished tool call stays in the history and every
        # later OpenAI request for this caller is rejected.
        turn_start = len(self.conversation_history)
        text = bf.to_devanagari(user_input or "").strip()
        language = self.language = detect_language(text, self.language)
        try:
            if self.booking is not None:
                reply, status = self.booking.handle(text, language)
                if status == "question":
                    answer = self._chat(text, language)
                    reply = answer + " " + bf.TEXT["continue"][language].format(
                        prompt=self.booking.prompt(language))
                else:
                    self.conversation_history.append({"role": "user", "content": text})
                    self.conversation_history.append({"role": "assistant", "content": reply})
                if self.booking.done:
                    self.booking = None
            else:
                reply = self._chat(text, language)
            self._trim_history()
            return standardize_reply(reply, language)
        except Exception:
            # The technical error goes to the server log, never to the caller:
            # the phone reads replies aloud to patients.
            traceback.print_exc()
            sys.stderr.flush()
            del self.conversation_history[turn_start:]
            return _ERROR_REPLY[language]

    def _chat(self, text, language):
        """The model answers (FAQ, schedule questions) or starts a booking.
        It may look things up up to three times in one turn."""
        self.conversation_history.append({"role": "user", "content": text})
        # Stated fresh each turn and never stored, so the reply language
        # follows the caller.
        note = {"role": "system", "content": f"Reply language: {language}."}
        for round_no in range(self._MAX_TOOL_ROUNDS + 1):
            use_tools = round_no < self._MAX_TOOL_ROUNDS
            kwargs = {"tools": _TOOLS, "tool_choice": "auto"} if use_tools else {}
            response = self.client.chat.completions.create(
                model=self.model, messages=self.conversation_history + [note], **kwargs)
            message = response.choices[0].message
            if not getattr(message, "tool_calls", None):
                reply = message.content or ""
                self.conversation_history.append({"role": "assistant", "content": reply})
                return reply
            self.conversation_history.append(message)
            booking_reply = None
            for call in message.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                if call.function.name == "start_booking":
                    booking_reply = self._start_booking(args, text, language)
                    result = "Booking started. The booking steps will now ask the caller for the details."
                else:
                    result = self._run_tool(call.function.name, args, text, language)
                self.conversation_history.append({
                    "tool_call_id": call.id, "role": "tool",
                    "name": call.function.name, "content": result,
                })
            if booking_reply is not None:
                self.conversation_history.append({"role": "assistant", "content": booking_reply})
                return booking_reply
        return ""


# ---------------------------------------------------------------------------
# 10. NOTE ON USAGE
# ---------------------------------------------------------------------------
# The server (app.py) creates one HospitalReceptionistAgent per caller session
# and calls process_user_input() once per caller turn.
