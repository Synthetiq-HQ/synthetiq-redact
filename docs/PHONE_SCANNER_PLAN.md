# Phone Scanner Plan

Synthetiq Redact should eventually support a phone-as-camera workflow without turning the product into a cloud service. The laptop or council workstation remains the processing device. The phone only captures pages and transfers them locally.

## Goals

- Let a phone act as a high-quality scanner for paper documents.
- Keep OCR, vision checking, redaction, review, export, and audit on the laptop.
- Avoid cloud upload for real documents.
- Make transfer obvious and short-lived, so staff do not accidentally expose documents.

## Mode 1: Same-Network Phone Scanner

The laptop starts a temporary local scanner session and displays a pairing code or QR code. The phone joins over the same local network, captures images, and uploads them to the laptop.

Flow:

1. User opens `Phone scanner` in the desktop web app.
2. Laptop creates a short-lived pairing session with a random code.
3. Phone scans the QR code or enters the pairing code.
4. Phone captures one or more pages.
5. Phone uploads images directly to the laptop over the local network.
6. Laptop creates a document, renders page images, and runs OCR/redaction/vision locally.
7. Phone deletes temporary captures unless the user explicitly saves them.

Security rules:

- No cloud upload.
- Pairing code expires quickly, for example after 5 minutes.
- Session accepts uploads only from the paired phone.
- Transfer should use HTTPS where feasible. For local development, show a clear insecure-local warning if plain HTTP is used.
- The laptop should display the paired device name and allow immediate disconnect.
- Uploaded images go through the same validation, malware/quarantine hook, size limits, and audit logging as normal uploads.
- Phone should not keep documents after transfer unless the user explicitly saves them.

Open questions:

- Whether councils will allow local-network device pairing on managed Wi-Fi.
- How to handle HTTPS certificates on private local networks without making setup painful.
- Whether the phone app should be native iOS/Android or a PWA first.

## Mode 2: Wired Phone Scanner

The phone connects to the laptop over USB or another trusted local channel where feasible. This is useful when council Wi-Fi blocks device-to-device local networking.

Possible approaches:

- Native companion app transfers images over a USB-supported local channel.
- The phone saves captures into a watched import folder exposed through standard device file transfer.
- The desktop app imports from an attached device after explicit user selection.

Security rules:

- No cloud upload.
- Laptop remains the processing device.
- The phone app stores captures only in temporary app storage by default.
- Transfer requires an explicit user action on both laptop and phone.
- Imported files use the same validation, size limits, and audit logging as normal uploads.

Open questions:

- iOS USB transfer APIs are more restricted than Android, so feasibility needs a prototype.
- Managed council devices may block trusted-device prompts or local companion apps.
- A simple PWA/LAN mode may deliver value earlier than a wired native mode.

## First Prototype Scope

Do not build this until the desktop redaction workflow is stable.

When ready, prototype only:

- Laptop-generated pairing code.
- Same-network phone capture page.
- Multi-page capture with retake/reorder/delete.
- Local upload to laptop.
- Automatic creation of a multi-page document in the existing editor.
- Clear transfer-complete screen on phone.
- Automatic phone-side temporary deletion.

Do not include:

- Cloud sync.
- User accounts on the phone.
- Remote council SaaS.
- Background uploads.
- Permanent phone-side document library.

## Acceptance Criteria

- A user can scan 3 to 10 pages from a phone into the laptop editor.
- No document leaves the local network.
- Pairing expires automatically.
- The laptop audit log records phone scanner import events.
- Phone temporary files are deleted after successful transfer.
- Failed transfers leave a clear retry path and do not create partial hidden documents.
