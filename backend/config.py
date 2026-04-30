import os
import re

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
DB_PATH = os.path.join(DATA_DIR, "db.sqlite3")

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Document categories with keyword triggers
CATEGORIES = {
    "housing_repairs": ["mould", "damp", "repair", "leak", "broken", "heating", "boiler"],
    "council_tax": ["council tax", "benefit", "hardship", "payment", "arrears", "discount"],
    "parking": ["parking", "fine", "PCN", "permit", "ticket", "appeal", "vehicle"],
    "complaint": ["complaint", "appeal", "unhappy", "dissatisfied", "service"],
    "waste": ["waste", "fly-tipping", "bin", "rubbish", "noise", "collection"],
    "adult_social_care": ["adult", "elderly", "care", "disability", "support", "carer"],
    "children_safeguarding": ["child", "safeguarding", "abuse", "neglect", "concern", "vulnerable"],
    "foi_legal": ["FOI", "SAR", "freedom of information", "subject access", "legal", "GDPR"],
    "translation": ["translate", "language", "interpreter", "non-english"],
}

# Department routing
DEPARTMENTS = {
    "housing_repairs": "Housing & Property Services",
    "council_tax": "Revenue & Benefits",
    "parking": "Parking Services",
    "complaint": "Customer Relations / Complaints",
    "waste": "Environmental Services",
    "adult_social_care": "Adult Social Care",
    "children_safeguarding": "Children's Services / Safeguarding",
    "foi_legal": "Legal & Governance",
    "translation": "Customer Services / Translation Hub",
    "unknown": "General Enquiries",
}

# Redaction regex patterns (compiled)
REDACTION_PATTERNS = {
    "email": re.compile(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}", re.IGNORECASE
    ),
    "phone": re.compile(
        r"(?:\+44\s?\(?0\)?[\s\-]?)?(?:\(0\)[\s\-]?)?[1-9][0-9]{0,4}[\s\-]?[0-9\s\-]{6,10}(?![0-9])"
    ),
    "postcode": re.compile(
        r"[A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2}", re.IGNORECASE
    ),
    "dob": re.compile(
        r"(?:\b(?:0?[1-9]|[12][0-9]|3[01])[/-](?:0?[1-9]|1[0-2])[/-](?:19|20)?\d{2}\b)"
        r"|(?:\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12][0-9]|3[01])[/-](?:19|20)?\d{2}\b)"
    ),
    "nin": re.compile(
        r"(?:[A-CEGHJ-PR-TW-Z]{1}[A-CEGHJ-NPR-TW-Z]{1}\s?\d{6}\s?[A-DFM]{1})|(?:[A-CEGHJ-PR-TW-Z]{1}\s?\d{6}\s?[A-DFM]{1})",
        re.IGNORECASE,
    ),
    "bank_account": re.compile(
        r"(?:\b\d{8}\b)\s*(?:sort\s*code[\s:]*\d{2}[-\s]?\d{2}[-\s]?\d{2})?|(?:\d{2}[-\s]?\d{2}[-\s]?\d{2}\s*\d{8})"
    ),
    "vehicle_reg": re.compile(
        r"(?:[A-Z]{2}\s?\d{2}\s?[A-Z]{3})|(?:[A-Z]{1,3}\s?\d{1,4}\s?[A-Z]{1,3})|(?:\d{1,4}\s?[A-Z]{1,3}\s?\d{1,2})",
        re.IGNORECASE,
    ),
    "council_ref": re.compile(
        r"\bREF-?\d{5,8}\b", re.IGNORECASE
    ),
}

# Sensitive keywords for risk detection
SENSITIVE_KEYWORDS = {
    "safeguarding": ["abuse", "neglect", "unsafe", "hurt", "scared"],
    "distress": ["suicide", "self-harm", "depression", "desperate", "nowhere"],
    "financial_hardship": ["can't pay", "starving", "eviction", "homeless", "no money"],
    "angry": ["disgusting", "unacceptable", "useless", "terrible", "furious"],
    "unsafe_housing": ["mould", "damp", "cold", "no heating", "rat", "infestation"],
    "repeated_complaint": ["again", "before", "still", "nothing done", "ignored"],
}

CONFIDENCE_THRESHOLD = 0.6

# Category urgency bases
CATEGORY_URGENCY_BASE = {
    "housing_repairs": 0.5,
    "council_tax": 0.4,
    "parking": 0.3,
    "complaint": 0.4,
    "waste": 0.3,
    "adult_social_care": 0.7,
    "children_safeguarding": 1.0,
    "foi_legal": 0.3,
    "translation": 0.2,
    "unknown": 0.2,
}
