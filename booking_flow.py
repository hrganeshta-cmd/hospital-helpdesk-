"""
Appointment booking as fixed steps in code.

The language model no longer runs the booking conversation. This module asks
for each detail in a fixed order (name -> mobile -> doctor -> date -> time ->
reason), checks every answer in code, reads the details back from what it
stored, and books only after a clear "yes". The model is used only as a
fallback to pull a detail out of a free-form sentence (see `extractor`).

Everything the caller hears is written here from templates, one standard
wording per language (English, Hindi, Marathi):
  - doctors are always "Doctor <name>" / "डॉक्टर <नाम>", never "Dr." or "डॉ.";
  - times, dates, mobile numbers and booking IDs are spoken the same way
    every time.

Nothing here imports agent_core at module level; the functions that need the
schedule or the database receive it as `core`.
"""

import difflib
import re
from datetime import date, datetime, time, timedelta, timezone

# ---------------------------------------------------------------------------
# Time zone: the hospital is in India; the server may run on UTC.
# ---------------------------------------------------------------------------
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST)


def today_ist():
    return now_ist().date()


LANGUAGES = ("English", "Hindi", "Marathi")

# ---------------------------------------------------------------------------
# Doctors and departments as they are spoken
# ---------------------------------------------------------------------------
# One fixed Devanagari spelling per doctor (Hindi and Marathi use the same),
# so the name is never spelled differently from call to call.
DOCTOR_NAMES_DEVANAGARI = {
    "DR. ARVIND MEHTA": "अरविंद मेहता",
    "DR. KAVITA RAO": "कविता राव",
    "DR. NIKHIL JOSHI": "निखिल जोशी",
    "DR. SNEHA IYER": "स्नेहा अय्यर",
    "DR. ROHAN BHATT": "रोहन भट्ट",
    "DR. POOJA NAIR": "पूजा नायर",
    "DR. FARHAN QURESHI": "फरहान कुरेशी",
    "DR. VIKRAM DESAI": "विक्रम देसाई",
    "DR. MEERA PILLAI": "मीरा पिल्लै",
    "DR. HARISH MENON": "हरीश मेनन",
    "DR. ADITYA KAPOOR": "आदित्य कपूर",
    "DR. SIDDHARTH RANE": "सिद्धार्थ राणे",
    "DR. MANISH AGARWAL": "मनीष अग्रवाल",
    "DR. LAKSHMI SUNDARAM": "लक्ष्मी सुंदरम",
    "DR. KARAN MALHOTRA": "करण मल्होत्रा",
    "DR. NANDINI GHOSH": "नंदिनी घोष",
    "DR. TANVI SAXENA": "तन्वी सक्सेना",
    "DR. DEEPA REDDY": "दीपा रेड्डी",
    "DR. RITU CHAWLA": "ऋतु चावला",
    "DR. IMRAN SHAIKH": "इमरान शेख",
    "DR. SHALINI BOSE": "शालिनी बोस",
    "DR. GAURAV SINHA": "गौरव सिन्हा",
    "DR. NEHA KAPADIA": "नेहा कपाडिया",
    "DR. ANKIT TIWARI": "अंकित तिवारी",
    "DR. RADHIKA IYENGAR": "राधिका अय्यंगार",
    "DR. PRAKASH HEGDE": "प्रकाश हेगडे",
    "DR. YAMINI GHATGE": "यामिनी घाटगे",
    "DR. VARUN KHANNA": "वरुण खन्ना",
    "DR. ISHITA BANERJEE": "इशिता बनर्जी",
    "DR. MOHAN CHANDRA": "मोहन चंद्रा",
    "DR. TEJAS PANDE": "तेजस पांडे",
    "DR. AJAY THAKUR": "अजय ठाकुर",
    "DR. REKHA JAIN": "रेखा जैन",
    "DR. SURESH NAIDU": "सुरेश नायडू",
    "DR. KUNAL ARORA": "कुणाल अरोरा",
    "DR. SUNITA MATHUR": "सुनीता माथुर",
    "DR. ABHAY DUTTA": "अभय दत्ता",
}

# Department names as spoken: (English, Hindi, Marathi)
DEPARTMENT_NAMES = {
    "DENTAL": ("Dental", "दंत चिकित्सा", "दंतचिकित्सा"),
    "DERMATOLOGY": ("Dermatology", "त्वचा रोग", "त्वचारोग"),
    "ENT": ("ENT", "कान-नाक-गला", "कान-नाक-घसा"),
    "ENDOCRINOLOGY": ("Endocrinology", "एंडोक्राइनोलॉजी", "एंडोक्राइनोलॉजी"),
    "GENERAL MEDICINE": ("General Medicine", "जनरल मेडिसिन", "जनरल मेडिसिन"),
    "GENERAL SURGERY": ("General Surgery", "जनरल सर्जरी", "जनरल सर्जरी"),
    "GYNAECOLOGY": ("Gynaecology", "स्त्री रोग", "स्त्रीरोग"),
    "INFECTIOUS DISEASES": ("Infectious Diseases", "संक्रामक रोग", "संसर्गजन्य आजार"),
    "INFERTILITY": ("Infertility", "निःसंतानता उपचार", "वंध्यत्व उपचार"),
    "LIVER CLINIC": ("Liver Clinic", "लिवर क्लिनिक", "यकृत क्लिनिक"),
    "MEDICAL GASTROENTEROLOGY": ("Gastroenterology", "पेट रोग", "पोटाचे विकार"),
    "MEDICAL ONCOLOGY": ("Medical Oncology", "कैंसर उपचार", "कर्करोग उपचार"),
    "NEPHROLOGY": ("Nephrology", "किडनी रोग", "मूत्रपिंड विकार"),
    "NEUROLOGY": ("Neurology", "न्यूरोलॉजी", "न्यूरोलॉजी"),
    "NEUROSURGERY": ("Neurosurgery", "न्यूरो सर्जरी", "न्यूरो सर्जरी"),
    "OPHTHALMOLOGY": ("Ophthalmology", "नेत्र रोग", "नेत्ररोग"),
    "ORAL & MAXILLOFACIAL SURGERY": ("Oral and Maxillofacial Surgery", "मुख और जबड़ा सर्जरी", "मुख व जबडा शस्त्रक्रिया"),
    "ORTHOPAEDICS": ("Orthopaedics", "हड्डी रोग", "अस्थिरोग"),
    "PAEDIATRIC SURGERY": ("Paediatric Surgery", "बाल सर्जरी", "बाल शस्त्रक्रिया"),
    "PAIN MANAGEMENT": ("Pain Management", "दर्द उपचार", "वेदना उपचार"),
    "PLASTIC SURGERY": ("Plastic Surgery", "प्लास्टिक सर्जरी", "प्लास्टिक सर्जरी"),
    "RADIATION ONCOLOGY": ("Radiation Oncology", "रेडिएशन ऑन्कोलॉजी", "रेडिएशन ऑन्कोलॉजी"),
    "SPINE SURGERY": ("Spine Surgery", "रीढ़ की सर्जरी", "मणक्याची शस्त्रक्रिया"),
    "SUPPORTIVE & ASSISTED CARE": ("Supportive and Assisted Care", "सहायक देखभाल", "सहाय्यक देखभाल"),
    "SURGICAL ONCOLOGY": ("Surgical Oncology", "कैंसर सर्जरी", "कर्करोग शस्त्रक्रिया"),
    "UROLOGY": ("Urology", "मूत्र रोग", "मूत्ररोग"),
}

# Everyday words for a department, in English, romanised Hindi/Marathi and
# Devanagari. More specific phrases are listed first ("kidney stone" before
# "kidney"). Devanagari entries match inside longer words.
_DEPARTMENT_WORDS = [
    (("kidney stone", "stone", "pathri", "पथरी", "मुतखडा"), ("UROLOGY",)),
    (("neurosurg", "न्यूरो सर्जरी", "न्यूरोसर्जरी", "मेंदूची शस्त्रक्रिया"), ("NEUROSURGERY",)),
    (("plastic", "प्लास्टिक"), ("PLASTIC SURGERY",)),
    (("spine", "back pain", "पीठ", "कमर", "मणक", "स्पाइन"), ("SPINE SURGERY",)),
    (("skin", "twacha", "त्वचा", "चमड़ी", "dermat"), ("DERMATOLOGY",)),
    (("teeth", "tooth", "dental", "dentist", "dant", "daat", "dat", "दांत", "दाँत", "दंत", "दात"), ("DENTAL",)),
    (("kidney", "किडनी", "गुर्द", "मूत्रपिंड", "nephro", "dialysis"), ("NEPHROLOGY",)),
    (("urine", "prostate", "urolog", "मूत्र", "पेशाब", "लघवी"), ("UROLOGY",)),
    (("eye", "eyes", "aankh", "ankh", "आंख", "आँख", "डोळ", "नेत्र", "ophthal"), ("OPHTHALMOLOGY",)),
    (("bone", "bones", "joint", "joints", "knee", "fracture", "haddi", "हड्डी", "हाड", "अस्थि", "घुटन", "गुडघ", "ortho"), ("ORTHOPAEDICS",)),
    (("ear", "nose", "throat", "ent", "कान", "नाक", "गला", "घसा"), ("ENT",)),
    (("stomach", "digestion", "gastro", "acidity", "पेट", "पोट"), ("MEDICAL GASTROENTEROLOGY",)),
    (("pregnan", "women", "gynae", "gyne", "delivery", "स्त्री", "प्रसूति", "प्रसूती", "गर्भ", "महिला"), ("GYNAECOLOGY",)),
    (("infertil", "ivf", "बांझ", "निःसंतान", "वंध्य"), ("INFERTILITY",)),
    (("brain", "nerve", "migraine", "stroke", "मेंदू", "दिमाग", "neurolog"), ("NEUROLOGY",)),
    (("cancer", "oncolog", "tumour", "tumor", "कैंसर", "कर्करोग", "कॅन्सर"), ("MEDICAL ONCOLOGY", "SURGICAL ONCOLOGY", "RADIATION ONCOLOGY")),
    (("sugar", "diabet", "thyroid", "endocrin", "मधुमेह", "शुगर", "डायबिटीज", "थायरॉइड"), ("ENDOCRINOLOGY",)),
    (("liver", "लिवर", "यकृत"), ("LIVER CLINIC",)),
    (("pain management", "chronic pain", "दर्द उपचार", "वेदना"), ("PAIN MANAGEMENT",)),
    (("child surgery", "paediatric", "pediatric", "बच्चों की सर्जरी"), ("PAEDIATRIC SURGERY",)),
    (("infection", "infectious", "संक्रम", "संसर्ग"), ("INFECTIOUS DISEASES",)),
    (("jaw", "maxillo", "जबड"), ("ORAL & MAXILLOFACIAL SURGERY",)),
    (("supportive", "assisted care", "palliative", "सहायक", "सहाय्यक"), ("SUPPORTIVE & ASSISTED CARE",)),
    (("general surgery", "surgeon", "सर्जरी", "शस्त्रक्रिया"), ("GENERAL SURGERY",)),
    (("fever", "physician", "general medicine", "general", "बुखार", "ताप", "सामान्य", "फिजिशियन"), ("GENERAL MEDICINE",)),
]

WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
_WEEKDAY_SPOKEN = {
    "English": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "Hindi": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
    "Marathi": ["सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
}
_MONTH_SPOKEN = {
    "English": ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"],
    "Hindi": ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई",
              "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    "Marathi": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै",
                "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"],
}
_DIGIT_WORDS_SPOKEN = {
    "English": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"],
    "Hindi": ["शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ"],
    "Marathi": ["शून्य", "एक", "दोन", "तीन", "चार", "पाच", "सहा", "सात", "आठ", "नऊ"],
}
_AND = {"English": "and", "Hindi": "और", "Marathi": "आणि"}
_DEVANAGARI_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")
_LATIN_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


# ---------------------------------------------------------------------------
# Script clean-up
# ---------------------------------------------------------------------------
def to_devanagari(text):
    """Gujarati script -> Devanagari. The two Unicode blocks have the same
    layout (0x180 apart), so this is a letter-for-letter conversion. Speech
    recognisers sometimes write Hindi or Marathi in Gujarati letters; after
    this, Gujarati never reaches the rest of the system."""
    return "".join(chr(ord(ch) - 0x180) if 0x0A80 <= ord(ch) <= 0x0AFF else ch
                   for ch in text or "")


def _norm(text):
    """Lower-case, Gujarati->Devanagari, Devanagari digits->Latin digits."""
    return to_devanagari(text or "").translate(_LATIN_DIGITS).lower()


def _join(items, language):
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {_AND[language]} " + items[-1]


# ---------------------------------------------------------------------------
# Speaking standards (one wording per language)
# ---------------------------------------------------------------------------
def say_doctor(key, language):
    """'DR. NEHA KAPADIA' -> 'Doctor Neha Kapadia' / 'डॉक्टर नेहा कपाडिया'."""
    if language == "English":
        return "Doctor " + key.replace("DR. ", "").title()
    return "डॉक्टर " + DOCTOR_NAMES_DEVANAGARI.get(key, key.replace("DR. ", "").title())


def say_department(dept_key, language):
    names = DEPARTMENT_NAMES.get(dept_key)
    if not names:
        return dept_key.title()
    return names[LANGUAGES.index(language)]


def _hm(t):
    return (t.hour, t.minute)


def say_time(t, language):
    """time(13, 30) -> '1:30 PM' / 'दोपहर 1:30 बजे' / 'दुपारी १:३० वाजता'."""
    hour12 = t.hour % 12 or 12
    clock = f"{hour12}:{t.minute:02d}" if t.minute else f"{hour12}"
    if language == "English":
        return f"{clock} {'AM' if t.hour < 12 else 'PM'}"
    if language == "Hindi":
        part = "सुबह" if t.hour < 12 else "दोपहर" if t.hour < 16 else "शाम"
        return f"{part} {clock} बजे"
    part = "सकाळी" if t.hour < 12 else "दुपारी" if t.hour < 17 else "संध्याकाळी"
    return f"{part} {clock.translate(_DEVANAGARI_DIGITS)} वाजता"


def say_window(t_from, t_to, language):
    """The span a doctor sits, e.g. '11 AM to 4 PM'."""
    if language == "English":
        return f"{say_time(t_from, language)} to {say_time(t_to, language)}"
    if language == "Hindi":
        return f"{say_time(t_from, language)} से {say_time(t_to, language)} तक"
    start = say_time(t_from, language).replace(" वाजता", "")
    end = say_time(t_to, language).replace(" वाजता", "")
    return f"{start} ते {end}"


def say_date(d, language):
    """date(2026, 10, 2) -> 'Friday, 2 October' / 'शुक्रवार, 2 अक्टूबर' /
    'शुक्रवार, २ ऑक्टोबर'. The year is said only when it is not this year."""
    weekday = _WEEKDAY_SPOKEN[language][d.weekday()]
    month = _MONTH_SPOKEN[language][d.month - 1]
    day = str(d.day)
    if language == "Marathi":
        day = day.translate(_DEVANAGARI_DIGITS)
    text = f"{weekday}, {day} {month}"
    if d.year != today_ist().year:
        year = str(d.year)
        text += " " + (year.translate(_DEVANAGARI_DIGITS) if language == "Marathi" else year)
    return text


def say_days(weekday_keys, language):
    """['MONDAY'..'FRIDAY'] -> 'Monday to Friday'; otherwise a list."""
    idx = sorted(WEEKDAYS.index(w) for w in weekday_keys)
    names = _WEEKDAY_SPOKEN[language]
    if len(idx) >= 3 and idx == list(range(idx[0], idx[-1] + 1)):
        joiner = {"English": " to ", "Hindi": " से ", "Marathi": " ते "}[language]
        return names[idx[0]] + joiner + names[idx[-1]]
    return _join([names[i] for i in idx], language)


def say_phone(digits, language):
    """'9226470807' -> 'nine two two six four, seven zero eight zero seven'
    (two groups of five, digit words in the caller's language)."""
    words = _DIGIT_WORDS_SPOKEN[language]
    groups = [digits[:5], digits[5:]]
    return ", ".join(" ".join(words[int(ch)] for ch in g) for g in groups if g)


def say_booking_id(booking_id):
    """'SUH-4829' -> 'S U H 4 8 2 9'. The phone app recognises this form and
    shows the ID as SUH-4829 on screen."""
    prefix, _, number = booking_id.partition("-")
    return " ".join(prefix) + " " + " ".join(number)


def say_slots(times, language):
    return _join([say_time(t, language) for t in times], language)


# ---------------------------------------------------------------------------
# Understanding the caller (code first; the model only as a fallback)
# ---------------------------------------------------------------------------
_PHONE_DIGIT_WORDS = {
    # English and English-in-Devanagari
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "to": "2", "too": "2",
    "three": "3", "four": "4", "for": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9",
    "ज़ीरो": "0", "जीरो": "0", "झिरो": "0", "झीरो": "0", "जिरो": "0", "वन": "1", "टू": "2", "टु": "2",
    "थ्री": "3", "फोर": "4", "फ़ोर": "4", "फाइव": "5", "फाईव": "5", "फाइव्ह": "5",
    "सिक्स": "6", "सेवन": "7", "सेव्हन": "7", "एट": "8", "एइट": "8", "एईट": "8",
    "नाइन": "9", "नाईन": "9",
    # Hindi
    "शून्य": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4", "पांच": "5", "पाँच": "5",
    "छह": "6", "छः": "6", "छे": "6", "छ": "6", "सात": "7", "आठ": "8", "नौ": "9",
    "shunya": "0", "ek": "1", "do": "2", "teen": "3", "char": "4", "chaar": "4",
    "panch": "5", "paanch": "5", "chhe": "6", "chheh": "6", "chah": "6", "saat": "7",
    "aath": "8", "nau": "9",
    # Marathi
    "दोन": "2", "पाच": "5", "सहा": "6", "नऊ": "9", "don": "2", "pach": "5", "saha": "6", "nahu": "9",
}
_REPEAT_WORDS = {"double": 2, "triple": 3, "डबल": 2, "ट्रिपल": 3, "dabal": 2}


def phone_digits(text):
    """The mobile number in a spoken answer, as 10 digits, or None.
    Understands digits, digit words in English/Hindi/Marathi (in Latin or
    Devanagari letters) and 'double'/'triple'. +91 and a leading 0 are removed."""
    tokens = re.findall(r"[0-9]+|[a-z]+|[ऀ-ॿ]+", _norm(text))
    digits, repeat = [], 1
    for tok in tokens:
        if tok.isdigit():
            digits.append(tok * repeat if len(tok) == 1 else tok)
            repeat = 1
        elif tok in _REPEAT_WORDS:
            repeat = _REPEAT_WORDS[tok]
        elif tok in _PHONE_DIGIT_WORDS:
            digits.append(_PHONE_DIGIT_WORDS[tok] * repeat)
            repeat = 1
    number = "".join(digits)
    if len(number) == 12 and number.startswith("91"):
        number = number[2:]
    elif len(number) == 11 and number.startswith("0"):
        number = number[1:]
    return number if re.fullmatch(r"[6-9]\d{9}", number) else None


def phone_digit_count(text):
    """How many digits were heard (for the 'I heard N digits' message)."""
    tokens = re.findall(r"[0-9]+|[a-z]+|[ऀ-ॿ]+", _norm(text))
    count, repeat = 0, 1
    for tok in tokens:
        if tok.isdigit():
            count += len(tok) * (repeat if len(tok) == 1 else 1); repeat = 1
        elif tok in _REPEAT_WORDS:
            repeat = _REPEAT_WORDS[tok]
        elif tok in _PHONE_DIGIT_WORDS:
            count += repeat; repeat = 1
    return count


_NUMBER_WORDS = {}
for _i, _w in enumerate(
        "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen twenty".split(), start=1):
    _NUMBER_WORDS[_w] = _i
for _i, _w in enumerate(
        "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth "
        "fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split(), start=1):
    _NUMBER_WORDS[_w] = _i
_NUMBER_WORDS.update({"thirty": 30, "thirtieth": 30})
_HINDI_1_31 = ("एक दो तीन चार पांच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह "
               "उन्नीस बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस").split()
_MARATHI_1_31 = ("एक दोन तीन चार पाच सहा सात आठ नऊ दहा अकरा बारा तेरा चौदा पंधरा सोळा सतरा अठरा "
                 "एकोणीस वीस एकवीस बावीस तेवीस चोवीस पंचवीस सव्वीस सत्तावीस अठ्ठावीस एकोणतीस तीस एकतीस").split()
for _i, _w in enumerate(_HINDI_1_31, start=1):
    _NUMBER_WORDS.setdefault(_w, _i)
for _i, _w in enumerate(_MARATHI_1_31, start=1):
    _NUMBER_WORDS.setdefault(_w, _i)
_NUMBER_WORDS.update({"पाँच": 5, "छः": 6, "ek": 1, "do": 2, "don": 2, "teen": 3, "char": 4, "chaar": 4,
                      "panch": 5, "paanch": 5, "pach": 5, "chhe": 6, "saha": 6, "saat": 7, "aath": 8,
                      "nau": 9, "das": 10, "daha": 10, "gyarah": 11, "gyara": 11, "akra": 11,
                      "barah": 12, "bara": 12, "ekvees": 21})

_MONTH_WORDS = {}
for _i, _names in enumerate([
        ("january", "jan", "जनवरी", "जानेवारी"), ("february", "feb", "फरवरी", "फ़रवरी", "फेब्रुवारी"),
        ("march", "mar", "मार्च"), ("april", "apr", "अप्रैल", "एप्रिल"), ("may", "मई", "मे"),
        ("june", "jun", "जून"), ("july", "jul", "जुलाई", "जुलै"), ("august", "aug", "अगस्त", "ऑगस्ट"),
        ("september", "sep", "sept", "सितंबर", "सितम्बर", "सप्टेंबर"),
        ("october", "oct", "अक्टूबर", "अक्तूबर", "ऑक्टोबर", "ओक्टोबर"),
        ("november", "nov", "नवंबर", "नवम्बर", "नोव्हेंबर"),
        ("december", "dec", "दिसंबर", "दिसम्बर", "डिसेंबर")], start=1):
    for _n in _names:
        _MONTH_WORDS[_n] = _i

_WEEKDAY_WORDS = {
    0: ("monday", "somvar", "सोमवार"), 1: ("tuesday", "mangalvar", "मंगलवार", "मंगळवार"),
    2: ("wednesday", "budhvar", "बुधवार"), 3: ("thursday", "guruvar", "गुरुवार", "गुरूवार", "बृहस्पतिवार"),
    4: ("friday", "shukravar", "शुक्रवार"), 5: ("saturday", "shanivar", "शनिवार"),
    6: ("sunday", "ravivar", "रविवार"),
}
_TODAY_WORDS = ("today", "aaj", "आज")
_TOMORROW_WORDS = ("tomorrow", "kal", "कल", "उद्या", "udya", "udyā")
_DAY_AFTER_WORDS = ("day after tomorrow", "parso", "परसों", "परसो", "परवा", "parva", "parwa")
_NEXT_WORDS = ("next", "पुढच्या", "पुढील", "अगले", "अगला", "agle", "pudhchya")


def parse_date(text, today=None):
    """A date from the caller's words, or None. A booking is always in the
    future, so 'कल'/'kal' means tomorrow here."""
    today = today or today_ist()
    s = _norm(text)
    words = re.findall(r"[0-9]+|[a-z]+|[ऀ-ॿ]+", s)

    # ISO, dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy (Indian day-month order)
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", s)
    if m and 1 <= int(m.group(2)) <= 12:                 # "10.30" is a time, not a date
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        if y < 100:
            y += 2000
        try:
            found = date(y, mo, d)
            if not m.group(3) and found < today:
                found = found.replace(year=found.year + 1)
            return found
        except ValueError:
            pass

    if any(w in s for w in _DAY_AFTER_WORDS):
        return today + timedelta(days=2)
    if any(w in words for w in _TODAY_WORDS):
        return today
    if any(w in words for w in _TOMORROW_WORDS):
        return today + timedelta(days=1)

    # "2 October", "second October", "दो अक्टूबर", "दोन ऑक्टोबर", "October 2nd"
    month_pos = [(i, _MONTH_WORDS[w]) for i, w in enumerate(words) if w in _MONTH_WORDS]
    if month_pos:
        i, month = month_pos[0]
        day = None
        for j in sorted(range(len(words)), key=lambda j: abs(j - i)):
            w = re.sub(r"(st|nd|rd|th)$", "", words[j]) if words[j][0].isdigit() else words[j]
            if w.isdigit() and 1 <= int(w) <= 31:
                day = int(w); break
            if w in _NUMBER_WORDS and _NUMBER_WORDS[w] <= 31 and j != i:
                day = _NUMBER_WORDS[w]; break
        if day:
            try:
                found = date(today.year, month, day)
            except ValueError:
                return None
            if found < today:
                found = found.replace(year=today.year + 1)
            return found

    # Weekday names ("next Monday", "सोमवारी", "पुढच्या शुक्रवारी")
    for wd, names in _WEEKDAY_WORDS.items():
        if any((n in s) if not n.isascii() else (n in words) for n in names):
            ahead = (wd - today.weekday()) % 7
            if ahead == 0 and any(n in s for n in _NEXT_WORDS):
                ahead = 7
            return today + timedelta(days=ahead)
    return None


_AM_WORDS = ("am", "morning", "subah", "सुबह", "सवेरे", "सकाळी", "sakali", "sakaali")
_PM_WORDS = ("pm", "afternoon", "evening", "noon", "dopahar", "dopehar", "sham", "shaam", "dupari",
             "दोपहर", "शाम", "दुपारी", "संध्याकाळी", "संध्याकाळ")
_HALF_PAST = ("half past", "saadhe", "sadhe", "साढ़े", "साढे", "साडे", "साडेतीन")
_ONE_THIRTY = ("dedh", "डेढ़", "डेढ", "दीड", "deed")
_TWO_THIRTY = ("dhai", "ढाई", "अडीच", "adich")


def parse_time(text):
    """A time from the caller's words, or None. With no morning/afternoon
    word, 8-11 are taken as morning and 12-7 as afternoon (OPD runs
    08:30 AM - 05:00 PM)."""
    s = _norm(text).replace("a.m.", "am").replace("p.m.", "pm").replace("a. m.", "am").replace("p. m.", "pm")
    words = re.findall(r"[0-9]+|[a-z]+|[ऀ-ॿ]+", s)
    hour = minute = None

    m = re.search(r"\b(\d{1,2})\s*[:.]\s*(\d{2})\b", s) or re.search(r"\b(\d{1,2})\s+(30|00)\b", s)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    elif any(w in s for w in _ONE_THIRTY):
        hour, minute = 1, 30
    elif any(w in s for w in _TWO_THIRTY):
        hour, minute = 2, 30
    else:
        nums = [int(w) for w in words if w.isdigit() and 1 <= int(w) <= 12]
        # Hindi "do" (two) / Marathi "don" count only next to baje/vajta,
        # so the English word "do" is not read as a number.
        clock_word = any(w in s for w in ("baje", "बजे", "vajta", "वाजता", "o'clock", "oclock"))
        spoken = [_NUMBER_WORDS[w] for w in words
                  if w in _NUMBER_WORDS and _NUMBER_WORDS[w] <= 12
                  and (clock_word or w not in ("do", "don", "ek"))]
        if nums:
            hour = nums[0]
        elif spoken:
            hour = spoken[0]
        elif "noon" in words or "दोपहर बारह" in s or "दुपारी बारा" in s:
            hour = 12
        if hour is not None:
            minute = 30 if (any(w in s for w in _HALF_PAST) or "thirty" in words
                            or "तीस" in s or "30" in words) else 0
    if hour is None or not (0 <= hour <= 23) or minute not in range(60):
        return None
    if any(w in s for w in _HALF_PAST) and minute == 0:
        minute = 30
    is_pm = any((w in words) if w.isascii() else (w in s) for w in _PM_WORDS)
    is_am = any((w in words) if w.isascii() else (w in s) for w in _AM_WORDS)
    if hour <= 12:
        if is_pm and hour < 12:
            hour += 12
        elif not is_am and not is_pm and 1 <= hour <= 7:
            hour += 12
    return time(hour, minute)


_NO_WORDS = ("no", "nope", "not", "don't", "dont", "wrong", "incorrect", "change", "cancel",
             "nahi", "nahin", "naahi", "nako", "galat", "badlo", "badla",
             "नहीं", "नही", "गलत", "ग़लत", "नाही", "नको", "चूक", "बदल", "कैंसल", "रद्द")
_UNSURE_WORDS = ("maybe", "perhaps", "shayad", "शायद", "कदाचित", "सकता", "सकती", "not sure")
_YES_WORDS = ("yes", "yeah", "yep", "ok", "okay", "sure", "correct", "right", "confirm", "confirmed",
              "proceed", "haan", "han", "haa", "ha", "hoy", "ho", "theek", "thik", "sahi", "barobar",
              "chalel", "ji", "हाँ", "हां", "हा", "जी", "ठीक", "सही", "हो", "होय", "बरोबर", "चालेल",
              "यस", "कन्फर्म", "ओके", "ओक")
_YES_PHRASES = ("go ahead", "book it", "book kar", "do it", "please book", "कर दो", "कर दीजिए",
                "करा", "बुक करा", "बुक कर")


def classify_yes_no(text, ignore=()):
    """'yes', 'no' or 'unclear'. A 'no' always wins over a 'yes' in the same
    answer ("नहीं जी, गलत है" is no); 'maybe' is unclear. `ignore` lists
    words that are not a 'no' here ("yes, cancel it" when cancelling)."""
    s = _norm(text)
    words = re.findall(r"[a-z']+|[ऀ-ॿ]+", s)
    if any(w in _UNSURE_WORDS for w in words) or "not sure" in s or "हो सकता" in s:
        return "unclear"
    no_words = [w for w in _NO_WORDS if w not in ignore]
    if any(w in no_words for w in words) or any(
            w in s for w in no_words if not w.isascii() and len(w) >= 3):
        return "no"
    if any(w in _YES_WORDS for w in words) or any(p in s for p in _YES_PHRASES):
        return "yes"
    return "unclear"


_STOP_PHRASES = ("stop booking", "cancel booking", "cancel the booking", "don't book", "do not book",
                 "never mind", "leave it", "rehne do", "rahne do", "रहने दो", "जाने दो", "राहू द्या",
                 "राहू दे", "बुकिंग नको", "बुकिंग रद्द", "नहीं करनी", "नही करनी")


_BOOK_WORDS = ("appointment", "appoint", "book", "booking", "reserve", "अपॉइंटमेंट", "अपॉईंटमेंट",
               "अपाइंटमेंट", "अपॉइंटमेन्ट", "बुक", "बुकिंग", "नंबर लगा", "वेळ घ्याय", "भेट घ्याय",
               "नाव नोंद", "नाम लिख")
_NOT_BOOKING = ("cancel", "कैंसल", "रद्द", "status", "check my", "my booking", "my appointment",
                "मेरी बुकिंग", "मेरा अपॉइंटमेंट", "माझी अपॉइंटमेंट", "माझी बुकिंग", "how can i book",
                "how do i book", "कैसे बुक", "कसे बुक", "कशी बुक")


def wants_to_book(text):
    """The caller asks to book an appointment (not to cancel or check one)."""
    s = _norm(text)
    return any(w in s for w in _BOOK_WORDS) and not any(w in s for w in _NOT_BOOKING)


_QUESTION_WORDS = ("where", "what", "when", "how", "which", "who", "why", "is there", "do you",
                   "कहाँ", "कहां", "क्या", "कौन", "कब", "कैसे", "कितना", "कुठे", "काय", "कोण", "कधी",
                   "कसे", "किती", "आहे का")


def looks_like_question(text):
    s = _norm(text)
    return "?" in s or any(w in s for w in _QUESTION_WORDS)


def wants_to_stop(text):
    s = _norm(text)
    return any(p in s for p in _STOP_PHRASES)


_HONORIFICS = {"dr", "doctor", "sir", "madam", "mam", "ji", "saheb", "sahab", "maam",
               "डॉ", "डॉक्टर", "डा", "डाक्टर", "डोक्टर", "डॉक्टर्स", "डॉक्टरांकडे", "जी", "साहब", "साहेब", "मॅडम", "मैडम", "सर"}


def find_doctors(text, among=None):
    """Doctor keys named in the text (Latin, Devanagari or Gujarati letters,
    small spelling slips allowed). Returns the best matches (usually one)."""
    s = _norm(text)
    tokens = [t for t in re.findall(r"[a-z]+|[ऀ-ॿ]+", s)
              if t not in _HONORIFICS and len(t) >= 3]
    best, best_score = [], 0.0
    for key in (among or DOCTOR_NAMES_DEVANAGARI):
        latin = key.replace("DR. ", "").lower().split()
        dev = DOCTOR_NAMES_DEVANAGARI[key].split()
        score = 0.0
        for name_part in latin + dev:
            ratios = [difflib.SequenceMatcher(None, tok, name_part).ratio() for tok in tokens]
            r = max(ratios, default=0)
            limit = 0.8 if name_part.isascii() else 0.75
            if r >= limit:
                score += r
        if score > best_score + 1e-9:
            best, best_score = [key], score
        elif score and abs(score - best_score) < 1e-9:
            best.append(key)
    return best if best_score >= 0.8 else []


def find_departments(text):
    """Department keys named in the text (everyday words in any language)."""
    s = _norm(text)
    words = set(re.findall(r"[a-z]+|[ऀ-ॿ]+", s))
    for keywords, depts in _DEPARTMENT_WORDS:
        for k in keywords:
            if (" " in k and k in s) or (k.isascii() and (k in words or (len(k) >= 5 and any(w.startswith(k) for w in words)))) \
                    or (not k.isascii() and k in s):
                return list(depts)
    return []


def extract_name(text):
    """The patient's name from an answer such as 'my name is Ganesh Shinde'."""
    s = to_devanagari(text or "").strip()
    s = re.sub(r"(?i)^(my name is|name is|i am|this is|patient name is|patient's name is|it is)\s+", "", s)
    s = re.sub(r"^(मेरा नाम|मरीज़ का नाम|मरीज का नाम|माझे नाव|माझं नाव|रुग्णाचे नाव)\s*", "", s)
    s = re.sub(r"\s*(है|हैं|आहे|hai|aahe)[\s.।!]*$", "", s)
    s = s.strip(" .,।!?\"'")
    if not s or re.search(r"\d", s) or len(s) > 60 or len(s.split()) > 5:
        return None
    if find_doctors(s) or phone_digit_count(s) >= 3 or any(
            h in _norm(s).split() for h in ("dr", "doctor", "डॉ", "डॉक्टर", "डोक्टर")):
        return None
    return s


_REASON_PRIVATE = ("confidential", "confident", "private", "not to share", "don't want to say",
                   "nahi batana", "गोपनीय", "नहीं बताना", "नही बताना", "सांगायचे नाही", "सांगायचं नाही")


def extract_reason(text):
    s = to_devanagari(text or "").strip(" .,।!?")
    if not s:
        return None
    if any(p in s.lower() for p in _REASON_PRIVATE):
        return "Not shared"
    return s[:120]


# ---------------------------------------------------------------------------
# Schedule and 30-minute slots
# ---------------------------------------------------------------------------
SLOT_MINUTES = 30
MAX_DAYS_AHEAD = 60


def _t(s):
    return datetime.strptime(s, "%I:%M %p").time()


def doctor_days(core, key):
    """Weekdays (e.g. 'MONDAY') on which the doctor sits, with the window."""
    days = {}
    for day, docs in core.DOCTOR_SCHEDULE.items():
        if key in docs:
            days[day] = (_t(docs[key]["from"]), _t(docs[key]["to"]))
    return days


def doctor_department(core, key):
    for docs in core.DOCTOR_SCHEDULE.values():
        if key in docs:
            return docs[key]["department"]
    return ""


def doctors_in_departments(core, depts):
    found = []
    for docs in core.DOCTOR_SCHEDULE.values():
        for key, info in docs.items():
            if info["department"] in depts and key not in found:
                found.append(key)
    return found


def all_slots(t_from, t_to):
    """Start times on the half hour; the whole 30 minutes must fit before t_to."""
    start = datetime.combine(date.today(), t_from)
    if start.minute % SLOT_MINUTES:
        start += timedelta(minutes=SLOT_MINUTES - start.minute % SLOT_MINUTES)
    end = datetime.combine(date.today(), t_to)
    slots = []
    while start + timedelta(minutes=SLOT_MINUTES) <= end:
        slots.append(start.time())
        start += timedelta(minutes=SLOT_MINUTES)
    return slots


def free_slots(core, key, day):
    """Free 30-minute start times for the doctor on `day` (a date)."""
    window = doctor_days(core, key).get(WEEKDAYS[day.weekday()])
    if not window:
        return []
    taken = core.booked_times(key, day.isoformat())
    slots = [t for t in all_slots(*window) if t.strftime("%I:%M %p") not in taken]
    if day == today_ist():
        soon = (now_ist() + timedelta(minutes=SLOT_MINUTES)).time()
        slots = [t for t in slots if t >= soon]
    return slots


def nearest_slots(slots, wanted, n=3):
    minutes = wanted.hour * 60 + wanted.minute
    return sorted(sorted(slots, key=lambda t: abs(t.hour * 60 + t.minute - minutes))[:n])


# ---------------------------------------------------------------------------
# What the desk says during a booking (one wording per language)
# ---------------------------------------------------------------------------
TEXT = {
    "ask_name": {
        "English": "Certainly. May I have the patient's full name, please?",
        "Hindi": "ज़रूर। कृपया मरीज़ का पूरा नाम बताइए।",
        "Marathi": "नक्की. कृपया रुग्णाचे पूर्ण नाव सांगा.",
    },
    "bad_name": {
        "English": "Sorry, I did not catch the name. Please say the patient's full name again.",
        "Hindi": "माफ़ कीजिए, नाम समझ नहीं आया। कृपया मरीज़ का पूरा नाम फिर से बताइए।",
        "Marathi": "माफ करा, नाव समजले नाही. कृपया रुग्णाचे पूर्ण नाव पुन्हा सांगा.",
    },
    "ask_phone": {
        "English": "Thank you. Please tell me your ten-digit mobile number.",
        "Hindi": "धन्यवाद। कृपया अपना दस अंकों का मोबाइल नंबर बताइए।",
        "Marathi": "धन्यवाद. कृपया तुमचा दहा अंकी मोबाईल नंबर सांगा.",
    },
    "bad_phone": {
        "English": "I heard {n} digits. Please say your ten-digit mobile number again, one digit at a time.",
        "Hindi": "मुझे {n} अंक सुनाई दिए। कृपया अपना दस अंकों का मोबाइल नंबर एक-एक अंक करके फिर से बताइए।",
        "Marathi": "मला {n} अंक ऐकू आले. कृपया तुमचा दहा अंकी मोबाईल नंबर एक-एक अंक करून पुन्हा सांगा.",
    },
    "ask_doctor": {
        "English": "Which doctor or which department would you like to see?",
        "Hindi": "आप किस डॉक्टर को या किस विभाग में दिखाना चाहते हैं?",
        "Marathi": "तुम्हाला कोणत्या डॉक्टरांकडे किंवा कोणत्या विभागात दाखवायचे आहे?",
    },
    "bad_doctor": {
        "English": "I could not find that doctor. Please say the doctor's name or the department again.",
        "Hindi": "यह डॉक्टर मुझे नहीं मिले। कृपया डॉक्टर का नाम या विभाग फिर से बताइए।",
        "Marathi": "हे डॉक्टर मला सापडले नाहीत. कृपया डॉक्टरांचे नाव किंवा विभाग पुन्हा सांगा.",
    },
    "choose_doctor": {
        "English": "In {dept} we have {names}. Which doctor would you like?",
        "Hindi": "{dept} में {names} हैं। आप किस डॉक्टर को दिखाना चाहेंगे?",
        "Marathi": "{dept} विभागात {names} आहेत. तुम्हाला कोणत्या डॉक्टरांकडे दाखवायचे आहे?",
    },
    "choose_between": {
        "English": "Did you mean {names}?",
        "Hindi": "क्या आपका मतलब {names} से है?",
        "Marathi": "तुम्हाला {names} यांच्यापैकी कोण म्हणायचे आहे?",
    },
    "doctor_days": {
        "English": "{doctor} sits on {days}, {window}.",
        "Hindi": "{doctor} {days}, {window} उपलब्ध हैं।",
        "Marathi": "{doctor} {days}, {window} उपलब्ध आहेत.",
    },
    "ask_date": {
        "English": "On which date would you like to come?",
        "Hindi": "आप किस तारीख को आना चाहेंगे?",
        "Marathi": "तुम्हाला कोणत्या तारखेला यायचे आहे?",
    },
    "bad_date": {
        "English": "Sorry, I did not understand the date. Please say it like 'Monday' or '2 October'.",
        "Hindi": "माफ़ कीजिए, तारीख समझ नहीं आई। कृपया 'सोमवार' या '2 अक्टूबर' की तरह बताइए।",
        "Marathi": "माफ करा, तारीख समजली नाही. कृपया 'सोमवार' किंवा '२ ऑक्टोबर' असे सांगा.",
    },
    "past_date": {
        "English": "That date has already passed. Please choose a date from today onwards.",
        "Hindi": "यह तारीख निकल चुकी है। कृपया आज या आगे की कोई तारीख बताइए।",
        "Marathi": "ही तारीख उलटून गेली आहे. कृपया आजची किंवा पुढची तारीख सांगा.",
    },
    "far_date": {
        "English": "Bookings can be made up to two months ahead. Please choose an earlier date.",
        "Hindi": "बुकिंग केवल दो महीने आगे तक होती है। कृपया पहले की कोई तारीख बताइए।",
        "Marathi": "बुकिंग फक्त दोन महिने पुढपर्यंत करता येते. कृपया त्याआधीची तारीख सांगा.",
    },
    "not_that_day": {
        "English": "{doctor} does not sit on {date}. {doctor_days} Which date would you like?",
        "Hindi": "{doctor} {date} को उपलब्ध नहीं हैं। {doctor_days} आप किस तारीख को आना चाहेंगे?",
        "Marathi": "{doctor} {date} रोजी उपलब्ध नाहीत. {doctor_days} तुम्हाला कोणत्या तारखेला यायचे आहे?",
    },
    "no_free_day": {
        "English": "There is no free time with {doctor} on {date}. Please choose another date.",
        "Hindi": "{date} को {doctor} के पास कोई समय खाली नहीं है। कृपया दूसरी तारीख बताइए।",
        "Marathi": "{date} रोजी {doctor} यांच्याकडे वेळ रिकामी नाही. कृपया दुसरी तारीख सांगा.",
    },
    "ask_time": {
        "English": "On {date}, {doctor} sits {window}. The first free times are {slots}. Which time suits you?",
        "Hindi": "{date} को {doctor} {window} उपलब्ध हैं। खाली समय हैं {slots}। आपको कौन सा समय ठीक रहेगा?",
        "Marathi": "{date} रोजी {doctor} {window} उपलब्ध आहेत. रिकाम्या वेळा आहेत {slots}. तुम्हाला कोणती वेळ सोयीची आहे?",
    },
    "bad_time": {
        "English": "Sorry, I did not understand the time. Please say it like '11 AM' or 'half past 2'.",
        "Hindi": "माफ़ कीजिए, समय समझ नहीं आया। कृपया 'सुबह 11 बजे' या 'दोपहर ढाई बजे' की तरह बताइए।",
        "Marathi": "माफ करा, वेळ समजली नाही. कृपया 'सकाळी ११ वाजता' किंवा 'दुपारी अडीच वाजता' असे सांगा.",
    },
    "time_not_free": {
        "English": "{time} is not available. The nearest free times are {slots}. Which one would you like?",
        "Hindi": "{time} उपलब्ध नहीं है। सबसे पास के खाली समय हैं {slots}। आप कौन सा चाहेंगे?",
        "Marathi": "{time} उपलब्ध नाही. जवळच्या रिकाम्या वेळा आहेत {slots}. तुम्हाला कोणती हवी आहे?",
    },
    "ask_reason": {
        "English": "What is the reason for the visit? If you prefer not to say, just say 'private'.",
        "Hindi": "आने का कारण क्या है? अगर बताना नहीं चाहते, तो 'गोपनीय' कहिए।",
        "Marathi": "भेटीचे कारण काय आहे? सांगायचे नसल्यास 'गोपनीय' म्हणा.",
    },
    "read_back": {
        "English": "Please confirm: patient {name}, mobile {phone}, with {doctor}, {dept}, on {date} at {time}, reason: {reason}. Shall I book it? Please say yes or no.",
        "Hindi": "कृपया पुष्टि कीजिए: मरीज़ {name}, मोबाइल {phone}, {doctor}, {dept}, {date} को {time}, कारण: {reason}। क्या मैं बुक कर दूँ? कृपया हाँ या नहीं कहिए।",
        "Marathi": "कृपया खात्री करा: रुग्ण {name}, मोबाईल {phone}, {doctor}, {dept}, {date} रोजी {time}, कारण: {reason}. मी बुक करू का? कृपया हो किंवा नाही सांगा.",
    },
    "reason_private": {"English": "not shared", "Hindi": "गोपनीय", "Marathi": "गोपनीय"},
    "unclear_yes_no": {
        "English": "Please say yes to book, or no to change something.",
        "Hindi": "बुक करने के लिए हाँ कहिए, या कुछ बदलना हो तो नहीं कहिए।",
        "Marathi": "बुक करण्यासाठी हो म्हणा, किंवा काही बदलायचे असल्यास नाही म्हणा.",
    },
    "ask_change": {
        "English": "What would you like to change: the name, mobile number, doctor, date, time or reason?",
        "Hindi": "आप क्या बदलना चाहते हैं: नाम, मोबाइल नंबर, डॉक्टर, तारीख, समय या कारण?",
        "Marathi": "तुम्हाला काय बदलायचे आहे: नाव, मोबाईल नंबर, डॉक्टर, तारीख, वेळ की कारण?",
    },
    "booked": {
        "English": "Your appointment is booked with {doctor} on {date} at {time}. Your booking ID is {bid}. Please note it down.",
        "Hindi": "आपका अपॉइंटमेंट {doctor} के साथ {date} को {time} बुक हो गया है। आपकी बुकिंग आईडी है {bid}। कृपया इसे लिख लीजिए।",
        "Marathi": "तुमची अपॉइंटमेंट {doctor} यांच्याकडे {date} रोजी {time} बुक झाली आहे. तुमचा बुकिंग आयडी आहे {bid}. कृपया तो लिहून ठेवा.",
    },
    "slot_just_taken": {
        "English": "Sorry, that time was just booked by someone else. The nearest free times are {slots}. Which one would you like?",
        "Hindi": "माफ़ कीजिए, यह समय अभी-अभी किसी और ने बुक कर लिया। सबसे पास के खाली समय हैं {slots}। आप कौन सा चाहेंगे?",
        "Marathi": "माफ करा, ही वेळ आत्ताच दुसऱ्यांनी बुक केली. जवळच्या रिकाम्या वेळा आहेत {slots}. तुम्हाला कोणती हवी आहे?",
    },
    "callback": {
        "English": "I am sorry, I could not complete the booking. Our reception team will call you back on {phone}.",
        "Hindi": "माफ़ कीजिए, मैं बुकिंग पूरी नहीं कर पाई। हमारी रिसेप्शन टीम आपको {phone} पर वापस कॉल करेगी।",
        "Marathi": "माफ करा, मी बुकिंग पूर्ण करू शकले नाही. आमची रिसेप्शन टीम तुम्हाला {phone} वर परत कॉल करेल.",
    },
    "callback_need_phone": {
        "English": "I am sorry, I could not complete the booking. Please tell me your mobile number, and our reception team will call you back.",
        "Hindi": "माफ़ कीजिए, मैं बुकिंग पूरी नहीं कर पाई। कृपया अपना मोबाइल नंबर बताइए, हमारी रिसेप्शन टीम आपको वापस कॉल करेगी।",
        "Marathi": "माफ करा, मी बुकिंग पूर्ण करू शकले नाही. कृपया तुमचा मोबाईल नंबर सांगा, आमची रिसेप्शन टीम तुम्हाला परत कॉल करेल.",
    },
    "callback_no_phone": {
        "English": "I am sorry, I could not take the booking. Please call our appointment desk on {desk}.",
        "Hindi": "माफ़ कीजिए, मैं बुकिंग नहीं ले पाई। कृपया हमारे अपॉइंटमेंट डेस्क {desk} पर कॉल कीजिए।",
        "Marathi": "माफ करा, मी बुकिंग घेऊ शकले नाही. कृपया आमच्या अपॉइंटमेंट डेस्कला {desk} वर कॉल करा.",
    },
    "stopped": {
        "English": "All right, I have not booked anything. How else can I help you?",
        "Hindi": "ठीक है, मैंने कुछ भी बुक नहीं किया है। मैं और कैसे मदद कर सकती हूँ?",
        "Marathi": "ठीक आहे, मी काहीही बुक केलेले नाही. मी आणखी कशी मदत करू?",
    },
    "continue": {
        "English": "Now, to continue the booking: {prompt}",
        "Hindi": "अब बुकिंग आगे बढ़ाते हैं: {prompt}",
        "Marathi": "आता बुकिंग पुढे करूया: {prompt}",
    },
}

_FIELD_WORDS = {
    "name": ("name", "naam", "नाम", "नाव"),
    "phone": ("phone", "mobile", "number", "नंबर", "मोबाइल", "मोबाईल", "फोन"),
    "doctor": ("doctor", "department", "डॉक्टर", "विभाग"),
    "date": ("date", "day", "तारीख", "दिन", "दिवस", "वार"),
    "time": ("time", "timing", "समय", "वेळ", "टाइम", "टाईम"),
    "reason": ("reason", "purpose", "कारण"),
}
ORDER = ("name", "phone", "doctor", "date", "time", "reason")


class BookingFlow:
    """One appointment booking, step by step. `core` is agent_core;
    `extractor(text, expect, language)` is the model fallback that returns a
    dict of fields found in a free-form sentence."""

    def __init__(self, core, extractor=None):
        self.core = core
        self.extractor = extractor
        self.f = {}                 # name, phone, doctor, date, time, reason
        self.stage = "collect"      # collect | confirm | change | callback_phone | done
        self.fail = {}
        self.options = []           # doctors offered when a department has several
        self.offered = []           # free slots last offered
        self.done = False

    # -- prompts -------------------------------------------------------------
    def expect(self):
        return next((k for k in ORDER if k not in self.f), None)

    def prompt(self, language):
        """The question for the next missing detail (or the read-back)."""
        field = self.expect()
        if field is None:
            self.stage = "confirm"
            return self.read_back(language)
        if field == "date":
            return self._days_line(language) + " " + TEXT["ask_date"][language]
        if field == "time":
            return self._ask_time(language)
        return TEXT["ask_" + field][language]

    def _days_line(self, language):
        """e.g. 'Doctor Radhika Iyengar sits on Monday to Friday, 11 AM to 4 PM.'
        (every doctor keeps the same hours on each day they sit)."""
        key = self.f["doctor"]
        days = doctor_days(self.core, key)
        window = say_window(*next(iter(days.values())), language)
        return TEXT["doctor_days"][language].format(
            doctor=say_doctor(key, language), days=say_days(days, language), window=window)

    def _ask_time(self, language):
        key, day = self.f["doctor"], self.f["date"]
        slots = free_slots(self.core, key, day)
        if not slots:
            self.f.pop("date", None)
            return TEXT["no_free_day"][language].format(doctor=say_doctor(key, language), date=say_date(day, language))
        self.offered = slots[:3]
        window = doctor_days(self.core, key)[WEEKDAYS[day.weekday()]]
        return TEXT["ask_time"][language].format(
            date=say_date(day, language), doctor=say_doctor(key, language),
            window=say_window(*window, language), slots=say_slots(self.offered, language))

    def read_back(self, language):
        f = self.f
        reason = TEXT["reason_private"][language] if f["reason"] == "Not shared" else f["reason"]
        return TEXT["read_back"][language].format(
            name=f["name"], phone=say_phone(f["phone"], language),
            doctor=say_doctor(f["doctor"], language),
            dept=say_department(doctor_department(self.core, f["doctor"]), language),
            date=say_date(f["date"], language), time=say_time(f["time"], language), reason=reason)

    # -- one caller turn -----------------------------------------------------
    def handle(self, text, language):
        """Returns (reply, status); status is 'continue', 'done' or
        'question' (the caller asked something else: answer it, then repeat
        `prompt`)."""
        text = to_devanagari(text)
        if wants_to_stop(text):
            self.done = True
            return TEXT["stopped"][language], "done"
        if self.stage == "confirm":
            return self._confirm(text, language)
        if self.stage == "change":
            return self._choose_change(text, language)
        if self.stage == "callback_phone":
            digits = phone_digits(text)
            if digits:
                self.f["phone"] = digits
                return self._callback(language)
            self.done = True
            return TEXT["callback_no_phone"][language].format(desk=self.core.APPOINTMENT_PHONE), "done"
        return self._collect(text, language)

    def _collect(self, text, language):
        field = self.expect()
        ok, message = self._take(field, text, language)
        if ok is None:
            # Details given out of order: a mobile number or a doctor said
            # while another detail was asked for is kept for later.
            if field != "phone" and "phone" not in self.f and phone_digits(text):
                self.f["phone"] = phone_digits(text)
                return self.prompt(language), "continue"
            if field != "doctor" and "doctor" not in self.f and len(find_doctors(text)) == 1:
                self.f["doctor"] = find_doctors(text)[0]
                return self.prompt(language), "continue"
        if ok is None:                          # nothing usable: try the model
            found = self.extractor(text, field, language) if self.extractor else {}
            if found.get("intent") == "question" and looks_like_question(text):
                return "", "question"
            ok, message = self._take_extracted(field, found, language)
            self._take_others(found, field, language)
        if ok:
            self.fail.pop(field, None)
            return self.prompt(language), "continue"
        if message.startswith("\x00"):          # guidance (choose a doctor / a free time)
            return message[1:], "continue"
        self.fail[field] = self.fail.get(field, 0) + 1
        if self.fail[field] >= 2:
            return self._callback(language)
        return message, "continue"

    def _take(self, field, text, language):
        """Try to fill `field` from the caller's words with code only.
        Returns (True, '') when filled; (False, message) when the answer was
        understood but is not acceptable; (None, message) when nothing
        usable was found. A message starting with '\\x00' is guidance that
        does not count as a failed attempt."""
        if field == "name":
            name = extract_name(text)
            if name:
                self.f["name"] = name
                return True, ""
            return None, TEXT["bad_name"][language]
        if field == "phone":
            digits = phone_digits(text)
            if digits:
                self.f["phone"] = digits
                return True, ""
            n = phone_digit_count(text)
            msg = TEXT["bad_phone"][language].format(n=n)
            return (False, msg) if n else (None, msg)
        if field == "doctor":
            return self._take_doctor(text, language)
        if field == "date":
            day = parse_date(text)
            return self._set_date(day, language) if day else (None, TEXT["bad_date"][language])
        if field == "time":
            t = parse_time(text)
            return self._set_time(t, language) if t else (None, TEXT["bad_time"][language])
        if field == "reason":
            reason = extract_reason(text)
            if reason:
                self.f["reason"] = reason
                return True, ""
            return None, TEXT["ask_reason"][language]
        return None, ""

    def _take_doctor(self, text, language):
        keys = find_doctors(text, among=self.options or None)
        if len(keys) == 1:
            self.f["doctor"], self.options = keys[0], []
            return True, ""
        depts = find_departments(text)
        if not keys and depts:
            keys = doctors_in_departments(self.core, depts)
        if len(keys) == 1:
            self.f["doctor"], self.options = keys[0], []
            return True, ""
        if len(keys) > 1:
            self.options = keys
            dept = say_department(doctor_department(self.core, keys[0]), language) if depts else ""
            names = _join([say_doctor(k, language) for k in keys], language)
            if not dept:
                return False, "\x00" + TEXT["choose_between"][language].format(names=names)
            return False, "\x00" + TEXT["choose_doctor"][language].format(dept=dept, names=names)
        return None, TEXT["bad_doctor"][language]

    def _set_date(self, day, language):
        today = today_ist()
        if day < today:
            return False, TEXT["past_date"][language]
        if day > today + timedelta(days=MAX_DAYS_AHEAD):
            return False, TEXT["far_date"][language]
        key = self.f["doctor"]
        if WEEKDAYS[day.weekday()] not in doctor_days(self.core, key):
            return False, TEXT["not_that_day"][language].format(
                doctor=say_doctor(key, language), date=say_date(day, language),
                doctor_days=self._days_line(language))
        if not free_slots(self.core, key, day):
            return False, TEXT["no_free_day"][language].format(
                doctor=say_doctor(key, language), date=say_date(day, language))
        self.f["date"] = day
        self.f.pop("time", None)
        return True, ""

    def _set_time(self, t, language):
        key, day = self.f["doctor"], self.f["date"]
        slots = free_slots(self.core, key, day)
        if _hm(t) in {_hm(s) for s in slots}:
            self.f["time"] = t
            return True, ""
        self.offered = nearest_slots(slots, t)
        return False, "\x00" + TEXT["time_not_free"][language].format(
            time=say_time(t, language), slots=say_slots(self.offered, language))

    def _take_extracted(self, field, found, language):
        value = (found or {}).get(field) or ""
        if not value:
            return False, self._retry_message(field, language)
        if field == "date":
            try:
                return self._set_date(date.fromisoformat(value), language)
            except ValueError:
                return False, TEXT["bad_date"][language]
        if field == "time":
            t = parse_time(value)
            return self._set_time(t, language) if t else (False, TEXT["bad_time"][language])
        if field == "doctor":
            if value in DOCTOR_NAMES_DEVANAGARI:
                self.f["doctor"] = value
                return True, ""
            return False, TEXT["bad_doctor"][language]
        ok, message = self._take(field, value, language)
        return (True, "") if ok else (False, message or self._retry_message(field, language))

    def _take_others(self, found, current, language):
        """Keep other details the caller mentioned in the same sentence."""
        for field in ("name", "phone", "reason"):
            if field != current and field not in self.f and (found or {}).get(field):
                self._take(field, found[field], language)

    def _retry_message(self, field, language):
        return {
            "name": TEXT["bad_name"], "phone": TEXT["ask_phone"], "doctor": TEXT["bad_doctor"],
            "date": TEXT["bad_date"], "time": TEXT["bad_time"], "reason": TEXT["ask_reason"],
        }[field][language].format(n=0)

    def _confirm(self, text, language):
        answer = classify_yes_no(text)
        if answer == "yes":
            return self._book(language)
        if answer == "no":
            self.stage = "change"
            changed = self._change_from(text, language)
            if changed:
                return changed
            return TEXT["ask_change"][language], "continue"
        self.fail["confirm"] = self.fail.get("confirm", 0) + 1
        if self.fail["confirm"] >= 3:
            return self._callback(language)
        return TEXT["unclear_yes_no"][language], "continue"

    def _change_from(self, text, language):
        """'No, make it 12 o'clock' -> change the time directly."""
        s = _norm(text)
        for field, words in _FIELD_WORDS.items():
            if any((w in s.split()) if w.isascii() else (w in s) for w in words):
                self._clear(field)
                ok, message = self._take(field, text, language)
                self.stage = "collect"
                if ok:
                    return self.prompt(language), "continue"
                return self.prompt(language), "continue"
        return None

    def _choose_change(self, text, language):
        s = _norm(text)
        for field, words in _FIELD_WORDS.items():
            if any((w in s.split()) if w.isascii() else (w in s) for w in words):
                self._clear(field)
                self.stage = "collect"
                return self.prompt(language), "continue"
        self.fail["change"] = self.fail.get("change", 0) + 1
        if self.fail["change"] >= 2:
            return self._callback(language)
        return TEXT["ask_change"][language], "continue"

    def _clear(self, field):
        self.f.pop(field, None)
        if field == "doctor":
            self.f.pop("date", None)
            self.f.pop("time", None)
        if field == "date":
            self.f.pop("time", None)

    def _book(self, language):
        f = self.f
        if not self.core.bookings_ready():
            return self._callback(language)
        record = self.core.book_slot(f["name"], f["phone"], f["date"], f["time"], f["reason"], f["doctor"])
        if record is None:                                  # someone took the slot meanwhile
            wanted = self.f.pop("time")
            self.stage = "collect"
            slots = free_slots(self.core, f["doctor"], f["date"])
            if not slots:
                self.f.pop("date", None)
                return self.prompt(language), "continue"
            self.offered = nearest_slots(slots, wanted)
            return TEXT["slot_just_taken"][language].format(slots=say_slots(self.offered, language)), "continue"
        self.done = True
        self.stage = "done"
        return TEXT["booked"][language].format(
            doctor=say_doctor(f["doctor"], language), date=say_date(f["date"], language),
            time=say_time(f["time"], language), bid=say_booking_id(record["booking_id"])), "done"

    def _callback(self, language):
        phone = self.f.get("phone")
        if not phone:
            self.stage = "callback_phone"
            return TEXT["callback_need_phone"][language], "continue"
        self.core.record_callback(self.f)
        self.done = True
        self.stage = "done"
        return TEXT["callback"][language].format(phone=say_phone(phone, language)), "done"
