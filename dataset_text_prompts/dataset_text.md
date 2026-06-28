# Synthetiq Redact Image Dataset Text Prompts

All documents below are synthetic. Names, addresses, references, phone numbers,
emails, NHS numbers, and NI numbers are fake training data.

For each document: copy the full block, including the letter text and image
generation prompt, into ChatGPT image generation. Save the 10 outputs in a
folder named after the document id.

---

## DOC-001 - FOI Request

### Ground Truth Letter Text

```
Northbridge Borough Council
Information Governance Team
Riverside House, Civic Square, Northbridge NB1 4ZZ

Freedom of Information Request
Reference: FOI-2026-0418
Date received: 14 June 2026

Requester name: Avery Demo
Email: avery.demo@example.invalid
Phone: 07123 456 801
Postal address: 18 Placeholder Road, Northbridge NB2 7QA

Dear Information Governance Team,

Please provide copies of policy documents, guidance notes, and internal review
minutes relating to parking enforcement grace periods between January 2025 and
May 2026. I am particularly interested in any guidance sent to civil enforcement
officers about medical appointments and blue badge holders.

Please send the response by email if possible.

Signed,
Avery Demo
```

### Answer Key

```json
{
  "document_id": "DOC-001",
  "document_type": "foi_request",
  "sensitive_items": [
    {"type": "person_name", "value": "Avery Demo", "expected_action": "redact_value"},
    {"type": "email", "value": "avery.demo@example.invalid", "expected_action": "redact_value"},
    {"type": "phone", "value": "07123 456 801", "expected_action": "redact_value"},
    {"type": "address", "value": "18 Placeholder Road, Northbridge NB2 7QA", "expected_action": "redact_value"},
    {"type": "council_ref", "value": "FOI-2026-0418", "expected_action": "review_or_redact"},
    {"type": "signature", "value": "Avery Demo", "expected_action": "review"}
  ]
}
```

### Image Generation Prompt

Generate 10 different realistic images of the same UK council FOI request letter above. Each image must show the exact letter text as a physical document, not a clean digital screenshot. Do not add real personal data, real logos, QR codes, barcodes, watermarks, or extra names.

Make the 10 outputs varied:
1. Neat blue-ink handwriting on lined paper, slight left tilt.
2. Black ballpoint handwriting on plain A4, mild scanner shadow.
3. Mixed typed header with handwritten body, slightly skewed scan.
4. Messy but legible handwriting with uneven line spacing.
5. Phone photo on a desk with soft shadow and small perspective angle.
6. Faint pencil-like handwriting with low contrast but still readable.
7. Older photocopy look with grey background and minor blur.
8. Compact handwriting with narrow margins and slight page curl.
9. Form-like layout with labels typed and values handwritten.
10. Rushed handwriting, a few crossed-out non-sensitive words, all PII still readable.

Keep the content legible enough for OCR. Preserve line breaks where possible. The answer key values must appear exactly as written.

---

## DOC-002 - Subject Access Request

### Ground Truth Letter Text

```
Eastmere District Council
Data Protection Office
Town Hall Annex, Market Street, Eastmere EM3 1TR

Subject Access Request
Case reference: SAR-26-7782
Date: 18 June 2026

Full name: Morgan Sample
Date of birth: 09/11/1984
National Insurance number: QQ 12 34 56 C
Email: morgan.sample@example.invalid
Current address: Flat 4, 99 Sample Street, Eastmere EM4 8ZZ
Previous address: 42 Fiction Close, Eastmere EM2 6LT

I am requesting copies of personal information held by the housing repairs team,
including call notes, repair appointments, contractor comments, complaint notes,
and any internal emails that mention my damp and mould report.

Please confirm receipt of this request in writing.

Signature: Morgan Sample
```

### Answer Key

```json
{
  "document_id": "DOC-002",
  "document_type": "sar_request",
  "sensitive_items": [
    {"type": "person_name", "value": "Morgan Sample", "expected_action": "redact_value"},
    {"type": "dob", "value": "09/11/1984", "expected_action": "redact_value"},
    {"type": "nin", "value": "QQ 12 34 56 C", "expected_action": "redact_value"},
    {"type": "email", "value": "morgan.sample@example.invalid", "expected_action": "redact_value"},
    {"type": "address", "value": "Flat 4, 99 Sample Street, Eastmere EM4 8ZZ", "expected_action": "redact_value"},
    {"type": "address", "value": "42 Fiction Close, Eastmere EM2 6LT", "expected_action": "redact_value"},
    {"type": "case_reference", "value": "SAR-26-7782", "expected_action": "review_or_redact"},
    {"type": "signature", "value": "Morgan Sample", "expected_action": "review"}
  ]
}
```

### Image Generation Prompt

Generate 10 realistic handwritten/scanned document images of the same subject access request above. The text must be copied exactly where possible. Do not invent extra personal details.

Make these variations:
1. Formal handwritten letter on white A4 with neat block capitals for labels.
2. Blue ink cursive values beside typed labels.
3. Slightly smudged black pen, still readable.
4. Phone scan with uneven lighting, top-left shadow.
5. Cropped page edge but all text visible.
6. Handwriting gets smaller near the bottom.
7. Mild coffee-ring mark away from text.
8. High-contrast photocopy with speckle noise.
9. Mixed print and cursive handwriting.
10. Page rotated about 2 degrees with visible paper texture.

The PII values in the answer key must remain readable and present.

---

## DOC-003 - Housing Repair Complaint

### Ground Truth Letter Text

```
Westhaven Council Housing Repairs
Tenant Services Centre
Repair complaint note
Repair reference: HSG-44291-WH

Tenant: Taylor Fiction
Phone: 07000 118 245
Email: taylor.fiction@example.invalid
Property address: 20 Fiction Avenue, Westhaven WH5 2PX
Preferred contact time: after 4pm

I reported damp on the bedroom wall on 03 May 2026 and again on 21 May 2026.
The contractor attended but did not remove the damaged plaster. My child has
been coughing at night and the room smells strongly of mould after rain.

I need the council to inspect the wall, repair the leaking window frame, and
confirm whether temporary accommodation is available if the bedroom is unsafe.

Tenant signature: Taylor Fiction
```

### Answer Key

```json
{
  "document_id": "DOC-003",
  "document_type": "housing_repair_complaint",
  "sensitive_items": [
    {"type": "person_name", "value": "Taylor Fiction", "expected_action": "redact_value"},
    {"type": "phone", "value": "07000 118 245", "expected_action": "redact_value"},
    {"type": "email", "value": "taylor.fiction@example.invalid", "expected_action": "redact_value"},
    {"type": "address", "value": "20 Fiction Avenue, Westhaven WH5 2PX", "expected_action": "redact_value"},
    {"type": "case_reference", "value": "HSG-44291-WH", "expected_action": "review_or_redact"},
    {"type": "medical_details", "value": "My child has been coughing at night", "expected_action": "review"},
    {"type": "signature", "value": "Taylor Fiction", "expected_action": "review"}
  ]
}
```

### Image Generation Prompt

Generate 10 different realistic document images of the housing repair complaint above. Make it look like council casework paperwork or a resident complaint letter. Do not use real names or real council branding.

Variation plan:
1. Resident handwritten complaint on plain A4, black pen.
2. Council repair note form with typed labels and handwritten values.
3. Messy handwriting, damp stain in margin away from text.
4. Slightly blurred phone photo, still OCR-readable.
5. Folded paper with crease across the page but text remains visible.
6. Blue ink, strong right slant.
7. Large handwriting with uneven baselines.
8. Low-contrast photocopy.
9. Neat print handwriting with boxed field labels.
10. Page shadow and slight perspective distortion.

Keep all answer-key sensitive values visible and legible.

---

## DOC-004 - Parking Appeal

### Ground Truth Letter Text

```
Southgate Parking Services
Penalty Charge Notice Appeal

PCN number: SG98765432
Vehicle registration: AB12 CDE
Applicant: Jordan Example
Address: 7 Demo Terrace, Southgate SG1 9QQ
Mobile: 07111 222 333
Email: jordan.example@example.invalid

I am appealing this penalty because the pay and display machine was not working.
I tried to pay by card at 09:18 and again at 09:24. The machine screen displayed
"temporarily unavailable". I left a handwritten note in the windscreen and moved
the vehicle as soon as I returned from the chemist.

Please review the CEO photographs and machine fault logs for 11 June 2026.

Signed: Jordan Example
```

### Answer Key

```json
{
  "document_id": "DOC-004",
  "document_type": "parking_appeal",
  "sensitive_items": [
    {"type": "case_reference", "value": "SG98765432", "expected_action": "review_or_redact"},
    {"type": "vehicle_reg", "value": "AB12 CDE", "expected_action": "redact_value"},
    {"type": "person_name", "value": "Jordan Example", "expected_action": "redact_value"},
    {"type": "address", "value": "7 Demo Terrace, Southgate SG1 9QQ", "expected_action": "redact_value"},
    {"type": "phone", "value": "07111 222 333", "expected_action": "redact_value"},
    {"type": "email", "value": "jordan.example@example.invalid", "expected_action": "redact_value"},
    {"type": "signature", "value": "Jordan Example", "expected_action": "review"}
  ]
}
```

### Image Generation Prompt

Generate 10 realistic images of the parking appeal above. It should look like a scanned or photographed handwritten appeal form or letter.

Create these 10 visual styles:
1. Clean handwritten appeal on white A4.
2. Parking appeal form with handwritten field values.
3. Black pen with pressure variation.
4. Blue pen with slightly twisted writing.
5. Phone photo on a car dashboard, no real car plate visible except the fake value in the text.
6. Slight skew and scanner edge shadow.
7. Compact writing with narrow line spacing.
8. Older photocopied page with speckles.
9. Mixed uppercase and lowercase handwriting.
10. Light blur at page corners but center text readable.

Do not change the PCN number, vehicle registration, name, address, phone, or email.

---

## DOC-005 - Social Care Visit Note

### Ground Truth Letter Text

```
Adult Social Care Visit Note
Northfield Council
Case ID: ASC-60291
Visit date: 17 June 2026

Resident: Riley Test
NHS number: 485 777 3456
Date of birth: 22/02/1949
Address: 31 Example Gardens, Northfield NF8 3AA
Emergency contact: Casey Test, 07999 444 221

Worker note:
Resident said she has missed two medication doses this week and felt dizzy on
Monday morning. She reported anxiety about opening post and asked for help with
the blue envelope from the benefits office. Kitchen floor was clear. No trip
hazards seen during the visit.

Follow-up requested: medication prompt call and benefits advice referral.
Worker initials: LT
```

### Answer Key

```json
{
  "document_id": "DOC-005",
  "document_type": "social_care_visit_note",
  "sensitive_items": [
    {"type": "person_name", "value": "Riley Test", "expected_action": "redact_value"},
    {"type": "nhs_number", "value": "485 777 3456", "expected_action": "redact_value"},
    {"type": "dob", "value": "22/02/1949", "expected_action": "redact_value"},
    {"type": "address", "value": "31 Example Gardens, Northfield NF8 3AA", "expected_action": "redact_value"},
    {"type": "person_name", "value": "Casey Test", "expected_action": "redact_value"},
    {"type": "phone", "value": "07999 444 221", "expected_action": "redact_value"},
    {"type": "case_reference", "value": "ASC-60291", "expected_action": "review_or_redact"},
    {"type": "medical_details", "value": "missed two medication doses this week and felt dizzy", "expected_action": "review"}
  ]
}
```

### Image Generation Prompt

Generate 10 different realistic images of this adult social care visit note. It should look handwritten by a caseworker on a council note sheet. Do not use real people or real council logos.

Variations:
1. Clipboard-style form, handwritten notes in black ink.
2. Blue pen cursive, neat but slightly slanted.
3. Rushed caseworker handwriting with abbreviations exactly as shown.
4. Low-light phone photo, still readable.
5. Scanned page with grey background.
6. Slight paper curl and shadow on right edge.
7. Printed labels with handwritten values.
8. Smaller handwriting in the worker note section.
9. Mild blur and compression artefacts.
10. Fold line through blank area, no text hidden.

The medical sentence must remain readable enough for review training.

---

## DOC-006 - Safeguarding-Style Note

### Ground Truth Letter Text

```
Children and Families Contact Note
Safeguarding style training example
Council reference: CF-TRAIN-2606

Child name: Sam Demo
Child age: 9
Parent / carer: Robin Demo
Home address: 44 Training Lane, Lakeside LS2 5XX
School: Lakeside Primary School
Contact phone: 07000 555 919

Summary of concern:
School reported that Sam arrived late three times this week and said there was
no breakfast at home on Tuesday. Parent said the family had a broken boiler and
was waiting for a repair appointment. No immediate injury was reported.

Action:
Call parent, check housing repair status, and offer early help referral.

Recorded by: Worker AB
```

### Answer Key

```json
{
  "document_id": "DOC-006",
  "document_type": "safeguarding_style_note",
  "sensitive_items": [
    {"type": "child_name", "value": "Sam Demo", "expected_action": "redact_value"},
    {"type": "child_age", "value": "9", "expected_action": "redact_value"},
    {"type": "person_name", "value": "Robin Demo", "expected_action": "redact_value"},
    {"type": "address", "value": "44 Training Lane, Lakeside LS2 5XX", "expected_action": "redact_value"},
    {"type": "school", "value": "Lakeside Primary School", "expected_action": "review_or_redact"},
    {"type": "phone", "value": "07000 555 919", "expected_action": "redact_value"},
    {"type": "case_reference", "value": "CF-TRAIN-2606", "expected_action": "review_or_redact"},
    {"type": "safeguarding_context", "value": "no breakfast at home on Tuesday", "expected_action": "review"}
  ]
}
```

### Image Generation Prompt

Generate 10 realistic handwritten/scanned images of this safeguarding-style contact note. This is synthetic training data only. Do not make it graphic, sensational, or use real people. Keep it like ordinary council casework notes.

Variation list:
1. Caseworker handwritten contact note on a blank form.
2. Typed headings, handwritten values.
3. Messy but legible handwriting, slight right tilt.
4. Phone photo with desk background and soft shadow.
5. Scanner image with mild skew.
6. Compact handwriting, cramped summary section.
7. Blue ink, uneven pressure.
8. Black ink, larger writing for field labels.
9. Low contrast photocopy with speckle noise.
10. Slightly wrinkled paper, all sensitive values readable.

Preserve every answer-key value exactly.

---

## DOC-007 - Homelessness Prevention Note

### Ground Truth Letter Text

```
Homelessness Prevention Team
Local Housing Options
Triage note
Reference: HPT-77104

Applicant: Casey Fiction
DOB: 05/06/1992
Phone number: 07888 120 120
Email address: casey.fiction@example.invalid
Current address: Room 3, 6 Sample House, Bridge Road, Hilltown HT3 4AB

Reason for contact:
Applicant states they have been asked to leave by a friend by 30 June 2026.
They are sleeping on the sofa and have one suitcase. Applicant said they cannot
return to their previous address because of a relationship breakdown.

Immediate action:
Book prevention interview, request proof of income, and provide emergency
accommodation advice if no safe option remains.
```

### Answer Key

```json
{
  "document_id": "DOC-007",
  "document_type": "homelessness_prevention_note",
  "sensitive_items": [
    {"type": "person_name", "value": "Casey Fiction", "expected_action": "redact_value"},
    {"type": "dob", "value": "05/06/1992", "expected_action": "redact_value"},
    {"type": "phone", "value": "07888 120 120", "expected_action": "redact_value"},
    {"type": "email", "value": "casey.fiction@example.invalid", "expected_action": "redact_value"},
    {"type": "address", "value": "Room 3, 6 Sample House, Bridge Road, Hilltown HT3 4AB", "expected_action": "redact_value"},
    {"type": "case_reference", "value": "HPT-77104", "expected_action": "review_or_redact"},
    {"type": "social_care_context", "value": "sleeping on the sofa and have one suitcase", "expected_action": "review"}
  ]
}
```

### Image Generation Prompt

Generate 10 realistic images of the homelessness prevention triage note above. Make each one look like a different scanned or photographed council note. Do not use real council branding or real personal data.

Variations:
1. Handwritten triage sheet with printed field labels.
2. Plain A4 letter, blue pen, slight left slant.
3. Black pen, rushed handwriting.
4. Phone photo, page on a wooden desk.
5. Scanner skew with faint grey background.
6. Folded paper with crease away from key text.
7. Uneven margins and variable line spacing.
8. Low contrast pencil-like writing.
9. Neat block handwriting.
10. Mixed typed header and handwritten body.

Keep the reference, applicant name, DOB, phone, email, and address readable.

---

## DOC-008 - Council Tax Support Form

### Ground Truth Letter Text

```
Council Tax Support Review
Benefits Service
Review ID: CTS-2026-8841

Claimant name: Jamie Placeholder
National Insurance number: QQ 98 76 54 A
Date of birth: 30/01/1978
Address: 15 Mockingbird Court, Fairford FF9 1ZZ
Email: jamie.placeholder@example.invalid
Telephone: 07123 999 000

Change reported:
Claimant started part-time work on 10 June 2026. Weekly hours are 14. Employer
is Example Supplies Ltd. Claimant says first wage slip will be available at the
end of the month.

Evidence requested:
Two wage slips, updated rent statement, and bank statement covering June 2026.

Signature: Jamie Placeholder
```

### Answer Key

```json
{
  "document_id": "DOC-008",
  "document_type": "council_tax_support_form",
  "sensitive_items": [
    {"type": "person_name", "value": "Jamie Placeholder", "expected_action": "redact_value"},
    {"type": "nin", "value": "QQ 98 76 54 A", "expected_action": "redact_value"},
    {"type": "dob", "value": "30/01/1978", "expected_action": "redact_value"},
    {"type": "address", "value": "15 Mockingbird Court, Fairford FF9 1ZZ", "expected_action": "redact_value"},
    {"type": "email", "value": "jamie.placeholder@example.invalid", "expected_action": "redact_value"},
    {"type": "phone", "value": "07123 999 000", "expected_action": "redact_value"},
    {"type": "case_reference", "value": "CTS-2026-8841", "expected_action": "review_or_redact"},
    {"type": "signature", "value": "Jamie Placeholder", "expected_action": "review"}
  ]
}
```

### Image Generation Prompt

Generate 10 different realistic images of this council tax support review form. It should look like synthetic local authority paperwork with handwritten values and notes.

10 variations:
1. Typed form labels, handwritten values, clean scan.
2. Entire page handwritten in neat black ink.
3. Blue pen, slightly twisted writing angle.
4. Low-contrast photocopy, readable text.
5. Phone photo with mild perspective distortion.
6. Page has a fold line and small shadow near bottom.
7. Compact handwriting in the change reported section.
8. Larger block capitals for field values.
9. Slight blur and paper texture.
10. Rushed handwriting with one crossed-out non-sensitive word.

Do not alter the fake NI number, DOB, address, email, phone, review ID, or signature name.

