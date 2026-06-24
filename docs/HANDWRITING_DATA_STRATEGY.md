# Handwriting Data Strategy

Use three layers of handwriting data.

## Public Datasets

- IAM Handwriting Database: useful English handwriting benchmark; non-commercial research restrictions need legal review.
- CVL Database: English and German handwriting from many writers; non-commercial restrictions need legal review.
- NIST Special Database 19: handprinted forms and characters; useful for block writing and forms.
- READ/HTR historical datasets: useful stress tests but less representative of modern council documents.

## Synthetic Data

Use the local generator in `backend/evaluation/generate_handwritten_forms.py` as the baseline.

Expand it to generate:

- FOI/SAR letters.
- Complaint forms.
- Housing repair notes.
- Parking appeals.
- Adult social-care notes.
- Safeguarding referral style documents.
- Mixed typed and handwritten pages.

Each generated document should include ground-truth JSON with all fields and redaction targets.

Add degradations:

- Blur, shadow, skew, folds, camera angle, low contrast, ruled paper, ink colour, stamps, crossings-out, and margin notes.

## AI-Generated Images

AI-generated handwriting may be used for augmentation only.

Allowed:

- Generate fake handwritten council-style documents with fake personal data.
- Store prompt, settings, expected ground truth, and generated file hash.
- Use generated images to stress-test layout and handwriting variety.

Not allowed:

- Do not use generated data as the only reliability proof.
- Do not imitate a real person's handwriting.
- Do not send real council documents to external image-generation or vision APIs.

Prompt pattern:

```text
Generate a scanned A4 handwritten UK council FOI/SAR form using fake personal data only. Include fields for name, address, phone, email, DOB, case reference, and a short sensitive note. Make handwriting messy but readable. Add mild skew, paper folds, shadows, and blue pen ink.
```

## Consented Fake Council Dataset

Recruit volunteers to handwrite fake documents using fake identities only.

Include:

- Fake names, addresses, NHS-style numbers, NI-style numbers, case references, medical notes, housing notes, social-care notes, and safeguarding references.
- Different pens, paper, scans, phone photos, blur, folds, shadows, crossings-out, and messy writing.
- Consent records and licence terms for project testing.
- Train/dev/test split with writer separation.

