import os
import json
import re
import requests
from openai import OpenAI
from bs4 import BeautifulSoup
from datetime import datetime, date
import uuid

# ---------------------------------------------------------------------------
# 1. API CONFIGURATION
# ---------------------------------------------------------------------------
# The key is read from the environment. Never write keys inside source code.
# On Windows Server (PowerShell):  $env:OPENAI_API_KEY = "sk-..."
# Or set it permanently in System Properties > Environment Variables.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# 2. MOCK PATIENT DATABASE
# ---------------------------------------------------------------------------
MOCK_PATIENT_DB = {
    "12345": {"name": "Naresh", "appointment": "March 15th at 10:00 AM", "doctor": "Dr. Ramesh"},
    "67890": {"name": "Harish", "appointment": "No upcoming appointments",  "doctor": "None"},
}

# ---------------------------------------------------------------------------
# 3. DOCTOR OPD SCHEDULES  — Monday through Saturday
#    Rules applied from source images:
#      - Doctors marked LEAVE are removed from that day entirely.
#      - "NOT RESPONDING TO CALL" treated as unavailable — removed.
#      - Entries with no published end-time use "" for "to".
# ---------------------------------------------------------------------------
DOCTOR_SCHEDULE = {
    "MONDAY": {
        "DR. RATANSING JUGNE":        {"department": "GENERAL MEDICINE",            "from": "08:30 AM", "to": "04:30 PM"},
        "DR. SARANG BARBIND":         {"department": "ENDOCRINOLOGY",               "from": "08:30 AM", "to": "04:30 PM"},
        "DR. TULSI S.":               {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. RUTUJA KALAMKAR":        {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. HIMCHUMI MEDHI":         {"department": "DENTAL",                      "from": "08:30 AM", "to": "06:00 PM"},
        "DR. SAHIL TRIMBAKE":         {"department": "OMFS",                        "from": "02:30 PM", "to": "04:30 PM"},
        "DR. AMOL KULKARNI":          {"department": "NEPHROLOGY",                  "from": "10:00 AM", "to": "06:00 PM"},
        "DR. ABHIJEET CHAVAN":        {"department": "NEPHROLOGY",                  "from": "08:30 AM", "to": "04:30 PM"},
        "DR. ANIKET SAOJI":           {"department": "MEDICAL GASTROENTROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. ASHISH CHAURASIA":       {"department": "UROLOGY",                     "from": "12:00 PM", "to": "02:00 PM"},
        "DR. KSHITIJ KIRANE":         {"department": "UROLOGY",                     "from": "11:00 AM", "to": "02:00 PM"},
        "DR. ALOK GADKARI":           {"department": "SPINE SURGERY",               "from": "09:00 AM", "to": "02:00 PM"},
        "DR. RAHUL KULKARNI":         {"department": "ONCOLOGY",                    "from": "03:00 PM", "to": "04:00 PM"},
        "DR. DHAIRYASHIL PATIL":      {"department": "ONCOSURGERY",                 "from": "10:00 AM", "to": "04:00 PM"},
        "DR. VIKAS KOTHAVADE":        {"department": "ONCO RADIATION",              "from": "03:00 PM", "to": ""},
        "DR. PRITI KUMAR":            {"department": "GYNAECOLOGY",                 "from": "10:00 AM", "to": "04:00 PM"},
        "DR. MEENAL PATVEKAR":        {"department": "GYNAECOLOGY",                 "from": "11:30 AM", "to": "04:30 PM"},
        "DR. SAMITIJAY KULKARNI":     {"department": "OPHTHALMOLOGY",               "from": "10:00 AM", "to": "04:00 PM"},
        "DR. SUJATA REGE":            {"department": "INFECTIOUS DISEASES",          "from": "01:00 PM", "to": "02:00 PM"},
        "DR. NEETA GOKHLE":           {"department": "DERMATOLOGY",                 "from": "09:00 AM", "to": "01:00 PM"},
        "DR. PRIYADARSHINI KULKARNI": {"department": "SUPPORTIVE & ASSISTED CARE",  "from": "11:00 AM", "to": "04:00 PM"},
        "DR. BRIG N RAMAKRISHNAN":    {"department": "ENT",                         "from": "10:00 AM", "to": "04:00 PM"},
        "DR. SARANG ROTE":            {"department": "NEUROSURGERY",                "from": "08:30 AM", "to": "12:00 PM"},
        "DR. SANJAY DEO":             {"department": "ORTHOPAEDIC",                 "from": "11:30 AM", "to": "02:00 PM"},
    },
    "TUESDAY": {
        "DR. RATANSING JUGNE":        {"department": "GENERAL MEDICINE",            "from": "08:30 AM", "to": "04:30 PM"},
        "DR. SARANG BARBIND":         {"department": "ENDOCRINOLOGY",               "from": "08:30 AM", "to": "04:30 PM"},
        "DR. TULSI S.":               {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. RUTUJA KALAMKAR":        {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. HIMCHUMI MEDHI":         {"department": "DENTAL",                      "from": "10:00 AM", "to": "06:00 PM"},
        "DR. DHANASHREE PAWAR":       {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. ABHIJEET CHAVAN":        {"department": "NEPHROLOGY",                  "from": "08:30 AM", "to": "04:30 PM"},
        "DR. AMOL KULKARNI":          {"department": "NEPHROLOGY",                  "from": "08:00 AM", "to": "04:30 PM"},
        "DR. ANIKET SAOJI":           {"department": "MEDICAL GASTROENTROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. SAVALI SULTANE":         {"department": "NEUROLOGY",                   "from": "11:00 AM", "to": "01:00 PM"},
        "DR. SARANG ROTE":            {"department": "NEURO SURGERY",               "from": "08:30 AM", "to": "12:00 PM"},
        "DR. ASHISH CHAURASIA":       {"department": "UROLOGY",                     "from": "09:30 AM", "to": "01:30 PM"},
        "DR. KSHITIJ KIRANE":         {"department": "UROLOGY",                     "from": "11:00 AM", "to": "02:00 PM"},
        "DR. KALPESH PATIL":          {"department": "PAEDIATRIC SURGERY",           "from": "10:00 AM", "to": "12:00 PM"},
        "DR. MEENAL PATVEKAR":        {"department": "GYNAECOLOGY",                 "from": "11:30 AM", "to": "04:30 PM"},
        "DR. PRANEET AWAKE":          {"department": "DERMATOLOGY",                 "from": "11:00 AM", "to": "02:00 PM"},
        "DR. ADITI SHENDE":           {"department": "DERMATOLOGY",                 "from": "09:00 AM", "to": "02:00 PM"},
        "DR. V. ANAND":               {"department": "ENT",                         "from": "09:00 AM", "to": "03:00 PM"},
        "DR. PRATIK BHOSALE":         {"department": "OPHTHALMOLOGY",               "from": "09:00 AM", "to": "02:00 PM"},
        "DR. ALOK GADKARI":           {"department": "SPINE SURGERY",               "from": "09:00 AM", "to": "12:00 PM"},
        "DR. PRIYADARSHINI KULKARNI": {"department": "SUPPORTIVE & ASSISTED CARE",  "from": "11:00 AM", "to": "04:00 PM"},
        "DR. DHAIRYASHIL PATIL":      {"department": "ONCOSURGERY",                 "from": "10:00 AM", "to": "04:00 PM"},
        "DR. SHEETAL PAWAR":          {"department": "PAIN MANAGEMENT",              "from": "02:00 PM", "to": "04:00 PM"},
        "DR. SANJAY DEO":             {"department": "ORTHOPAEDIC",                 "from": "11:30 AM", "to": "02:00 PM"},
    },
    "WEDNESDAY": {
        "DR. RATANSING JUGNE":        {"department": "GENERAL MEDICINE",            "from": "08:30 AM", "to": "04:30 PM"},
        "DR. SARANG BARBIND":         {"department": "ENDOCRINOLOGY",               "from": "08:30 AM", "to": "04:30 PM"},
        "DR. TULSI S.":               {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. HIMCHUMI MEDHI":         {"department": "DENTAL",                      "from": "08:30 AM", "to": "06:00 PM"},
        "DR. RUTUJA KALAMKAR":        {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. AMOL KULKARNI":          {"department": "NEPHROLOGY",                  "from": "10:00 AM", "to": "06:00 PM"},
        "DR. ABHIJEET CHAVAN":        {"department": "NEPHROLOGY",                  "from": "08:30 AM", "to": "04:30 PM"},
        "DR. ANIKET SAOJI":           {"department": "MEDICAL GASTROENTROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. RAIBA DESHMUKH":         {"department": "GENERAL SURGERY",             "from": "11:00 AM", "to": "01:00 PM"},
        "DR. MEENAL PATVEKAR":        {"department": "GYNAECOLOGY",                 "from": "11:30 AM", "to": "04:30 PM"},
        "DR. ALOK GADKARI":           {"department": "SPINE SPECIALIST",            "from": "09:00 AM", "to": "01:00 PM"},
        "DR. SARANG ROTE":            {"department": "NEUROSURGERY",                "from": "08:30 AM", "to": "12:00 PM"},
        "DR. PRAVEEN NAPHADE":        {"department": "NEUROLOGY",                   "from": "03:00 PM", "to": "04:30 PM"},
        "DR. DHAIRYASHIL PATIL":      {"department": "ONCOSURGERY",                 "from": "02:00 PM", "to": "04:00 PM"},
        "DR. RAHUL KULKARNI":         {"department": "ONCOLOGY",                    "from": "03:00 PM", "to": "04:00 PM"},
        "DR. PARUL GUPTA":            {"department": "RADIATION ONCOLOGY",          "from": "03:00 PM", "to": "05:00 PM"},
        "DR. ASHISH CHAURASIA":       {"department": "UROLOGY",                     "from": "09:00 AM", "to": "01:00 PM"},
        "DR. KSHITIJ KIRANE":         {"department": "UROLOGY",                     "from": "11:00 AM", "to": "02:00 PM"},
        "DR. ADITI SHENDE":           {"department": "DERMATOLOGY",                 "from": "09:00 AM", "to": "02:00 PM"},
        "DR. SANJAY DEO":             {"department": "ORTHOPAEDIC",                 "from": "11:30 AM", "to": "02:00 PM"},
        "DR. MONICA SHAH":            {"department": "OPHTHALMOLOGY",               "from": "10:00 AM", "to": "02:00 PM"},
        "DR. AJINKYA SANDBHOR":       {"department": "ENT",                         "from": "10:00 AM", "to": "02:00 PM"},
        "DR. V. ANAND":               {"department": "ENT",                         "from": "09:00 AM", "to": "03:00 PM"},
        "DR. SANDEEP NAPHADE":        {"department": "PLASTIC SURGERY",             "from": "03:00 PM", "to": "05:00 PM"},
        "DR. MILIND TELANG":          {"department": "INFERTILITY",                 "from": "02:00 PM", "to": "05:00 PM"},
        "DR. PRIYADARSHINI KULKARNI": {"department": "SUPPORTIVE & ASSISTED CARE",  "from": "11:00 AM", "to": "04:00 PM"},
        "DR. SANIKA KULKARNI":        {"department": "ONCOSURGERY",                 "from": "11:00 AM", "to": "02:00 PM"},
        "DR. ANUP TAMHNAKAR":         {"department": "ONCOSURGERY",                 "from": "11:00 AM", "to": "12:00 PM"},
        "DR. PAVAN HANCHANALE":       {"department": "LIVER CLINIC",                "from": "03:00 PM", "to": "05:00 PM"},
    },
    # THURSDAY — Source: image dated 02/04/2026
    # Removed: DR. BRIG. N. RAMAKRISHNAN (LEAVE), DR. SUJATA REGE (LEAVE)
    "THURSDAY": {
        "DR. RATANSING JUGNE":        {"department": "GENERAL MEDICINE",            "from": "08:30 AM", "to": "04:30 PM"},
        "DR. SARANG BARBIND":         {"department": "ENDOCRINOLOGY",               "from": "08:30 AM", "to": "04:30 PM"},
        "DR. TULSI S.":               {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. DHANASHREE PAWAR":       {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. HIMCHUMI MEDHI":         {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. ANIKET SAOJI":           {"department": "MEDICAL GASTROENTROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. KSHITIJ KIRANE":         {"department": "UROLOGY",                     "from": "11:00 AM", "to": "02:00 PM"},
        "DR. SAGAR BHALERAO":         {"department": "UROLOGY",                     "from": "01:00 PM", "to": ""},
        "DR. AMOL KULKARNI":          {"department": "NEPHROLOGY",                  "from": "09:00 AM", "to": "06:00 PM"},
        "DR. ABHIJEET CHAVAN":        {"department": "NEPHROLOGY",                  "from": "09:00 AM", "to": "04:30 PM"},
        "DR. MEENAL PATVEKAR":        {"department": "GYNAECOLOGY",                 "from": "11:30 AM", "to": ""},
        "DR. ALOK GADKARI":           {"department": "SPINE SPECIALIST",            "from": "09:00 AM", "to": "01:00 PM"},
        "DR. NEETA GHOKHALE":         {"department": "DERMATOLOGY",                 "from": "09:00 AM", "to": "02:00 PM"},
        "DR. V. ANAND":               {"department": "ENT",                         "from": "09:00 AM", "to": "03:00 PM"},
        "DR. SANJAY DEO":             {"department": "ORTHOPAEDIC",                 "from": "11:30 AM", "to": ""},
        "DR. PRIYADARSHINI KULKARNI": {"department": "SUPPORTIVE & ASSISTED CARE",  "from": "11:00 AM", "to": "04:00 PM"},
        "DR. SHEETAL PAWAR":          {"department": "PAIN MANAGEMENT",              "from": "02:00 PM", "to": "04:00 PM"},
        "DR. PRANJAL PANDIT":         {"department": "PLASTIC SURGERY",             "from": "10:00 AM", "to": "12:30 PM"},
        "DR. SARANG ROTE":            {"department": "NEUROSURGERY",                "from": "08:30 AM", "to": "12:00 PM"},
        "DR. AISHWARYA GADEWAR":      {"department": "OPHTHALMOLOGY",               "from": "09:00 AM", "to": "02:00 PM"},
        "DR. DHAIRYASHIL PATIL":      {"department": "ONCOSURGERY",                 "from": "10:00 AM", "to": "04:00 PM"},
    },
    # FRIDAY — Source: image dated 03/04/2026
    # Removed: DR. MEENAL PATVEKAR (LEAVE), DR. ALOK GADKARI (LEAVE),
    #          DR. MONICA SHAH (NOT RESPONDING TO CALL)
    "FRIDAY": {
        "DR. RATANSING JUGNE":        {"department": "GENERAL MEDICINE",            "from": "08:30 AM", "to": "04:30 PM"},
        "DR. SARANG BARBIND":         {"department": "ENDOCRINOLOGY",               "from": "08:30 AM", "to": "04:30 PM"},
        "DR. TULSI S.":               {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. HIMCHUMI MEDHI":         {"department": "DENTAL",                      "from": "10:00 AM", "to": "06:00 PM"},
        "DR. DHANASHREE PAWAR":       {"department": "DENTAL",                      "from": "08:30 AM", "to": "04:30 PM"},
        "DR. AMOL KULKARNI":          {"department": "NEPHROLOGY",                  "from": "10:00 AM", "to": "06:00 PM"},
        "DR. ABHIJEET CHAVAN":        {"department": "NEPHROLOGY",                  "from": "08:30 AM", "to": "04:00 PM"},
        "DR. ANIKET SAOJI":           {"department": "MEDICAL GASTROENTROLOGY",     "from": "08:30 AM", "to": "01:30 PM"},
        "DR. KALPESH PATIL":          {"department": "PAEDIATRIC SURGERY",           "from": "09:30 AM", "to": ""},
        "DR. SAVALI SULTANE":         {"department": "NEUROLOGY",                   "from": "02:30 PM", "to": ""},
        "DR. PRANEET AWAKE":          {"department": "DERMATOLOGY",                 "from": "09:00 AM", "to": "02:00 PM"},
        "DR. SANDEEP NAPHADE":        {"department": "PLASTIC SURGERY",             "from": "03:30 PM", "to": "04:30 PM"},
        "DR. ASHISH CHAURASIA":       {"department": "UROLOGY",                     "from": "09:30 AM", "to": "12:30 PM"},
        "DR. KSHITIJ KIRANE":         {"department": "UROLOGY",                     "from": "11:00 AM", "to": "02:00 PM"},
        "DR. PRIYADARSHINI KULKARNI": {"department": "SUPPORTIVE & ASSISTED CARE",  "from": "10:00 AM", "to": "04:00 PM"},
        "DR. V. ANAND":               {"department": "ENT",                         "from": "09:00 AM", "to": "03:00 PM"},
        "DR. SARANG ROTE":            {"department": "NEURO SURGERY",               "from": "08:30 AM", "to": "12:00 PM"},
        "DR. SANJAY DEO":             {"department": "ORTHOPAEDIC",                 "from": "11:30 AM", "to": ""},
        "DR. DHAIRYASHIL PATIL":      {"department": "ONCOSURGERY",                 "from": "09:00 AM", "to": "04:00 PM"},
        "DR. RAIBA DESHMUKH":         {"department": "GENERAL SURGERY",             "from": "11:00 AM", "to": "01:00 PM"},
    },
    # SATURDAY — Source: image dated 04/04/2026
    # Removed: DR. SARANG BARBIND (LEAVE), DR. TULSI S. (LEAVE),
    #          DR. KSHITIJ KIRANE (LEAVE), DR. AISHWARYA GADEWAR (LEAVE)
    "SATURDAY": {
        "DR. RATANSING JUGNE":        {"department": "GENERAL MEDICINE",            "from": "08:30 AM", "to": "04:30 PM"},
        "DR. HIMCHUMI MEDHI":         {"department": "DENTAL",                      "from": "10:00 AM", "to": "06:00 PM"},
        "DR. AMOL KULKARNI":          {"department": "NEPHROLOGY",                  "from": "08:30 AM", "to": "06:00 PM"},
        "DR. MEENAL PATVEKAR":        {"department": "GYNAECOLOGY",                 "from": "11:30 AM", "to": ""},
        "DR. ANIKET SAOJI":           {"department": "MEDICAL GASTROENTROLOGY",     "from": "08:30 AM", "to": "01:00 PM"},
        "DR. PRAVIN NAPHADE":         {"department": "NEUROLOGY",                   "from": "02:00 PM", "to": ""},
        "DR. SARANG ROTE":            {"department": "NEURO SURGERY",               "from": "09:00 AM", "to": "12:00 PM"},
        "DR. V. ANAND":               {"department": "ENT",                         "from": "12:00 PM", "to": "03:00 PM"},
        "DR. PRANEET AWAKE":          {"department": "DERMATOLOGY",                 "from": "09:00 AM", "to": "02:00 PM"},
        "DR. SANIKA KULKARNI":        {"department": "ONCOSURGERY",                 "from": "09:00 AM", "to": ""},
    },
}

# ---------------------------------------------------------------------------
# 4. APPOINTMENT STORAGE — SQLite database
#    Replaces the old appointments.json file. SQLite handles concurrent
#    requests from many phones safely on one server. The two function names
#    (load_appointments / save_appointments) are kept the same so that every
#    other part of this file works without change.
# ---------------------------------------------------------------------------
import sqlite3

DB_PATH = os.environ.get("HOSPITAL_DB_PATH",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "appointments.db"))

def _get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            booking_id      TEXT PRIMARY KEY,
            patient_name    TEXT NOT NULL,
            phone_number    TEXT NOT NULL,
            date            TEXT NOT NULL,
            time            TEXT NOT NULL,
            purpose         TEXT,
            consultant_name TEXT NOT NULL,
            department      TEXT,
            status          TEXT NOT NULL DEFAULT 'Confirmed',
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    return conn

_COLUMNS = ["booking_id", "patient_name", "phone_number", "date", "time",
            "purpose", "consultant_name", "department", "status"]

def load_appointments():
    conn = _get_db()
    try:
        rows = conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM appointments"
        ).fetchall()
        return [dict(zip(_COLUMNS, row)) for row in rows]
    finally:
        conn.close()

def save_appointments(appointments):
    """Insert any appointment that is not yet stored (matched by booking_id)."""
    conn = _get_db()
    try:
        for a in appointments:
            conn.execute(
                f"INSERT OR IGNORE INTO appointments ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
                [a.get(c, "") for c in _COLUMNS],
            )
        conn.commit()
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# 5. HELPER — FLEXIBLE TIME PARSER
#    Accepts spoken/natural time strings and returns a datetime.time object.
#    Returns None if no known format matches.
# ---------------------------------------------------------------------------
def parse_time_flexible(time_str):
    if not time_str or not isinstance(time_str, str):
        return None
    t = time_str.strip().upper()
    # Insert space before AM/PM if missing: "10:00AM" -> "10:00 AM"
    t = re.sub(r'(\d)(AM|PM)', r'\1 \2', t)
    for fmt in ["%I:%M %p", "%I %p", "%H:%M", "%I:%M", "%H:%M:%S"]:
        try:
            return datetime.strptime(t, fmt).time()
        except ValueError:
            continue
    return None

# ---------------------------------------------------------------------------
# 6. HELPER — DOCTOR AVAILABILITY AT A GIVEN TIME
# ---------------------------------------------------------------------------
def is_doctor_available_at_time(doctor_info, requested_time_obj):
    """
    Returns True if the doctor's OPD window covers the requested time.
    If the "to" field is empty, any time at or after "from" is accepted.
    """
    try:
        from_str = doctor_info.get("from", "")
        to_str   = doctor_info.get("to",   "")
        if not from_str:
            return False
        from_time = parse_time_flexible(from_str)
        if from_time is None:
            return False
        if not to_str:
            return requested_time_obj >= from_time
        to_time = parse_time_flexible(to_str)
        if to_time is None:
            return requested_time_obj >= from_time
        return from_time <= requested_time_obj <= to_time
    except Exception:
        return False

# ---------------------------------------------------------------------------
# 7. HELPER — FUZZY DOCTOR / DEPARTMENT MATCHER
#    Handles partial names, informal names ("Sarang sir", "Dr Barbind"),
#    and department-based queries ("the kidney doctor", "skin specialist").
#
#    Resolution sequence:
#      Step 1 — Filter schedule to the requested day only.
#      Step 2 — Strip honorifics; score each doctor by word-overlap.
#      Step 3 — From scored matches, keep only those available at the requested time.
#      Step 4 — If exactly 1 remains  → "found".
#               If 2+ remain          → "ambiguous" (agent reads options to patient).
#               If 0 remain           → try department keyword search on the same day/time.
#               If still 0            → "not_found".
# ---------------------------------------------------------------------------
HONORIFICS = {"DR", "DR.", "DOCTOR", "SIR", "MADAM", "MA'AM", "SAHEB", "JI", "S."}

def find_doctor_match(spoken_name, day_of_week, requested_time_obj=None):
    if day_of_week not in DOCTOR_SCHEDULE:
        return {
            "status":  "not_found",
            "matches": [],
            "message": (f"Our OPD is not scheduled on {day_of_week.capitalize()}. "
                        "OPDs run Monday through Saturday. Please choose another day."),
        }

    day_schedule = DOCTOR_SCHEDULE[day_of_week]

    # Tokenise and clean the spoken input
    raw_words    = spoken_name.upper().replace(".", " ").split()
    spoken_words = [w for w in raw_words if w not in HONORIFICS and w.strip()]

    if not spoken_words:
        return {
            "status":  "not_found",
            "matches": [],
            "message": "I could not understand the doctor's name. Could you please repeat it?",
        }

    # --- Score by name word-overlap ---
    scored = []
    for doc_key, doc_info in day_schedule.items():
        key_tokens = [t for t in doc_key.upper().replace(".", " ").split()
                      if t not in HONORIFICS and t.strip()]
        score = sum(1 for w in spoken_words if w in key_tokens)
        if score > 0:
            scored.append((score, doc_key, doc_info))

    # --- Filter by availability at the requested time ---
    if requested_time_obj and scored:
        time_filtered = [
            (s, k, i) for s, k, i in scored
            if is_doctor_available_at_time(i, requested_time_obj)
        ]
        if time_filtered:
            scored = time_filtered      # apply only when filter leaves results

    if scored:
        max_score = max(s for s, _, _ in scored)
        top = [(k, i) for s, k, i in scored if s == max_score]

        if len(top) == 1:
            return {"status": "found", "matches": top, "message": ""}

        # Multiple doctors match — return options to agent for disambiguation
        options = "; ".join(
            "{} ({}, {}{})" .format(
                k, i["department"], i["from"],
                f" to {i['to']}" if i["to"] else ""
            )
            for k, i in top
        )
        return {
            "status":  "ambiguous",
            "matches": top,
            "message": (
                f"I found more than one doctor with that name on "
                f"{day_of_week.capitalize()}: {options}. "
                "Could you please tell me the department or the full name?"
            ),
        }

    # --- No name match — try department keyword search ---
    dept_matches = []
    for doc_key, doc_info in day_schedule.items():
        dept_tokens = doc_info["department"].upper().split()
        if any(w in dept_tokens for w in spoken_words):
            if requested_time_obj:
                if is_doctor_available_at_time(doc_info, requested_time_obj):
                    dept_matches.append((doc_key, doc_info))
            else:
                dept_matches.append((doc_key, doc_info))

    if not dept_matches:
        return {
            "status":  "not_found",
            "matches": [],
            "message": (
                f"I could not find any doctor matching '{spoken_name}' on "
                f"{day_of_week.capitalize()} at the requested time. "
                "Please verify the name or department, or try a different day or time."
            ),
        }

    if len(dept_matches) == 1:
        return {"status": "found", "matches": dept_matches, "message": ""}

    options = "; ".join(
        "{} ({}, {}{})" .format(
            k, i["department"], i["from"],
            f" to {i['to']}" if i["to"] else ""
        )
        for k, i in dept_matches
    )
    return {
        "status":  "department_match",
        "matches": dept_matches,
        "message": (
            f"I found the following doctors in that department on "
            f"{day_of_week.capitalize()}: {options}. "
            "Which doctor would you like to consult?"
        ),
    }

# ---------------------------------------------------------------------------
# 8. TOOL FUNCTIONS
# ---------------------------------------------------------------------------

def check_appointment_status(patient_id: str) -> str:
    """
    Check appointments using a Patient ID or phone number.
    Searches both the mock database and the live appointments.json file.
    """
    print(f"--- System: Querying records for: {patient_id} ---")
    results = []

    # Mock database lookup
    record = MOCK_PATIENT_DB.get(patient_id)
    if record:
        results.append(
            f"Patient: {record['name']} | "
            f"Upcoming Appointment: {record['appointment']} | "
            f"Doctor: {record['doctor']}"
        )

    # Live appointments.json lookup by phone number or patient name
    for appt in load_appointments():
        if (appt.get("phone_number", "") == patient_id or
                patient_id.lower() in appt.get("patient_name", "").lower()):
            results.append(
                f"Booking ID: {appt['booking_id']} | "
                f"Doctor: {appt['consultant_name']} ({appt['department']}) | "
                f"Date: {appt['date']} | Time: {appt['time']} | "
                f"Status: {appt['status']}"
            )

    if results:
        return "\n".join(results)
    return (
        "No appointment records found for the provided ID. "
        "Please ask the patient to verify their patient ID or phone number."
    )


def book_appointment(patient_name: str, phone_number: str, date_str: str,
                     time_str: str, purpose: str, consultant_name: str) -> str:
    """
    Book an OPD appointment.
    - date_str       : YYYY-MM-DD  (the LLM normalises natural language dates)
    - time_str       : HH:MM AM/PM (the LLM normalises natural language times)
    - consultant_name: partial or informal name — resolved by find_doctor_match()
    Checks doctor availability, prevents double-booking, and saves the record.
    """
    print(f"--- System: Booking | {patient_name} | {consultant_name} | {date_str} {time_str} ---")

    # 1. Parse date
    try:
        appt_date = datetime.strptime(date_str.strip(), "%Y-%m-%d")
    except ValueError:
        return (
            "The date was not understood. Please provide the date in the format "
            "YYYY-MM-DD, for example 2026-04-15."
        )

    # 1b. Reject past dates
    if appt_date.date() < date.today():
        return (
            "Appointments cannot be made for past dates. "
            "Please choose today or a future date."
        )

    # 2. Parse time with flexible parser
    req_time = parse_time_flexible(time_str)
    if req_time is None:
        return (
            "The time was not understood. Please provide the time in the format "
            "HH:MM AM or HH:MM PM, for example 10:00 AM or 02:30 PM."
        )

    # Canonical storage strings
    canonical_time = datetime.combine(appt_date, req_time).strftime("%I:%M %p")
    canonical_date = appt_date.strftime("%Y-%m-%d")
    day_of_week    = appt_date.strftime("%A").upper()

    # 3. Check day
    if day_of_week == "SUNDAY":
        return (
            "Our OPDs are closed on Sundays. Emergency services are available "
            "24 hours. Please choose a date between Monday and Saturday."
        )
    if day_of_week not in DOCTOR_SCHEDULE:
        return (
            f"No OPD schedule is available for {day_of_week.capitalize()}. "
            "Please choose another day."
        )

    # 4. Resolve doctor using fuzzy matcher
    match = find_doctor_match(consultant_name, day_of_week, req_time)

    if match["status"] in ("not_found", "ambiguous", "department_match"):
        return match["message"]     # Returned to agent; agent speaks it to patient

    matched_key, doctor_info = match["matches"][0]

    # 4b. FIX: enforce the doctor's OPD time window explicitly.
    #     The matcher's time filter is advisory only — when no doctor fits
    #     the requested time it falls back to the name match, which allowed
    #     bookings outside OPD hours. This check closes that gap.
    if not is_doctor_available_at_time(doctor_info, req_time):
        window = doctor_info["from"] + (
            f" to {doctor_info['to']}" if doctor_info["to"] else " onwards"
        )
        return (
            f"{matched_key} is available on {day_of_week.capitalize()} "
            f"from {window}, so {canonical_time} is outside the OPD hours. "
            "Please choose a time within this window."
        )

    # 5. Conflict check — normalise both sides before comparing
    for appt in load_appointments():
        existing_time = parse_time_flexible(appt.get("time", ""))
        existing_canonical = (
            datetime.combine(appt_date, existing_time).strftime("%I:%M %p")
            if existing_time else appt.get("time", "")
        )
        if (appt["date"] == canonical_date
                and existing_canonical == canonical_time
                and appt["consultant_name"].upper() == matched_key.upper()):
            return (
                f"The {canonical_time} slot on {canonical_date} with {matched_key} "
                "is already booked. Please suggest an alternative time."
            )

    # 6. Generate booking ID and persist
    booking_id = f"SUH-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:5].upper()}"
    new_appointment = {
        "booking_id":      booking_id,
        "patient_name":    patient_name,
        "phone_number":    phone_number,
        "date":            canonical_date,
        "time":            canonical_time,
        "purpose":         purpose,
        "consultant_name": matched_key,
        "department":      doctor_info["department"],
        "status":          "Confirmed",
    }
    all_appointments = load_appointments()
    all_appointments.append(new_appointment)
    save_appointments(all_appointments)

    return (
        f"Appointment confirmed. Your booking ID is {booking_id}. "
        f"{matched_key} from {doctor_info['department']} will see you on "
        f"{appt_date.strftime('%A, %d %B %Y')} at {canonical_time} for {purpose}. "
        "Please save this booking ID for future reference."
    )


def get_appointment_by_booking_id(booking_id: str = "", phone_number: str = "") -> str:
    """
    Retrieve an existing appointment record by booking ID or registered phone number.
    """
    appointments = load_appointments()
    if not appointments:
        return "No appointments have been booked through this system yet."

    found = []
    if booking_id:
        found = [a for a in appointments
                 if a.get("booking_id", "").upper() == booking_id.strip().upper()]
    if not found and phone_number:
        found = [a for a in appointments
                 if a.get("phone_number", "").strip() == phone_number.strip()]

    if not found:
        return (
            "No appointment was found with the provided booking ID or phone number. "
            "Please verify the details and try again."
        )

    return "\n".join(
        f"Booking ID: {a['booking_id']} | "
        f"Patient: {a['patient_name']} | "
        f"Doctor: {a['consultant_name']} ({a['department']}) | "
        f"Date: {a['date']} | Time: {a['time']} | "
        f"Purpose: {a['purpose']} | Status: {a['status']}"
        for a in found
    )


def search_web(query: str) -> str:
    """Search the web for general information not covered by the FAQs."""
    print(f"--- System: Web search for '{query}' ---")
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(keywords=query, max_results=3)
        if results:
            return "\n\n".join(
                f"Title: {r['title']}\nSnippet: {r['body']}\nURL: {r['href']}"
                for r in results
            )
        return "No relevant search results found."
    except Exception as e:
        return f"Search failed: {e}"


def get_url_context(url: str) -> str:
    """Fetch and return readable paragraph text from a webpage."""
    print(f"--- System: Fetching {url} ---")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        text = "\n".join(p.get_text() for p in soup.find_all("p"))
        return text[:2000] + "..." if len(text) > 2000 else text
    except Exception as e:
        return f"Failed to fetch URL content: {e}"


def cancel_appointment(booking_id: str) -> str:
    """
    Cancel a confirmed appointment by booking ID.
    Sets the appointment status to 'Cancelled' in the database.
    Returns an error string if the booking ID is not found or already cancelled.
    """
    print(f"--- System: Cancelling booking {booking_id} ---")
    bid = booking_id.strip().upper()
    conn = _get_db()
    try:
        cursor = conn.execute(
            "UPDATE appointments SET status = 'Cancelled' "
            "WHERE booking_id = ? AND status = 'Confirmed'",
            (bid,),
        )
        conn.commit()
        if cursor.rowcount == 1:
            return (
                f"Appointment {bid} has been successfully cancelled. "
                "If you would like to rebook, please let me know."
            )
        row = conn.execute(
            "SELECT status FROM appointments WHERE booking_id = ?", (bid,)
        ).fetchone()
        if row:
            return (
                f"Booking {bid} is already {row[0]}. No changes were made."
            )
        return (
            "No confirmed appointment was found with that booking ID. "
            "Please verify the ID and try again."
        )
    finally:
        conn.close()


def list_available_slots(doctor_name: str, date_str: str) -> str:
    """
    Return a doctor's OPD window for a given date and highlight any
    already-confirmed bookings within that window.
    date_str must be in YYYY-MM-DD format.
    """
    print(f"--- System: Listing slots for '{doctor_name}' on {date_str} ---")
    try:
        appt_date = datetime.strptime(date_str.strip(), "%Y-%m-%d")
    except ValueError:
        return (
            "The date was not understood. Please provide it in YYYY-MM-DD format, "
            "for example 2026-06-20."
        )

    day_of_week = appt_date.strftime("%A").upper()

    if day_of_week == "SUNDAY":
        return "Our OPDs are closed on Sundays. Please choose a weekday or Saturday."
    if day_of_week not in DOCTOR_SCHEDULE:
        return f"No OPD is scheduled on {day_of_week.capitalize()}."

    match = find_doctor_match(doctor_name, day_of_week)
    if match["status"] == "not_found":
        return match["message"]
    if match["status"] in ("ambiguous", "department_match"):
        return match["message"]

    matched_key, doctor_info = match["matches"][0]
    window = doctor_info["from"] + (
        f" to {doctor_info['to']}" if doctor_info["to"] else " onwards"
    )
    date_label = appt_date.strftime("%A, %d %B %Y")

    booked_times = sorted(
        appt["time"]
        for appt in load_appointments()
        if appt["date"] == appt_date.strftime("%Y-%m-%d")
        and appt["consultant_name"].upper() == matched_key.upper()
        and appt["status"] == "Confirmed"
    )

    if booked_times:
        return (
            f"{matched_key} ({doctor_info['department']}) is available on "
            f"{date_label} from {window}. "
            f"Already booked times on that day: {', '.join(booked_times)}. "
            "Any other time within the window can be booked."
        )
    return (
        f"{matched_key} ({doctor_info['department']}) is available on "
        f"{date_label} from {window}. "
        "No appointments have been booked yet — any time in that window is free."
    )

# ---------------------------------------------------------------------------
# 9. HOSPITAL FAQ KNOWLEDGE BASE
# ---------------------------------------------------------------------------
hospital_faqs = """
Based on the provided FAQ document for Symbiosis University Hospital, here are the questions and answers arranged in English, Hindi, and Marathi:
1.	Hospital Location
o	English Q: Where is Symbiosis Hospital located?
	A: Welcome to Symbiosis Hospital. We are located in Lavale, Pune, accessible via the Pashan - Sus Road.
o	Hindi Q: सिम्बायोसिस हॉस्पिटल कहाँ स्थित है?
	A: सिम्बायोसिस हॉस्पिटल में आपका स्वागत है। हम लवले, पुणे में स्थित हैं, यहाँ पाषाण-सूस रोड के माध्यम से पहुँचा जा सकता है।
o	Marathi Q: सिम्बायोसिस हॉस्पिटल कोठे आहे?
	A: सिम्बायोसिस हॉस्पिटलमध्ये आपले स्वागत आहे. आमचे रुग्णालय लवळे, पुणे येथे असून पाषाण-सूस रोडने येथे पोहोचता येते.
2.	OPD Timings
o	English Q: What are the OPD timings?
	A: Welcome to Symbiosis Hospital. Our OPD services are available from 8:30 am to 5:00 pm.
o	Hindi Q: ओपीडी (OPD) का समय क्या है?
	A: सिम्बायोसिस हॉस्पिटल में आपका स्वागत है। हमारी ओपीडी सेवाएं सुबह 8:30 बजे से शाम 5:00 बजे तक उपलब्ध हैं।
o	Marathi Q: ओपीडी (OPD) ची वेळ काय आहे?
	A: सिम्बायोसिस हॉस्पिटलमध्ये आपले स्वागत आहे. आमची ओपीडी सेवा सकाळी ८:३० ते संध्याकाळी ५:०० वाजेपर्यंत सुरू असते.
3.	Government Health Schemes
o	English Q: Do you support Government health schemes?
	A: Welcome to Symbiosis Hospital. Yes, we support all major Government Schemes (like MPJAY/PMJAY) and have dedicated registration counters for them.
o	Hindi Q: क्या यहाँ आयुष्मान भारत योजना चलती है?
	A: सिम्बायोसिस हॉस्पिटल में आपका स्वागत है। जी हाँ, यहाँ PMJAY और सभी प्रमुख सरकारी योजनाएं मान्य हैं।
o	Marathi Q: सरकारी योजना लागू आहेत का?
	A: सिम्बायोसिस हॉस्पिटलमध्ये आपले स्वागत आहे. होय, येथे MPJAY आणि सर्व प्रमुख सरकारी योजना लागू आहेत; त्यासाठी स्वतंत्र खिडक्या उपलब्ध आहेत.
4.	Appointment Booking
o	English Q: How can I book an appointment?
	A: Welcome to Symbiosis Hospital. Paid patients can book appointments in advance telephonically at +91 9226470807.
o	Hindi Q: क्या एडवांस अपॉइंटमेंट ले सकते हैं?
	A: सिम्बायोसिस हॉस्पिटल में आपका स्वागत है। जी हाँ, आप +91 9226470807 पर कॉल करके अपॉइंटमेंट बुक कर सकते हैं।
o	Marathi Q: अपॉइंटमेंट फोनवर बुक करता येते का?
	A: सिम्बायोसिस हॉस्पिटलमध्ये आपले स्वागत आहे. होय, सशुल्क रुग्ण +91 9226470807 वर संपर्क करून आगाऊ वेळ घेऊ शकतात.
5.	Cashless Treatment
o	English Q: Do you offer cashless treatment?
	A: Welcome to Symbiosis Hospital. Yes, we have all major TPAs registered for cashless insurance processing.
o	Hindi Q: क्या कैशलेस इलाज की सुविधा है?
	A: सिम्बायोसिस हॉस्पिटल में आपका स्वागत है। जी हाँ, हमारे पास सभी प्रमुख टीपीए (TPA) पंजीकृत हैं।
o	Marathi Q: कॅशलेस सुविधा उपलब्ध आहे का?
	A: सिम्बायोसिस हॉस्पिटलमध्ये आपले स्वागत आहे. होय, आमच्याकडे सर्व प्रमुख टीपीए (TPA) नोंदणीकृत असून कॅशलेस उपचार मिळतात.
6.	Key Specialties
o	English Q: Which key specialties are available?
	A: Welcome to Symbiosis Hospital. We offer major specialties, including Cardiology, Oncology, and Neurology.
o	Hindi Q: क्या यहाँ हृदय रोग का इलाज होता है?
	A: सिम्बायोसिस हॉस्पिटल में आपका स्वागत है। जी हाँ, कार्डियोलॉजी, ऑन्कोलॉजी और न्यूरोलॉजी हमारे प्रमुख विभाग हैं।
7.	Pharmacy and Blood Bank
o	Marathi Q: औषधांचे दुकान २४ तास उघडे असते का?
	A: सिम्बायोसिस हॉस्पिटलमध्ये आपले स्वागत आहे. होय, आमच्या रुग्णालयात २४ तास फार्मसी आणि ब्लड बँक उपलब्ध आहे.
o	English Q: Is there a pharmacy on-site? / Do you have a blood bank?
	A: Yes, we have a 24/7 in-house pharmacy and a 24/7 Blood Centre available within the hospital premises.
8.	Visiting Hours
o	English Q: What are the IPD visiting hours?
	A: Welcome to Symbiosis Hospital. General visiting hours are 11:00 am to 1:00 pm and 4:00 pm to 6:00 pm.
o	Marathi Q: पेशंटला भेटण्याची वेळ काय आहे?
	A: सिम्बायोसिस हॉस्पिटलमध्ये आपले स्वागत आहे. भेटण्याची वेळ सकाळी ११ ते १ आणि संध्याकाळी ४ ते ६ आहे.
9.	Diabetes Clinic
o	English Q: Do you have a Diabetes Clinic?
	A: Welcome to Symbiosis Hospital. Yes, we have specialized clinics for Diabetes, Pain Management, and Women's Health.
o	Marathi Q: मधुमेहासाठी विशेष क्लिनिक आहे का?
	A: सिम्बायोसिस हॉस्पिटलमध्ये आपले स्वागत आहे. होय, आमच्याकडे तज्ज्ञ डॉक्टरांच्या मार्गदर्शनाखाली विशेष मधुमेह क्लिनिक चालवले जाते.
10.	Health Check-up
o	English Q: How do I book a Health Check-up?
	A: Welcome to Symbiosis Hospital. You can book various health packages by calling +91 9226470807. Please arrive fasting for 10-12 hours.
11.	Ambulance Services
o	English Q: Do you provide ambulance services?
	A: Welcome to Symbiosis Hospital. Yes, we provide 24/7 fully-equipped ambulance services.
o	Hindi Q: क्या अस्पताल की एम्बुलेंस सेवा उपलब्ध है?
	A: सिम्बायोसिस हॉस्पिटल में आपका स्वागत है। जी हाँ, हमारी एम्बुलेंस सेवा 24/7 उपलब्ध है।
o	Marathi Q: रुग्णालयाची रुग्णवाहिका (Ambulance) सेवा उपलब्ध आहे का?
	A: सिम्बायोसिस हॉस्पिटलमध्ये आपले स्वागत आहे. होय, आमची अद्ययावत रुग्णवाहिका सेवा २४ तास उपलब्ध आहे.
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
	A: Yes, there are several hotels and guest houses in the Lavale and Sus area. Our helpdesk can provide a list.
25.	Bus Connectivity (PMPML)
o	English Q: Does the PMPML bus service reach the hospital?
	A: Yes, PMPML buses ply regularly to the Symbiosis Lavale campus from various parts of Pune.
26.	ATM Facility
o	English Q: Is there an ATM inside the hospital campus?
	A: Yes, there is an ATM facility available within the Symbiosis campus.
27.	Distance from Railway Station
o	English Q: How far is the hospital from Pune Railway Station?
	A: The hospital is approximately 18-20 km from Pune Railway Station. It usually takes 45-60 minutes by taxi.
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
# 10. SYSTEM PROMPT
#     Today's date is injected at startup so the model can resolve relative
#     date expressions like "tomorrow" or "next Monday" accurately.
# ---------------------------------------------------------------------------
_today_str = date.today().strftime("%A, %d %B %Y")   # e.g., "Tuesday, 07 April 2026"

system_prompt = f"""
You are Anjali, a professional and empathetic hospital receptionist at
Symbiosis University Hospital and Research Center, Pune.
Your role is to assist patients with booking appointments, checking existing
appointments, and answering general hospital queries.

Today's date is {_today_str}.
Use this to resolve relative date expressions such as "tomorrow", "next Monday",
or "this Friday" before passing any date to a tool.

COMMUNICATION RULES:
1. Speak in short, complete sentences. Maximum two sentences per response.
2. Use courteous transitions: "Certainly", "Of course", "Thank you for that",
   "I understand", "Please allow me a moment."
3. No bullet points, numbered lists, or text formatting in spoken responses.
4. Be calm and empathetic. Never rush the patient.
5. Do not provide medical advice or diagnosis under any circumstance.
6. Respond in the same language the patient uses — English, Hindi, or Marathi.

DATE AND TIME INTERPRETATION — MANDATORY:
- Convert any natural date expression ("tomorrow", "next Monday", "15th April",
  "April 15", "this coming Saturday") to YYYY-MM-DD format before using it.
- Convert any natural time expression to HH:MM AM/PM format before using it.
  Examples:
    "10 in the morning"  →  10:00 AM
    "2 in the afternoon" →  02:00 PM
    "half past 3"        →  03:30 PM
    "around 11"          →  11:00 AM
    "evening"            →  Use 04:00 PM as default and confirm with patient.
  Morning means AM. Afternoon and evening mean PM.

APPOINTMENT BOOKING — MANDATORY STEP-BY-STEP SEQUENCE:
Collect one piece of information at a time in this exact order.
Do not combine questions. Wait for the patient's response at each step.

  Step 1 — Ask for the patient's full name.
  Step 2 — Ask for the patient's phone number.
  Step 3 — Ask for the preferred date. Convert to YYYY-MM-DD internally.
  Step 4 — Ask for the preferred time. Convert to HH:MM AM/PM internally.
  Step 5 — Ask for the purpose or reason for the visit.
  Step 6 — Ask for the doctor's name or department.

Before calling book_appointment, read back all six details clearly to the patient
and ask for a yes or no confirmation. Call the tool only after receiving explicit
confirmation.

DOCTOR IDENTIFICATION:
The book_appointment tool resolves partial and informal doctor names automatically.
Pass exactly what the patient says for the doctor's name or department.
If the tool returns a list of matching doctors, read the options clearly to the
patient and ask them to choose. Then re-submit with the clarified name.

APPOINTMENT RETRIEVAL:
If a patient provides a booking ID (format: SUH-YYYYMMDD-XXXXX) or their registered
phone number, use the get_appointment_by_booking_id tool to retrieve the record.
If a patient provides their patient ID or phone number to check an appointment,
use the check_appointment_status tool.

APPOINTMENT CANCELLATION:
If a patient asks to cancel an appointment, ask for the booking ID
(format: SUH-YYYYMMDD-XXXXX). Read back the booking ID and ask for a yes or no
confirmation before calling cancel_appointment. Do not cancel without confirmation.

SLOT AVAILABILITY:
If a patient asks when a doctor is free, available, or what times can be booked,
use list_available_slots with the doctor's name and the requested date in
YYYY-MM-DD format. Resolve any relative date expression first.

{hospital_faqs}

Current OPD schedules for your reference:
{json.dumps(DOCTOR_SCHEDULE, indent=2)}
"""

# ---------------------------------------------------------------------------
# 11. AGENT CLASS
# ---------------------------------------------------------------------------
class HospitalReceptionistAgent:
    _MAX_HISTORY = 50   # max non-system messages to keep; ~25 full call turns

    def __init__(self, model="gpt-4o-mini"):
        if not OPENAI_API_KEY.strip():
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is not set. "
                "Set it before starting the server."
            )
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model  = model
        self.conversation_history = [{"role": "system", "content": system_prompt}]
        self.tools  = [
            {
                "type": "function",
                "function": {
                    "name": "check_appointment_status",
                    "description": (
                        "Check a patient's upcoming appointments using their Patient ID "
                        "or phone number. Searches both the hospital database and live "
                        "booking records."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "patient_id": {
                                "type": "string",
                                "description": "The patient's ID number or registered phone number.",
                            }
                        },
                        "required": ["patient_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "book_appointment",
                    "description": (
                        "Book an OPD appointment for a patient. "
                        "The consultant_name field accepts partial or informal names "
                        "and department names — the system resolves them automatically. "
                        "All six fields are required."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "patient_name": {
                                "type": "string",
                                "description": "Full name of the patient.",
                            },
                            "phone_number": {
                                "type": "string",
                                "description": "Patient's contact phone number.",
                            },
                            "date_str": {
                                "type": "string",
                                "description": "Appointment date in YYYY-MM-DD format.",
                            },
                            "time_str": {
                                "type": "string",
                                "description": "Appointment time in HH:MM AM/PM format, e.g. 10:00 AM.",
                            },
                            "purpose": {
                                "type": "string",
                                "description": "Reason or purpose of the patient's visit.",
                            },
                            "consultant_name": {
                                "type": "string",
                                "description": (
                                    "Doctor's name as spoken by the patient. "
                                    "Partial names, last names only, and department "
                                    "names are all accepted."
                                ),
                            },
                        },
                        "required": [
                            "patient_name", "phone_number", "date_str",
                            "time_str", "purpose", "consultant_name",
                        ],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_appointment_by_booking_id",
                    "description": (
                        "Retrieve an existing appointment record using a booking ID "
                        "(format: SUH-YYYYMMDD-XXXXX) or the patient's registered "
                        "phone number."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_id": {
                                "type": "string",
                                "description": "The booking ID issued at the time of confirmation.",
                            },
                            "phone_number": {
                                "type": "string",
                                "description": "The patient's registered phone number as an alternative.",
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the internet for general information not covered by the FAQs.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query string.",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_url_context",
                    "description": "Read and return the text content of a specific webpage URL.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The full URL of the webpage to fetch.",
                            }
                        },
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_appointment",
                    "description": (
                        "Cancel a confirmed appointment using its booking ID. "
                        "Only call this after the patient has confirmed they want to cancel."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_id": {
                                "type": "string",
                                "description": "The booking ID to cancel (format: SUH-YYYYMMDD-XXXXX).",
                            }
                        },
                        "required": ["booking_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_available_slots",
                    "description": (
                        "Show a doctor's OPD time window for a given date and list "
                        "any already-booked times so the patient can choose a free slot."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "doctor_name": {
                                "type": "string",
                                "description": "Doctor's name or department as spoken by the patient.",
                            },
                            "date_str": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format.",
                            },
                        },
                        "required": ["doctor_name", "date_str"],
                    },
                },
            },
        ]

    def _trim_history(self):
        """Drop oldest non-system messages once the history exceeds _MAX_HISTORY.
        Starts the trimmed tail at a user-turn boundary to avoid splitting a
        tool-call chain mid-sequence."""
        rest = self.conversation_history[1:]
        if len(rest) <= self._MAX_HISTORY:
            return
        tail = rest[-self._MAX_HISTORY:]
        # Advance to the first user message so we never start mid-tool-chain
        i = next((j for j, m in enumerate(tail) if m.get("role") == "user"), 0)
        self.conversation_history = [self.conversation_history[0]] + tail[i:]

    def process_user_input(self, user_input: str) -> str:
        self.conversation_history.append({"role": "user", "content": user_input})
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation_history,
                tools=self.tools,
                tool_choice="auto",
            )
            response_message = response.choices[0].message

            if response_message.tool_calls:
                self.conversation_history.append(response_message)

                for tool_call in response_message.tool_calls:
                    fn_name = tool_call.function.name
                    fn_args = json.loads(tool_call.function.arguments)

                    if fn_name == "check_appointment_status":
                        fn_result = check_appointment_status(
                            patient_id=fn_args.get("patient_id")
                        )
                    elif fn_name == "book_appointment":
                        fn_result = book_appointment(
                            patient_name=fn_args.get("patient_name"),
                            phone_number=fn_args.get("phone_number"),
                            date_str=fn_args.get("date_str"),
                            time_str=fn_args.get("time_str"),
                            purpose=fn_args.get("purpose"),
                            consultant_name=fn_args.get("consultant_name"),
                        )
                    elif fn_name == "get_appointment_by_booking_id":
                        fn_result = get_appointment_by_booking_id(
                            booking_id=fn_args.get("booking_id", ""),
                            phone_number=fn_args.get("phone_number", ""),
                        )
                    elif fn_name == "search_web":
                        fn_result = search_web(query=fn_args.get("query"))
                    elif fn_name == "get_url_context":
                        fn_result = get_url_context(url=fn_args.get("url"))
                    elif fn_name == "cancel_appointment":
                        fn_result = cancel_appointment(
                            booking_id=fn_args.get("booking_id", ""),
                        )
                    elif fn_name == "list_available_slots":
                        fn_result = list_available_slots(
                            doctor_name=fn_args.get("doctor_name", ""),
                            date_str=fn_args.get("date_str", ""),
                        )
                    else:
                        fn_result = f"Error: Tool '{fn_name}' is not registered."

                    self.conversation_history.append({
                        "tool_call_id": tool_call.id,
                        "role":         "tool",
                        "name":         fn_name,
                        "content":      fn_result,
                    })

                second_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.conversation_history,
                )
                final_answer = second_response.choices[0].message.content
                self.conversation_history.append(
                    {"role": "assistant", "content": final_answer}
                )
                self._trim_history()
                return final_answer

            else:
                final_answer = response_message.content
                self.conversation_history.append(
                    {"role": "assistant", "content": final_answer}
                )
                self._trim_history()
                return final_answer

        except Exception as e:
            return (
                "I'm sorry, I'm having a little trouble connecting right now. "
                f"Error: {e}"
            )


# ---------------------------------------------------------------------------
# 12. NOTE ON USAGE
#     The old desktop files imported a single global `root_agent`.
#     The server (app.py) now creates one HospitalReceptionistAgent per
#     caller session, so each phone call keeps its own conversation history.
#     ADKBridge is kept only for backward compatibility with the old
#     desktop voice_caller.py, and is created on demand, not at import.
# ---------------------------------------------------------------------------
class ADKBridge:
    def __init__(self):
        self.agent = HospitalReceptionistAgent()

    def __call__(self, user_input: str) -> str:
        return self.agent.process_user_input(user_input)
