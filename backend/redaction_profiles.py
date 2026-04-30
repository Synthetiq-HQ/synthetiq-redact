"""
Redaction profiles and category-to-profile mapping.
Controls which PII types are redacted based on document category.
"""

PROFILES: dict[str, set[str]] = {
    "general_pii": {
        "person_name", "address", "phone", "email", "dob",
        "postcode", "signature", "council_ref", "nin",
    },
    "medical_strict": {
        "person_name", "address", "phone", "email", "dob",
        "postcode", "nin", "nhs_number", "signature", "medical_details", "notes",
    },
    "financial_strict": {
        "nin", "bank_account", "bank_details", "sort_code",
        "council_ref", "benefit_ref", "notes",
    },
    "safeguarding_strict": {
        "person_name", "address", "phone", "email", "dob",
        "postcode", "nin", "school", "signature", "case_ref", "medical_details", "notes",
    },
    "vehicle_parking": {
        "vehicle_reg", "pcn", "person_name", "address", "phone", "email",
    },
    "unknown_strict": {
        "person_name", "address", "phone", "email", "dob",
        "postcode", "nin", "signature", "council_ref", "notes",
        "bank_details",
    },
}

CATEGORY_PROFILE_MAP: dict[str, list[str]] = {
    "housing_repairs":       ["general_pii"],
    "complaint":             ["general_pii"],
    "waste":                 ["general_pii"],
    "council_tax":           ["general_pii", "financial_strict"],
    "parking":               ["general_pii", "vehicle_parking"],
    "adult_social_care":     ["general_pii", "medical_strict"],
    "children_safeguarding": ["general_pii", "safeguarding_strict", "medical_strict"],
    "foi_legal":             ["general_pii"],
    "translation":           ["general_pii"],
    "unknown":               ["unknown_strict"],
}

# Categories/profiles that always trigger human review
REVIEW_REQUIRED_CATEGORIES = {"foi_legal", "unknown"}
REVIEW_REQUIRED_PROFILES = {"safeguarding_strict"}


def get_profiles_for_category(category: str) -> list[str]:
    return CATEGORY_PROFILE_MAP.get(category or "unknown", ["general_pii"])


def get_allowed_types(profiles: list[str]) -> set[str]:
    types: set[str] = set()
    for p in profiles:
        types |= PROFILES.get(p, set())
    return types


def requires_review(category: str, profiles: list[str]) -> bool:
    if category in REVIEW_REQUIRED_CATEGORIES:
        return True
    return bool(set(profiles) & REVIEW_REQUIRED_PROFILES)
