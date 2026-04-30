"""
Text-only redaction evaluation for synthetic extracted document text.

This script does not run OCR, image redaction, database writes, or Ollama.
It exercises the existing profile-aware text redaction path directly.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from redaction import RedactionEngine
from redaction_profiles import (
    get_allowed_types,
    get_profiles_for_category,
    requires_review,
)

TYPE_ALIASES = {
    "nhs_number": "nin",
    "pcn": "vehicle_reg",
}


@dataclass(frozen=True)
class RedactionCase:
    id: str
    category: str
    selected_category: str | None
    input_text: str
    expected_redacted_values: list[str]
    expected_unredacted_labels: list[str]
    expected_not_redacted_values: list[str]
    expected_redaction_types: list[str]
    expected_needs_review: bool


def build_cases() -> list[RedactionCase]:
    """Return 50 synthetic extracted-text redaction cases."""
    return [
        # Housing repairs
        RedactionCase(
            "housing_01_known_form",
            "housing_repairs",
            "housing_repairs",
            "\n".join(
                [
                    "Full Name: Daniel Mercer",
                    "Date of Birth: 14 March 1993",
                    "Address: 82 Willow Crescent, Brookfield, NY 11726",
                    "Phone: (555) 814-2937",
                    "Email: daniel.mercer93@examplemail.com",
                    "National ID: XJ-4829-1173",
                    "Occupation: Logistics Coordinator",
                    "Emergency Contact Sarah Mercer",
                    "Emergency Phone (555) 901-4421",
                    "Notes: Allergic to penicillin.",
                    "Signature: Daniel Mercer",
                    "Date: 24 May 2024",
                ]
            ),
            [
                "Daniel Mercer",
                "14 March 1993",
                "82 Willow Crescent, Brookfield, NY 11726",
                "(555) 814-2937",
                "daniel.mercer93@examplemail.com",
                "Sarah Mercer",
                "(555) 901-4421",
                "Daniel Mercer",
            ],
            [
                "Full Name:",
                "Date of Birth:",
                "Address:",
                "Phone:",
                "Email:",
                "National ID:",
                "Occupation:",
                "Emergency Contact",
                "Emergency Phone",
                "Notes:",
                "Signature:",
                "Date:",
            ],
            ["Logistics Coordinator", "24 May 2024", "National ID:", "Allergic to penicillin"],
            ["person_name", "dob", "address", "phone", "email", "signature"],
            False,
        ),
        RedactionCase(
            "housing_02_multiline_address",
            "housing_repairs",
            "housing_repairs",
            "Name: Priya Shah\nAddress: 14 Elm Road\nUxbridge UB8 1AA\nPhone: 07700 900111\nIssue: mould in bedroom",
            ["Priya Shah", "14 Elm Road\nUxbridge UB8 1AA", "07700 900111"],
            ["Name:", "Address:", "Phone:", "Issue:"],
            ["mould in bedroom"],
            ["person_name", "address", "phone"],
            False,
        ),
        RedactionCase(
            "housing_03_no_colon",
            "housing_repairs",
            "housing_repairs",
            "Applicant Name Omar Clarke\nProperty Address 9 Cedar Close Hayes UB3 2AB\nContact Number 020 8123 4567\nRepair type boiler leak",
            ["Omar Clarke", "9 Cedar Close Hayes UB3 2AB", "020 8123 4567"],
            ["Applicant Name", "Property Address", "Contact Number"],
            ["Repair type boiler leak"],
            ["person_name", "address", "phone"],
            False,
        ),
        RedactionCase(
            "housing_04_letter_date",
            "housing_repairs",
            "housing_repairs",
            "Date: 12 April 2026\nReported by: Aisha Khan\nEmail: aisha.khan@example.test\nComplaint: heating still broken",
            ["Aisha Khan", "aisha.khan@example.test"],
            ["Date:", "Reported by:", "Email:", "Complaint:"],
            ["12 April 2026", "heating still broken"],
            ["person_name", "email"],
            False,
        ),
        RedactionCase(
            "housing_05_reference",
            "housing_repairs",
            "housing_repairs",
            "Reference: REF-284756\nFull Name: Mark Ellis\nHome Address: 3 Demo Street UB10 0AA\nDescription: damp wall in kitchen",
            ["REF-284756", "Mark Ellis", "3 Demo Street UB10 0AA"],
            ["Reference:", "Full Name:", "Home Address:", "Description:"],
            ["damp wall in kitchen"],
            ["council_ref", "person_name", "address"],
            False,
        ),
        # Council tax / benefits
        RedactionCase(
            "council_tax_01_financial",
            "council_tax",
            "council_tax",
            "Full Name: Helen Brooks\nNI Number: QQ 12 34 56 C\nBank Account: 12345678\nSort Code: 12-34-56\nEmail: helen.brooks@example.test",
            ["Helen Brooks", "QQ 12 34 56 C", "12345678", "12-34-56", "helen.brooks@example.test"],
            ["Full Name:", "NI Number:", "Bank Account:", "Sort Code:", "Email:"],
            [],
            ["person_name", "nin", "bank_details", "email"],
            False,
        ),
        RedactionCase(
            "council_tax_02_hardship_notes",
            "council_tax",
            "council_tax",
            "Applicant: Maria Lopez\nAddress: 7 Riverside Court UB8 2PQ\nNotes: I cannot afford food this month after rent.",
            ["Maria Lopez", "7 Riverside Court UB8 2PQ", "I cannot afford food this month after rent."],
            ["Applicant:", "Address:", "Notes:"],
            [],
            ["person_name", "address", "notes"],
            False,
        ),
        RedactionCase(
            "council_tax_03_employer_boundary",
            "council_tax",
            "council_tax",
            "Name: Callum Price\nNIN: AB123456C\nEmployer: Demo Warehouse Ltd\nStatus: arrears plan requested",
            ["Callum Price", "AB123456C"],
            ["Name:", "NIN:", "Employer:", "Status:"],
            ["Demo Warehouse Ltd", "arrears plan requested"],
            ["person_name", "nin"],
            False,
        ),
        RedactionCase(
            "council_tax_04_benefit_ref",
            "council_tax",
            "council_tax",
            "Full Name: Nina Patel\nCouncil tax reference REF-778812\nPhone: 01895 222333\nPayment date: 2 May 2026",
            ["Nina Patel", "REF-778812", "01895 222333"],
            ["Full Name:", "Phone:"],
            ["2 May 2026"],
            ["person_name", "council_ref", "phone"],
            False,
        ),
        RedactionCase(
            "council_tax_05_email_phone",
            "council_tax",
            "council_tax",
            "Email Address: resident.tax@example.test\nMobile 07700 111222\nDOB 05/09/1984\nRequest: discount review",
            ["resident.tax@example.test", "07700 111222", "05/09/1984"],
            ["Email Address:", "Mobile", "DOB"],
            ["discount review"],
            ["email", "phone", "dob"],
            False,
        ),
        # Parking
        RedactionCase(
            "parking_01_vehicle_pcn",
            "parking",
            "parking",
            "Name: Robert Williams\nVehicle Reg: AB12 XYZ\nPCN: HT20268847\nEmail: robert.w@example.test\nAppeal reason: sign was unclear",
            ["Robert Williams", "AB12 XYZ", "HT20268847", "robert.w@example.test"],
            ["Name:", "Vehicle Reg:", "PCN:", "Email:"],
            ["sign was unclear"],
            ["person_name", "vehicle_reg", "email"],
            False,
        ),
        RedactionCase(
            "parking_02_no_colon_vrm",
            "parking",
            "parking",
            "Applicant Name Tina Gray\nVRM CD34 EFG\nPhone 020 7999 1111\nDate: 24 May 2024",
            ["Tina Gray", "CD34 EFG", "020 7999 1111"],
            ["Applicant Name", "VRM", "Phone", "Date:"],
            ["24 May 2024"],
            ["person_name", "vehicle_reg", "phone"],
            False,
        ),
        RedactionCase(
            "parking_03_blue_badge_context",
            "parking",
            "parking",
            "Full Name: Peter Long\nAddress: 21 Station Road HA4 7BD\nNotes: my disabled child was with me.\nVehicle Registration: EF56 HIJ",
            ["Peter Long", "21 Station Road HA4 7BD", "EF56 HIJ"],
            ["Full Name:", "Address:", "Notes:", "Vehicle Registration:"],
            ["my disabled child was with me"],
            ["person_name", "address", "vehicle_reg"],
            False,
        ),
        RedactionCase(
            "parking_04_month_guard",
            "parking",
            "parking",
            "Date: 24 May 2024\nRegistration: GH78 KLM\nPhone: 07700 333444",
            ["GH78 KLM", "07700 333444"],
            ["Date:", "Registration:", "Phone:"],
            ["24 May 2024"],
            ["vehicle_reg", "phone"],
            False,
        ),
        RedactionCase(
            "parking_05_public_road",
            "parking",
            "parking",
            "Name: Imran Ali\nEmail: imran.ali@example.test\nLocation: High Street public bay\nPCN HT2026-8847",
            ["Imran Ali", "imran.ali@example.test", "HT2026-8847"],
            ["Name:", "Email:", "Location:", "PCN"],
            ["High Street public bay"],
            ["person_name", "email", "vehicle_reg"],
            False,
        ),
        # Complaints
        RedactionCase(
            "complaint_01_contact",
            "complaint",
            "complaint",
            "Full Name: Janet Fox\nContact Address: 8 Sample Lane UB10 1XY\nTelephone: 01895 444555\nComplaint: missed appointment",
            ["Janet Fox", "8 Sample Lane UB10 1XY", "01895 444555"],
            ["Full Name:", "Contact Address:", "Telephone:", "Complaint:"],
            ["missed appointment"],
            ["person_name", "address", "phone"],
            False,
        ),
        RedactionCase(
            "complaint_02_staff_name_free_text",
            "complaint",
            "complaint",
            "Name: Leah Morris\nI spoke to Mr Brown at the desk and he was rude.\nEmail: leah.morris@example.test",
            ["Leah Morris", "leah.morris@example.test"],
            ["Name:", "Email:"],
            ["Mr Brown", "rude"],
            ["person_name", "email"],
            False,
        ),
        RedactionCase(
            "complaint_03_case_reference",
            "complaint",
            "complaint",
            "Ref No: CR-112233\nApplicant: George Hill\nMobile: 07700 555666\nDescription: appeal not answered",
            ["George Hill", "07700 555666"],
            ["Ref No:", "Applicant:", "Mobile:", "Description:"],
            ["CR-112233", "appeal not answered"],
            ["person_name", "phone"],
            False,
        ),
        RedactionCase(
            "complaint_04_no_pii",
            "complaint",
            "complaint",
            "Hello World\nComplaint: bins were late on Monday\nDate: 3 June 2026",
            [],
            ["Complaint:", "Date:"],
            ["Hello World", "bins were late", "3 June 2026"],
            [],
            False,
        ),
        RedactionCase(
            "complaint_05_signature",
            "complaint",
            "complaint",
            "Name: Aaron Singh\nSignature: Aaron Singh\nDate: 15 July 2026",
            ["Aaron Singh", "Aaron Singh"],
            ["Name:", "Signature:", "Date:"],
            ["15 July 2026"],
            ["person_name", "signature"],
            False,
        ),
        # Waste / environment
        RedactionCase(
            "waste_01_missed_bins",
            "waste",
            "waste",
            "Reported by: Chloe Evans\nHome Address: 6 Green Walk UB7 0ZZ\nPhone: 07700 777888\nIssue: missed bins",
            ["Chloe Evans", "6 Green Walk UB7 0ZZ", "07700 777888"],
            ["Reported by:", "Home Address:", "Phone:", "Issue:"],
            ["missed bins"],
            ["person_name", "address", "phone"],
            False,
        ),
        RedactionCase(
            "waste_02_vehicle_plate",
            "waste",
            "waste",
            "Name: Ben Carter\nEmail: ben.carter@example.test\nI saw a blue van AB12 CDE dumping rubbish.",
            ["Ben Carter", "ben.carter@example.test"],
            ["Name:", "Email:"],
            ["AB12 CDE", "dumping rubbish"],
            ["person_name", "email"],
            False,
        ),
        RedactionCase(
            "waste_03_neighbour",
            "waste",
            "waste",
            "Applicant Sarah Green\nContact Number 020 8000 2222\nMy neighbour at number 14 leaves waste outside.",
            ["Sarah Green", "020 8000 2222"],
            ["Applicant", "Contact Number"],
            ["number 14", "leaves waste outside"],
            ["person_name", "phone"],
            False,
        ),
        RedactionCase(
            "waste_04_public_location",
            "waste",
            "waste",
            "Email: report.env@example.test\nLocation: High Street near station\nDate: 9 May 2026",
            ["report.env@example.test"],
            ["Email:", "Location:", "Date:"],
            ["High Street near station", "9 May 2026"],
            ["email"],
            False,
        ),
        RedactionCase(
            "waste_05_contact_address",
            "waste",
            "waste",
            "Name: Zoe Mills\nContact Address 18 Mock Avenue HA5 1AA\nTelephone 01895 123789",
            ["Zoe Mills", "18 Mock Avenue HA5 1AA", "01895 123789"],
            ["Name:", "Contact Address", "Telephone"],
            [],
            ["person_name", "address", "phone"],
            False,
        ),
        # Adult social care / medical-style
        RedactionCase(
            "adult_social_01_medical_notes",
            "adult_social_care",
            "adult_social_care",
            "Patient Name: Arthur Reed\nDOB: 11/02/1948\nNHS Number: 485 777 3456\nNotes: takes insulin and lives alone.",
            ["Arthur Reed", "11/02/1948", "485 777 3456", "takes insulin and lives alone."],
            ["Patient Name:", "DOB:", "NHS Number:", "Notes:"],
            [],
            ["person_name", "dob", "nin", "notes"],
            False,
        ),
        RedactionCase(
            "adult_social_02_allergy",
            "adult_social_care",
            "adult_social_care",
            "Full Name: Daniel Mercer\nNotes: Allergic to penicillin.\nPhone: (555) 814-2937",
            ["Daniel Mercer", "Allergic to penicillin.", "(555) 814-2937"],
            ["Full Name:", "Notes:", "Phone:"],
            [],
            ["person_name", "notes", "phone"],
            False,
        ),
        RedactionCase(
            "adult_social_03_carer",
            "adult_social_care",
            "adult_social_care",
            "Carer Name: Susan Cole\nAddress: 1 Care Road UB4 5TT\nDoctor: Demo GP\nStatus: needs assessment",
            ["Susan Cole", "1 Care Road UB4 5TT"],
            ["Carer Name:", "Address:", "Doctor:", "Status:"],
            ["Demo GP", "needs assessment"],
            ["person_name", "address"],
            False,
        ),
        RedactionCase(
            "adult_social_04_medication_free_text",
            "adult_social_care",
            "adult_social_care",
            "Name: Victor Stone\nMedication list: metformin and ramipril.\nEmail: victor.stone@example.test",
            ["Victor Stone", "victor.stone@example.test"],
            ["Name:", "Medication list:", "Email:"],
            ["metformin and ramipril"],
            ["person_name", "email"],
            False,
        ),
        RedactionCase(
            "adult_social_05_appointment_date",
            "adult_social_care",
            "adult_social_care",
            "Patient Name: Elaine Wood\nDate: 5 August 2026\nTelephone: 020 8333 4444\nType: care review",
            ["Elaine Wood", "020 8333 4444"],
            ["Patient Name:", "Date:", "Telephone:", "Type:"],
            ["5 August 2026", "care review"],
            ["person_name", "phone"],
            False,
        ),
        # Children safeguarding
        RedactionCase(
            "safeguarding_01_child",
            "children_safeguarding",
            "children_safeguarding",
            "Child Name: Emily Carter\nDOB: 03/11/2015\nAddress: 25 Willow Lane UB3 4RT\nNotes: child feels unsafe at home.",
            ["Emily Carter", "03/11/2015", "25 Willow Lane UB3 4RT", "child feels unsafe at home."],
            ["Child Name:", "DOB:", "Address:", "Notes:"],
            [],
            ["person_name", "dob", "address", "notes"],
            True,
        ),
        RedactionCase(
            "safeguarding_02_parent",
            "children_safeguarding",
            "children_safeguarding",
            "Reported by: School Safeguarding Lead\nName: Noah White\nPhone: 07700 202020\nNotes: neglect concern.",
            ["School Safeguarding Lead", "Noah White", "07700 202020", "neglect concern."],
            ["Reported by:", "Name:", "Phone:", "Notes:"],
            [],
            ["person_name", "phone", "notes"],
            True,
        ),
        RedactionCase(
            "safeguarding_03_no_colon",
            "children_safeguarding",
            "children_safeguarding",
            "Child Name Lily Adams\nHome Address 4 Orchard Close UB6 1AA\nEmergency Phone 01895 909090",
            ["Lily Adams", "4 Orchard Close UB6 1AA", "01895 909090"],
            ["Child Name", "Home Address", "Emergency Phone"],
            [],
            ["person_name", "address", "phone"],
            True,
        ),
        RedactionCase(
            "safeguarding_04_medical",
            "children_safeguarding",
            "children_safeguarding",
            "Patient Name: Kai Moore\nNHS Number: 943 476 5910\nNotes: bruising observed by teacher.",
            ["Kai Moore", "943 476 5910", "bruising observed by teacher."],
            ["Patient Name:", "NHS Number:", "Notes:"],
            [],
            ["person_name", "nin", "notes"],
            True,
        ),
        RedactionCase(
            "safeguarding_05_case_worker_boundary",
            "children_safeguarding",
            "children_safeguarding",
            "Name: Ava King\nCase Worker: Demo Officer\nStatus: urgent assessment\nEmail: safe.case@example.test",
            ["Ava King", "safe.case@example.test"],
            ["Name:", "Case Worker:", "Status:", "Email:"],
            ["Demo Officer", "urgent assessment"],
            ["person_name", "email"],
            True,
        ),
        # FOI / legal
        RedactionCase(
            "foi_legal_01_requester",
            "foi_legal",
            "foi_legal",
            "Requester Name: Oliver Grant\nEmail: oliver.grant@example.test\nDate: 1 April 2026\nRequest: copies of policy documents",
            ["Oliver Grant", "oliver.grant@example.test"],
            ["Requester Name:", "Email:", "Date:", "Request:"],
            ["1 April 2026", "copies of policy documents"],
            ["person_name", "email"],
            True,
        ),
        RedactionCase(
            "foi_legal_02_address",
            "foi_legal",
            "foi_legal",
            "Name: Fatima Noor\nAddress: 40 Legal Road UB8 8AA\nReference: SAR-445566\nDescription: subject access request",
            ["Fatima Noor", "40 Legal Road UB8 8AA"],
            ["Name:", "Address:", "Reference:", "Description:"],
            ["SAR-445566", "subject access request"],
            ["person_name", "address"],
            True,
        ),
        RedactionCase(
            "foi_legal_03_third_party",
            "foi_legal",
            "foi_legal",
            "Applicant: James Rowe\nThe complaint mentions Sarah Kent and a legal claim.\nPhone: 01895 101010",
            ["James Rowe", "01895 101010"],
            ["Applicant:", "Phone:"],
            ["Sarah Kent", "legal claim"],
            ["person_name", "phone"],
            True,
        ),
        RedactionCase(
            "foi_legal_04_signature",
            "foi_legal",
            "foi_legal",
            "Full Name: Grace Hall\nSignature: Grace Hall\nEmail Address: grace.hall@example.test",
            ["Grace Hall", "Grace Hall", "grace.hall@example.test"],
            ["Full Name:", "Signature:", "Email Address:"],
            [],
            ["person_name", "signature", "email"],
            True,
        ),
        RedactionCase(
            "foi_legal_05_deadline",
            "foi_legal",
            "foi_legal",
            "Name: Theo Scott\nContact Number: 020 8555 1212\nDeadline date: 30 May 2026\nPublic authority: Hillingdon Council",
            ["Theo Scott", "020 8555 1212"],
            ["Name:", "Contact Number:"],
            ["30 May 2026", "Hillingdon Council"],
            ["person_name", "phone"],
            True,
        ),
        # Translation / non-English extracted text
        RedactionCase(
            "translation_01_spanish_with_english_labels",
            "translation",
            "translation",
            "Full Name: Maria Garcia Lopez\nAddress: 7 Riverside Court UB8 2PQ\nTelefono: 07700 654321\nSolicitud: ayuda para alquiler",
            ["Maria Garcia Lopez", "7 Riverside Court UB8 2PQ", "07700 654321"],
            ["Full Name:", "Address:", "Telefono:"],
            ["ayuda para alquiler"],
            ["person_name", "address", "phone"],
            False,
        ),
        RedactionCase(
            "translation_02_spanish_email",
            "translation",
            "translation",
            "Solicitante: Ana Ruiz\nEmail: ana.ruiz@example.test\nFecha: 4 Mayo 2026",
            ["ana.ruiz@example.test"],
            ["Solicitante:", "Email:", "Fecha:"],
            ["Ana Ruiz", "4 Mayo 2026"],
            ["email"],
            False,
        ),
        RedactionCase(
            "translation_03_french_phone",
            "translation",
            "translation",
            "Nom: Luc Martin\nPhone: 07700 777000\nAdresse: 5 Rue Demo",
            ["07700 777000"],
            ["Nom:", "Phone:", "Adresse:"],
            ["Luc Martin", "5 Rue Demo"],
            ["phone"],
            False,
        ),
        RedactionCase(
            "translation_04_arabic_safe",
            "translation",
            "translation",
            "Hello World\nLanguage: Arabic\nRequest: translation support\nDate: 24 May 2024",
            [],
            ["Language:", "Request:", "Date:"],
            ["Hello World", "24 May 2024"],
            [],
            False,
        ),
        RedactionCase(
            "translation_05_mixed_dob",
            "translation",
            "translation",
            "Applicant: Lucia Fernandez\nDate of Birth: 12/05/1985\nEmail: lucia.f@example.test",
            ["Lucia Fernandez", "12/05/1985", "lucia.f@example.test"],
            ["Applicant:", "Date of Birth:", "Email:"],
            [],
            ["person_name", "dob", "email"],
            False,
        ),
        # Unknown / mixed
        RedactionCase(
            "unknown_01_obvious_pii",
            "unknown",
            None,
            "Name: Sam Blake\nPhone: 07700 101202\nEmail: sam.blake@example.test",
            ["Sam Blake", "07700 101202", "sam.blake@example.test"],
            ["Name:", "Phone:", "Email:"],
            [],
            ["person_name", "phone", "email"],
            True,
        ),
        RedactionCase(
            "unknown_02_safe_text",
            "unknown",
            None,
            "Hello World\nThis is a general note about bins and opening hours.\nDate: 24 May 2024",
            [],
            ["Date:"],
            ["Hello World", "opening hours", "24 May 2024"],
            [],
            True,
        ),
        RedactionCase(
            "unknown_03_bank",
            "unknown",
            None,
            "Account Number: 87654321\nSort Code: 11-22-33\nComments: test only",
            ["87654321", "11-22-33"],
            ["Account Number:", "Sort Code:", "Comments:"],
            ["test only"],
            ["bank_details"],
            True,
        ),
        RedactionCase(
            "unknown_04_national_id",
            "unknown",
            None,
            "National ID XJ-4829-1173\nOccupation: Logistics Coordinator\nDate: 24 May 2024",
            ["XJ-4829-1173"],
            ["National ID", "Occupation:", "Date:"],
            ["Logistics Coordinator", "24 May 2024"],
            ["nin"],
            True,
        ),
        RedactionCase(
            "unknown_05_foreign_handwriting_like",
            "unknown",
            None,
            "N a m e:  Kim Park\nMobile: 07700 303404\nNotes: unclear handwriting",
            ["07700 303404", "unclear handwriting"],
            ["Mobile:", "Notes:"],
            ["Kim Park"],
            ["phone", "notes"],
            True,
        ),
    ]


def _contains(text: str, value: str) -> bool:
    """Case-insensitive containment helper."""
    return value.lower() in text.lower()


def _detected_types_for_values(spans: list[dict[str, Any]], values: list[str]) -> set[str]:
    """Return detected span types whose original value contains or is contained by an expected value."""
    types: set[str] = set()
    for expected in values:
        exp = expected.lower()
        for span in spans:
            got = str(span.get("value", "")).lower()
            if got and (exp in got or got in exp):
                rtype = str(span.get("type", ""))
                types.add(rtype)
                types.add(TYPE_ALIASES.get(rtype, rtype))
    return types


def _case_review(category: str) -> bool:
    """Mirror the current category/profile review rule for text-only evaluation."""
    profiles = get_profiles_for_category(category)
    return requires_review(category, profiles)


def evaluate_case(engine: RedactionEngine, case: RedactionCase) -> dict[str, Any]:
    """Evaluate a single synthetic case."""
    profiles = get_profiles_for_category(case.category)
    allowed_types = get_allowed_types(profiles)
    spans = engine.detect_sensitive_text(case.input_text, llm_engine=None, allowed_types=allowed_types)
    redacted_text = engine.redact_text(case.input_text, spans)
    actual_review = _case_review(case.category)

    missed_values = [
        value for value in case.expected_redacted_values if _contains(redacted_text, value)
    ]
    redacted_safe_values = [
        value for value in case.expected_not_redacted_values if value and not _contains(redacted_text, value)
    ]
    redacted_labels = [
        label for label in case.expected_unredacted_labels if label and not _contains(redacted_text, label)
    ]

    detected_types = {str(span.get("type", "")) for span in spans}
    canonical_detected_types = detected_types | {TYPE_ALIASES.get(rtype, rtype) for rtype in detected_types}
    detected_types_for_values = _detected_types_for_values(spans, case.expected_redacted_values)
    missing_types = [
        rtype
        for rtype in sorted(set(case.expected_redaction_types))
        if rtype not in canonical_detected_types and rtype not in detected_types_for_values
    ]

    review_ok = actual_review == case.expected_needs_review
    passed = not missed_values and not redacted_safe_values and not redacted_labels and not missing_types and review_ok

    reasons: list[str] = []
    if missed_values:
        reasons.append(f"missed expected redactions: {missed_values}")
    if redacted_safe_values:
        reasons.append(f"redacted values expected to remain visible: {redacted_safe_values}")
    if redacted_labels:
        reasons.append(f"redacted labels/headings expected to remain visible: {redacted_labels}")
    if missing_types:
        reasons.append(f"missing expected redaction types: {missing_types}")
    if not review_ok:
        reasons.append(f"review flag mismatch: expected {case.expected_needs_review}, got {actual_review}")

    return {
        "case": case,
        "passed": passed,
        "reasons": reasons,
        "profiles": profiles,
        "allowed_types": sorted(allowed_types),
        "spans": spans,
        "redacted_text": redacted_text,
        "actual_review": actual_review,
        "missed_values": missed_values,
        "redacted_safe_values": redacted_safe_values,
        "redacted_labels": redacted_labels,
        "missing_types": missing_types,
    }


def print_result(result: dict[str, Any]) -> None:
    """Print one concise case result, expanding failures."""
    case: RedactionCase = result["case"]
    status = "PASS" if result["passed"] else "FAIL"
    print(f"{status} {case.id} [{case.category}] profiles={','.join(result['profiles'])}")
    if result["passed"]:
        return
    for reason in result["reasons"]:
        print(f"  - {reason}")
    span_summary = [
        {
            "type": span.get("type"),
            "value": span.get("value"),
            "confidence": span.get("confidence"),
            "method": span.get("method"),
        }
        for span in result["spans"]
    ]
    print(f"  input: {case.input_text!r}")
    print(f"  expected_values: {case.expected_redacted_values!r}")
    print(f"  detected_spans: {span_summary!r}")
    print(f"  redacted_output: {result['redacted_text']!r}")


def summarize(results: list[dict[str, Any]]) -> None:
    """Print aggregate metrics."""
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    expected_values = sum(len(result["case"].expected_redacted_values) for result in results)
    missed_values = sum(len(result["missed_values"]) for result in results)
    expected_labels = sum(len(result["case"].expected_unredacted_labels) for result in results)
    redacted_labels = sum(len(result["redacted_labels"]) for result in results)
    safe_values = sum(len(result["case"].expected_not_redacted_values) for result in results)
    redacted_safe_values = sum(len(result["redacted_safe_values"]) for result in results)
    review_passed = sum(
        1
        for result in results
        if result["actual_review"] == result["case"].expected_needs_review
    )

    type_expected: dict[str, int] = defaultdict(int)
    type_missing: dict[str, int] = defaultdict(int)
    for result in results:
        for rtype in set(result["case"].expected_redaction_types):
            type_expected[rtype] += 1
        for rtype in set(result["missing_types"]):
            type_missing[rtype] += 1

    overall_accuracy = passed / total if total else 0
    value_recall = (
        (expected_values - missed_values) / expected_values if expected_values else 1
    )
    label_score = (
        (expected_labels - redacted_labels) / expected_labels if expected_labels else 1
    )
    safe_value_score = (
        (safe_values - redacted_safe_values) / safe_values if safe_values else 1
    )
    review_score = review_passed / total if total else 0
    category_profile_score = review_score

    print("\nSUMMARY")
    print(f"cases: {passed}/{total} passed ({overall_accuracy:.1%})")
    print(f"overall_accuracy: {overall_accuracy:.1%}")
    print(f"value_recall: {value_recall:.1%}")
    print(f"false_negative_count: {missed_values}")
    print(f"false_positive_count: {redacted_safe_values}")
    print(f"label_preservation_score: {label_score:.1%}")
    print(f"safe_value_preservation_score: {safe_value_score:.1%}")
    print(f"category_profile_score: {category_profile_score:.1%}")
    print(f"review_flag_score: {review_score:.1%}")

    print("\nRECALL BY TYPE")
    for rtype in sorted(type_expected):
        expected = type_expected[rtype]
        missing = type_missing.get(rtype, 0)
        recall = (expected - missing) / expected if expected else 1
        print(f"{rtype}: {expected - missing}/{expected} ({recall:.1%})")

    failed = [result["case"].id for result in results if not result["passed"]]
    print("\nFAILED CASES")
    print(", ".join(failed) if failed else "none")

    if overall_accuracy < 0.85:
        print("\nACCEPTANCE: FAIL - below 85% overall case accuracy")
    else:
        print("\nACCEPTANCE: PASS - at least 85% overall case accuracy")


def main() -> int:
    """Run all synthetic redaction cases."""
    cases = build_cases()
    if len(cases) != 50:
        raise RuntimeError(f"Expected 50 cases, found {len(cases)}")

    engine = RedactionEngine()
    results = [evaluate_case(engine, case) for case in cases]
    for result in results:
        print_result(result)
    summarize(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
