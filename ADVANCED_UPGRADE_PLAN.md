# Synthetiq Redact — Advanced v2.0 Upgrade Plan

**Target:** Transform the current hackathon prototype into a production-grade, monetizable document redaction platform.

**Philosophy:** Keep the local-first, privacy-first DNA. Make it council-ready, enterprise-grade, and commercially viable.

---

## 1. EXECUTIVE SUMMARY

Current state: Hackathon MVP serving 300+ users. Solid OCR + regex + spaCy pipeline with basic UI.

Target state: Full document processing platform with smart AI, human review workflows, batch automation, role-based security, and a monetizable tier structure.

**Estimated effort:** 6-8 weeks for v2.0 core, 12 weeks for full enterprise feature set.

---

## 2. CURRENT ARCHITECTURE (What We Have)

```
Backend:    FastAPI + SQLAlchemy + SQLite
OCR:        EasyOCR (local)
NER:        spaCy en_core_web_sm + custom regex
LLM:        Ollama/Qwen (optional local)
Translation: MarianMT Helsinki-NLP (local)
Frontend:   React + Vite + Tailwind
Mobile:     Flutter (experimental)
Outputs:    PNG redacted, mask overlay, TXT, JSON, DOCX
```

**Strengths to preserve:**
- Local-first, no cloud APIs required
- Clean per-document output folders
- Audit trail in SQLite
- UK-specific PII patterns (NHS, NIN, council refs)
- Handwriting safety pass
- Category-specific redaction profiles

---

## 3. UPGRADE PHASES

### Phase 1: AI Stack Upgrade (Week 1-2)
**Goal:** Dramatically improve accuracy and reduce "human review required" flags.

#### 3.1 OCR Engine Upgrade
**Current:** EasyOCR (weak on handwriting, no layout detection)
**Upgrade:** Multi-engine architecture with primary/fallback

```python
# New engine: PaddleOCR or DocTR
# PaddleOCR gives us:
# - Better accuracy on messy docs
# - Table/structure detection
# - Layout analysis (header, body, footer)
# - Angle classification for rotated docs
# - 80+ languages support

# Architecture change:
class OCREngineManager:
    def __init__(self):
        self.primary = PaddleOCREngine()   # New default
        self.fallback = EasyOCREngine()    # Keep as backup
        self.layout = LayoutAnalyzer()     # NEW: Structure detection
        
    def extract(self, image_path):
        # Try PaddleOCR first
        result = self.primary.extract(image_path)
        confidence = result["average_confidence"]
        
        # Fallback if confidence < 0.7
        if confidence < 0.7:
            result = self.fallback.extract(image_path)
            result["engine_used"] = "easyocr_fallback"
        
        # NEW: Detect document regions
        layout = self.layout.analyze(image_path)
        result["regions"] = layout  # header, body, footer, signature, etc.
        
        return result
```

**Why PaddleOCR:**
- 4x better on handwritten text than EasyOCR
- Built-in text direction classification
- Supports recognition of rotated text
- Can detect tables and structured forms
- Active community, well-maintained

#### 3.2 NER / PII Detection Upgrade
**Current:** spaCy + regex only
**Upgrade:** Tiered detection with fine-tuned models

```python
class PII Detection Pipeline:
    Tier 0: Field-label detection (current, keep)          [0.95 conf]
    Tier 1: Fine-tuned BERT for UK gov PII (NEW)           [0.92 conf]
    Tier 2: Layout-aware detection using document regions    [0.88 conf]
    Tier 3: LLM (Qwen/Ollama) for context-aware detection   [0.82 conf]
    Tier 4: Regex patterns (current, keep as fallback)       [0.85 conf]
    Tier 5: spaCy NER (current, lowest priority)           [0.65 conf]
```

**New model to add:**
- Fine-tune `dslim/bert-base-NER` or `Jean-Baptiste/roberta-large-ner-english` on UK-specific entities:
  - NHS numbers (10 digits, checksum)
  - National Insurance numbers (AB123456C format)
  - UK postcodes (complex regex)
  - Council tax references
  - Parking PCN numbers
  - UTR (Unique Taxpayer Reference)
  - Driving licence numbers

**Training data:** Can be synthetic — generate fake documents with known PII, train model to detect them.

#### 3.3 Document Classification Upgrade
**Current:** Keyword matching + optional LLM
**Upgrade:** LayoutLMv3 or Donut model

```python
class DocumentClassifier:
    def __init__(self):
        # LayoutLMv3 understands BOTH text AND visual layout
        self.model = LayoutLMv3ForSequenceClassification.from_pretrained(
            "microsoft/layoutlmv3-base"
        )
        
    def classify(self, image_path, ocr_result):
        # Uses text positions on page, not just words
        # Can distinguish "housing complaint" from "council tax" 
        # even if keywords overlap, by understanding form structure
        
    def detect_document_type(self, image_path):
        # NEW: Is it a form, letter, email printout, handwritten note?
        # Different processing paths for each
```

#### 3.4 Handwriting Transcription Upgrade
**Current:** EasyOCR baseline + optional MLX-VLM (Apple Silicon only)
**Upgrade:** Full TrOCR or Paraformer integration

```python
class HandwritingEngine:
    def __init__(self):
        self.trocr = TrOCRProcessor()  # Microsoft TrOCR
        self.vlm = VLMTranscription()  # Keep MLX-VLM as option
        
    def transcribe(self, image_path, ocr_result):
        confidence = ocr_result["average_confidence"]
        
        if confidence < 0.75:
            # Handwriting detected — use TrOCR
            result = self.trocr.transcribe(image_path)
            return result
        
        return ocr_result  # Typed text, OCR is fine
```

**TrOCR advantages:**
- End-to-end handwriting recognition
- No need for character segmentation
- Handles cursive writing
- Works on CPU (slower but functional)

---

### Phase 2: Smart Redaction Engine (Week 2-3)
**Goal:** Context-aware, role-based, learning redaction system.

#### 2.1 Partial Redaction System
**Current:** All-or-nothing — entire value is blacked out
**Upgrade:** Configurable partial masking

```python
REDACTION_POLICIES = {
    "phone": {
        "mode": "partial",
        "pattern": "XXX-XXX-{last4}",
        "example": "07700-900-123 → XXX-XXX-0123"
    },
    "email": {
        "mode": "partial", 
        "pattern": "{first2}***@{domain}",
        "example": "john.smith@email.com → jo***@email.com"
    },
    "address": {
        "mode": "partial",
        "pattern": "{street}, [REDACTED-town], {postcode}",
        "example": "123 Baker St, London, NW1 → 123 Baker St, [REDACTED], NW1"
    },
    "nin": {
        "mode": "full",  # Always fully redact
    },
    "nhs_number": {
        "mode": "full",
    }
}
```

#### 2.2 Role-Based Visibility
**New feature:** Different users see different redaction levels.

```python
class RoleBasedRedaction:
    ROLES = {
        "caseworker": {
            # Can see partial redactions
            "phone": "partial",
            "email": "partial", 
            "address": "partial",
            "person_name": "none",  # Caseworker needs names
        },
        "public_facing": {
            # Full redaction for FOI responses
            "phone": "full",
            "email": "full",
            "address": "full",
            "person_name": "full",
        },
        "auditor": {
            # Can see everything (for audit purposes)
            "all": "none",
        }
    }
```

#### 2.3 Document-Type Profiles (Enhanced)
**Current:** Static profiles per category
**Upgrade:** Dynamic profile builder

```python
class RedactionProfileBuilder:
    def build_profile(self, document_type, sensitivity_level="standard"):
        base = self.BASE_PROFILES[document_type]
        
        if sensitivity_level == "high":
            # Add extra fields for safeguarding/foi
            base.add("medical_details")
            base.add("notes")
            base.add("signature")
            
        if sensitivity_level == "public_foi":
            # Strip everything for public release
            base = {"person_name", "address", "phone", "email", "nin", "nhs_number"}
            
        return base
```

#### 2.4 Pattern Learning (Feedback Loop)
**New feature:** When human corrects a redaction, system learns.

```python
class RedactionLearner:
    def __init__(self, db):
        self.db = db
        
    def record_correction(self, doc_id, redaction_id, action, user_id):
        """
        action: "approve", "reject", "expand", "shrink", "add_type"
        """
        correction = CorrectionLog(
            document_id=doc_id,
            redaction_id=redaction_id,
            action=action,
            user_id=user_id,
            timestamp=datetime.now()
        )
        self.db.add(correction)
        
    def get_learned_patterns(self, redaction_type, time_window_days=30):
        """Get patterns that humans frequently correct."""
        # Query corrections in last 30 days
        # If humans keep expanding "phone" redactions by 2 chars on average,
        # adjust default padding
        
    def apply_learned_adjustments(self, redactions):
        """Adjust redaction boxes based on historical corrections."""
        for red in redactions:
            adjustment = self.get_adjustment(red["type"])
            red["padding"] += adjustment
```

#### 2.5 Table/Form Structure Preservation
**New feature:** Redact values inside tables without destroying table structure.

```python
class TableRedaction:
    def redact_table(self, image, table_regions, redactions):
        """
        Instead of black rectangles, replace cell text with [REDACTED]
        while preserving table grid lines and structure.
        """
        for region in table_regions:
            cell = self.find_cell_for_redaction(region, redactions)
            if cell:
                # White-out cell background
                # Draw [REDACTED-{type}] centered in cell
                # Keep border lines intact
                self.redact_cell_preserving_structure(cell)
```

---

### Phase 3: Human Review Studio (Week 3-4)
**Goal:** Professional review interface that councils will actually pay for.

#### 3.1 Split-Screen Review UI
```
┌─────────────────────────────────────────────────────────────┐
│  Document #4821                    [Approve All] [Export]    │
├──────────────────────────┬──────────────────────────────────┤
│                          │  REDACTION REVIEW PANEL          │
│   ORIGINAL DOCUMENT      │  ┌────────────────────────────┐  │
│                          │  │ 📍 Person Name             │  │
│   [Image with           │  │ Value: "Daniel Mercer"     │  │
│    redaction boxes]     │  │ Confidence: 0.95 ✅         │  │
│                          │  │ [✓ Approve] [✗ Reject]   │  │
│   Click any box to       │  │ [↔ Adjust Box] [Change Type│  │
│   select for review     │  └────────────────────────────┘  │
│                          │  ┌────────────────────────────┐  │
│                          │  │ 📍 Address                 │  │
│                          │  │ Value: "123 Baker St"      │  │
│                          │  │ Confidence: 0.78 ⚠️         │  │
│                          │  │ [✓ Approve] [✗ Reject]   │  │
│                          │  │ [↔ Adjust] [Flag Review] │  │
│                          │  └────────────────────────────┘  │
│                          │                                   │
│   [🔍 Zoom] [📐 Measure] │  Confidence Heatmap:            │
│   [↩ Undo] [↪ Redo]      │  🟢 12 high | 🟡 5 medium | 🔴 2│
├──────────────────────────┴──────────────────────────────────┤
│  Status: 17/19 approved | 2 pending review | Auto-save ON   │
└─────────────────────────────────────────────────────────────┘
```

**Frontend components to add:**
- `ReviewStudio.jsx` — main review interface
- `RedactionInspector.jsx` — per-redaction approval panel
- `ConfidenceHeatmap.jsx` — visual overlay of confidence levels
- `DocumentCompare.jsx` — original vs redacted slider comparison
- `ReviewQueue.jsx` — list of docs awaiting review with SLA timers

#### 3.2 Confidence Heatmap Overlay
```javascript
// Render confidence as color-coded overlay
function ConfidenceOverlay({ redactions }) {
  return redactions.map(red => {
    const color = 
      red.confidence > 0.9 ? 'rgba(0, 255, 0, 0.2)' :   // Green = high
      red.confidence > 0.7 ? 'rgba(255, 255, 0, 0.2)' : // Yellow = medium  
      'rgba(255, 0, 0, 0.3)';                            // Red = low
    
    return <RedactionBox bbox={red.bbox} color={color} />;
  });
}
```

#### 3.3 Keyboard Shortcuts for Power Users
```
Space        — Approve selected redaction
Backspace    — Reject selected redaction  
Arrow keys   — Navigate between redactions
Shift+Arrow — Adjust box size
Tab          — Cycle through redaction types
Ctrl+S       — Save progress
Ctrl+A       — Approve all high-confidence
Ctrl+Shift+A — Approve ALL pending
```

#### 3.4 Review Queue with SLA
**New backend endpoints:**
```python
@app.get("/api/review-queue")
async def get_review_queue(
    priority: str = Query("all", enum=["urgent", "high", "normal", "all"]),
    sla_hours: int = Query(24),
    assigned_to: Optional[str] = None,
):
    """Return documents needing review, sorted by SLA urgency."""
    
@app.post("/api/redaction/{redaction_id}/approve")
@app.post("/api/redaction/{redaction_id}/reject")
@app.post("/api/redaction/{redaction_id}/adjust")
@app.post("/api/redaction/{redaction_id}/change-type")
```

#### 3.5 Audit Trail Enhancement
**Current:** Basic action logging
**Upgrade:** Full forensic audit

```python
class EnhancedAuditLog:
    def log_redaction_decision(self, doc_id, redaction_id, user_id, 
                                decision, previous_state, new_state,
                                reason=None):
        """
        decision: "approved", "rejected", "modified", "added", "removed"
        Captures before/after state for compliance.
        """
        entry = AuditLog(
            document_id=doc_id,
            action=f"redaction_{decision}",
            user_id=user_id,
            details={
                "redaction_id": redaction_id,
                "decision": decision,
                "previous_bbox": previous_state.get("bbox"),
                "new_bbox": new_state.get("bbox"),
                "previous_type": previous_state.get("type"),
                "new_type": new_state.get("type"),
                "reason": reason,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
```

---

### Phase 4: Batch & Automation (Week 4-5)
**Goal:** Handle volume. Councils don't process 1 doc at a time.

#### 4.1 Job Queue System
```python
class BatchJob:
    def __init__(self, job_id, files, config):
        self.id = job_id
        self.files = files  # List of file paths
        self.config = config  # Redaction profile, translation, etc.
        self.status = "queued"
        self.progress = 0
        self.results = []
        
class JobQueue:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.workers = []  # Background workers
        
    async def add_job(self, files, config) -> str:
        job_id = str(uuid.uuid4())
        job = BatchJob(job_id, files, config)
        await self.queue.put(job)
        return job_id
        
    async def worker_loop(self):
        while True:
            job = await self.queue.get()
            await self.process_job(job)
            
    async def process_job(self, job):
        for i, file_path in enumerate(job.files):
            # Process each doc
            doc_id = await self.upload_and_process(file_path, job.config)
            job.results.append(doc_id)
            job.progress = (i + 1) / len(job.files) * 100
            
            # Emit progress via WebSocket
            await self.emit_progress(job.id, job.progress)
```

#### 4.2 Drop Folder / Watch Mode
```python
class FolderWatcher:
    def __init__(self, watch_path, output_path):
        self.watch_path = watch_path
        self.output_path = output_path
        
    def start_watching(self):
        """Watch folder for new files and auto-process."""
        observer = Observer()
        handler = AutoProcessHandler(self.output_path)
        observer.schedule(handler, self.watch_path, recursive=True)
        observer.start()
        
class AutoProcessHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(('.png', '.jpg', '.pdf')):
            # Auto-queue for processing
            self.queue.add_job([event.src_path], auto_config=True)
```

#### 4.3 Processing Dashboard
```
┌─────────────────────────────────────────────────────────────┐
│ BATCH PROCESSING DASHBOARD                                  │
├─────────────────────────────────────────────────────────────┤
│ Active Jobs: 3 | Queue: 47 docs | Completed today: 1,247      │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ Job #2847    │ Job #2848    │ Job #2849    │ + New Batch    │
│ Housing Dept │ Parking Team │ Safeguarding │ [Drop ZIP]     │
│              │              │              │                │
│ ████████░░   │ █████░░░░░   │ ██░░░░░░░░   │                │
│ 78% (47/60)  │ 45% (9/20)   │ 15% (3/20)   │                │
│              │              │              │                │
│ ⏱️ ETA: 4m   │ ⏱️ ETA: 12m  │ ⏱️ ETA: 34m  │                │
│ 12 reviewing │ 5 reviewing  │ 18 reviewing │                │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

#### 4.4 API Webhooks & Integrations
```python
@app.post("/api/webhooks/configure")
async def configure_webhook(
    url: str,
    events: List[str],  # ["doc.complete", "doc.needs_review", "batch.done"]
    secret: str,  # For HMAC signature
):
    """Configure webhook for external system integration."""
    
# Events emitted:
# - doc.uploaded
# - doc.processing.complete
# - doc.needs_review
# - doc.approved
# - doc.exported
# - batch.started
# - batch.progress
# - batch.completed
# - safeguarding.alert
```

---

### Phase 5: Security Fortress (Week 5-6)
**Goal:** Council procurement compliance. GDPR. Audit-proof.

#### 5.1 Database Encryption
```python
# Current: Plain SQLite
# Upgrade: SQLCipher encrypted SQLite

from sqlcipher3 import dbapi2 as sqlite

def init_encrypted_db(password):
    conn = sqlite.connect(DB_PATH)
    conn.execute(f"PRAGMA key = '{password}'")
    return conn

# All PII stored encrypted at rest
# Even if someone copies the .db file, it's useless without key
```

#### 5.2 Tamper-Proof Audit Logs
```python
import hashlib
import ed25519

class TamperProofAudit:
    def __init__(self, signing_key):
        self.sk = signing_key
        self.last_hash = b'0' * 64  # Genesis hash
        
    def log(self, entry):
        # Chain hash: each entry includes hash of previous
        data = json.dumps(entry, sort_keys=True)
        chained = f"{self.last_hash.hex()}:{data}"
        entry_hash = hashlib.sha256(chained.encode()).digest()
        signature = self.sk.sign(entry_hash)
        
        entry["_chain_hash"] = entry_hash.hex()
        entry["_signature"] = signature.hex()
        entry["_previous_hash"] = self.last_hash.hex()
        
        self.last_hash = entry_hash
        return entry
        
    def verify_chain(self, entries):
        """Verify entire audit chain hasn't been tampered."""
        for i, entry in enumerate(entries):
            expected_prev = entries[i-1]["_chain_hash"] if i > 0 else '0'*64
            if entry["_previous_hash"] != expected_prev:
                raise TamperError(f"Chain broken at entry {i}")
```

#### 5.3 Role-Based Access Control (RBAC)
```python
class RBAC:
    PERMISSIONS = {
        "document.upload": ["processor", "admin", "caseworker"],
        "document.review": ["reviewer", "admin"],
        "document.approve": ["reviewer", "admin"],
        "document.export": ["processor", "reviewer", "admin"],
        "document.delete": ["admin"],
        "audit.read": ["auditor", "admin"],
        "settings.modify": ["admin"],
        "batch.create": ["processor", "admin"],
        "webhook.configure": ["admin"],
    }
    
    def check(self, user_role, permission):
        return user_role in self.PERMISSIONS.get(permission, [])
```

#### 5.4 Retention Policies
```python
class RetentionPolicy:
    def __init__(self, db):
        self.policies = {
            "housing_repairs": 7,      # years
            "council_tax": 7,
            "parking": 2,
            "complaint": 3,
            "children_safeguarding": 25,  # Until child turns 25
            "foi_legal": 3,
            "default": 7,
        }
        
    async def enforce(self):
        """Daily job: purge expired documents."""
        for category, years in self.policies.items():
            cutoff = datetime.now() - timedelta(days=years * 365)
            expired = self.db.query(Document).filter(
                Document.category == category,
                Document.created_at < cutoff
            ).all()
            
            for doc in expired:
                # Secure delete: overwrite file before unlinking
                self.secure_delete(doc.original_path)
                self.secure_delete(doc.redacted_path)
                self.db.delete(doc)
                
    def secure_delete(self, path):
        """Overwrite file with random data before deletion."""
        if os.path.exists(path):
            size = os.path.getsize(path)
            with open(path, 'wb') as f:
                f.write(os.urandom(size))
            os.unlink(path)
```

#### 5.5 Watermarking
```python
class ForensicWatermark:
    def embed(self, image_path, metadata):
        """
        Invisibly embed document ID, user ID, timestamp into image.
        Uses DCT (Discrete Cosine Transform) steganography.
        Undetectable to eye, recoverable if leaked.
        """
        import numpy as np
        from scipy.fftpack import dct, idct
        
        img = cv2.imread(image_path)
        # Embed in frequency domain
        watermark = f"SYNTHETIQ:{metadata['doc_id']}:{metadata['user_id']}:{metadata['timestamp']}"
        # ... DCT embedding logic ...
        
    def extract(self, image_path):
        """Extract watermark from leaked image to trace source."""
```

---

### Phase 6: Multi-Modal Inputs (Week 6-7)
**Goal:** Handle more than just photos.

#### 6.1 PDF Processing
```python
class PDFProcessor:
    def process(self, pdf_path):
        """
        - Extract each page as image
        - Detect if page is scanned (image-based) or text-based
        - For text-based: extract text directly, no OCR needed
        - For scanned: run OCR pipeline
        - Maintain page numbers in output
        """
        from pdf2image import convert_from_path
        from PyPDF2 import PdfReader
        
        # Check if text-based
        reader = PdfReader(pdf_path)
        has_text = any(page.extract_text() for page in reader.pages)
        
        if has_text:
            # Native PDF text extraction
            return self.extract_native_text(reader)
        else:
            # Image-based PDF, convert to images
            images = convert_from_path(pdf_path, dpi=300)
            return [self.ocr.process(img) for img in images]
```

#### 6.2 Email Processing
```python
class EmailProcessor:
    def process_email(self, .eml_or_.msg_file):
        """
        - Parse headers (redact sender, recipients)
        - Extract attachments (process each)
        - Handle thread/conversation context
        - Maintain email structure in output
        """
        import email
        
        msg = email.message_from_file(f)
        
        # Redact headers
        headers_to_redact = ['From', 'To', 'Cc', 'Reply-To']
        
        # Process body (HTML or plain text)
        # Process attachments
```

#### 6.3 Screenshot / Image Cleanup
```python
class ImageCleanup:
    def preprocess(self, image_path):
        """
        Enhanced preprocessing:
        - Auto-rotate based on text direction
        - Perspective correction (fix camera angle)
        - Glare removal
        - Shadow correction
        - De-skew
        - Auto-crop to document boundaries
        """
        img = cv2.imread(image_path)
        
        # Detect document edges
        edges = self.detect_document_edges(img)
        
        # Perspective transform
        if edges:
            img = self.perspective_correct(img, edges)
            
        # Glare removal
        img = self.remove_glare(img)
        
        return img
```

---

### Phase 7: Integration Ecosystem (Week 7-8)
**Goal:** Become infrastructure, not just an app.

#### 7.1 REST API v2
```python
# Current: Basic upload/download
# Upgrade: Full CRUD + webhooks + batch + search

@app.post("/v2/batch")
async def create_batch_job(files: List[UploadFile], config: BatchConfig):
    """Upload multiple files, get job ID for tracking."""
    
@app.get("/v2/batch/{job_id}/status")
async def get_batch_status(job_id: str):
    """Real-time progress of batch job."""
    
@app.get("/v2/documents/search")
async def search_documents(
    query: str,
    category: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    status: Optional[str] = None,
    redacted_only: bool = False,
):
    """Full-text search across processed documents."""
    
@app.post("/v2/documents/{doc_id}/share")
async def create_share_link(
    doc_id: str,
    expires_hours: int = 24,
    permissions: List[str] = ["view"],
):
    """Time-limited shareable link with audit trail."""
```

#### 7.2 SharePoint / OneDrive Connector
```python
class SharePointConnector:
    def __init__(self, tenant_id, client_id, client_secret):
        self.graph = MicrosoftGraphClient(tenant_id, client_id, client_secret)
        
    async def sync_folder(self, sharepoint_path, local_watch_path):
        """
        - Poll SharePoint folder for new documents
        - Download, process, upload redacted version
        - Maintain folder structure
        """
        
    async def upload_result(self, doc_id, sharepoint_destination):
        """Upload redacted output back to SharePoint."""
```

#### 7.3 Zapier / Make.com Integration
```python
# Standard webhook format for no-code platforms
ZAPIER_WEBHOOK_FORMAT = {
    "event": "doc.processed",
    "document_id": "...",
    "status": "complete",
    "redaction_summary": {
        "total": 23,
        "by_type": {"person_name": 3, "address": 2, "phone": 4},
    },
    "download_links": {
        "redacted_image": "https://...",
        "redacted_text": "https://...",
        "docx": "https://...",
    },
    "needs_review": False,
    "processing_time_seconds": 12.4,
}
```

---

### Phase 8: Mobile Becomes Primary (Week 8-9)
**Goal:** Field workers can process docs on-site.

#### 8.1 Flutter App Overhaul
```dart
class ScanScreen extends StatelessWidget {
  // Camera guide overlay
  // - Document edge detection live preview
  // - "Move closer" / "Reduce glare" guidance
  // - Auto-capture when document is stable and centered
  
  Widget build(BuildContext context) {
    return CameraPreview(
      overlay: DocumentGuideOverlay(
        onDocumentDetected: (bounds) {
          // Show green rectangle around detected document
          // Auto-capture when stable for 1 second
        },
        onGuidanceNeeded: (message) {
          // "Too dark", "Move closer", "Straighten"
        },
      ),
    );
  }
}
```

#### 8.2 Offline Mode
```dart
class OfflineQueue {
  // When no network:
  // 1. Save document to local SQLite
  // 2. Queue for processing
  // 3. Process locally if models cached
  // 4. Sync when online
  
  Future<void> processOffline(Document doc) async {
    final hasModels = await LocalModels.areAvailable();
    if (hasModels) {
      // Run local OCR + redaction
      final result = await LocalPipeline.process(doc);
      await localDb.saveResult(result);
    } else {
      // Just queue for server processing
      await syncQueue.add(doc);
    }
  }
}
```

#### 8.3 Voice Notes
```dart
class VoiceNoteAttachment {
  // Attach voice memo to flagged document
  // e.g., "This handwritten note is a safeguarding concern 
  //        from a home visit today"
  
  Future<void> attachVoiceNote(String docId, String audioPath) async {
    // Transcribe audio to text
    final transcription = await Whisper.transcribe(audioPath);
    // Attach to document metadata
    await api.attachNote(docId, {
      "type": "voice_transcription",
      "audio_url": audioPath,
      "text": transcription,
      "timestamp": DateTime.now(),
    });
  }
}
```

---

### Phase 9: Analytics Dashboard (Week 9-10)
**Goal:** Insight into processing volume, accuracy, cost savings.

#### 9.1 Processing Metrics
```javascript
const DashboardMetrics = {
  // Volume
  documentsProcessedToday: 1247,
  documentsThisMonth: 28471,
  avgProcessingTime: "12.4s",
  
  // Quality
  autoApprovedRate: 0.73,      // 73% need no human review
  humanReviewRate: 0.27,
  avgReviewTime: "4.2m",
  
  // Accuracy
  correctionRate: 0.08,       // 8% of redactions are corrected
  mostCorrectedType: "phone",
  
  // Cost savings
  estimatedManualHoursSaved: 416,  // vs manual redaction
  costSavingGBP: 8320,             // £20/hr * hours saved
  
  // Safeguarding
  safeguardingAlertsThisWeek: 12,
  avgUrgencyScore: 0.34,
}
```

#### 9.2 Trend Charts
```
Line chart: Processing volume over time
Bar chart: Documents by department
Pie chart: Redaction types distribution
Heatmap: Review queue load by hour/day
Alert timeline: Safeguarding flags over time
```

---

### Phase 10: Monetization Structure (Week 10+)
**Goal:** Revenue.

#### Tier Structure
```
┌─────────────────────────────────────────────────────────────┐
│ SYNTHETIQ REDACT — Pricing                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 🟢 COMMUNITY (Free)                                         │
│ • Single-user local processing                              │
│ • Basic OCR (EasyOCR)                                       │
│ • Standard redaction profiles                               │
│ • TXT/PNG export                                            │
│ • Community support                                         │
│                                                             │
│ 🔵 PRO — £49/month per user                                 │
│ • Multi-user (up to 5)                                      │
│ • Advanced OCR (PaddleOCR)                                  │
│ • Review studio with approval workflow                      │
│ • Batch processing (up to 100 docs/batch)                   │
│ • API access                                                │
│ • Priority email support                                    │
│                                                             │
│ 🟣 TEAM — £199/month                                        │
│ • Up to 25 users                                            │
│ • Role-based access control                                 │
│ • Batch processing (up to 1,000 docs/batch)               │
│ • Webhooks + Zapier integration                             │
│ • Encrypted database + tamper-proof audit                   │
│ • SharePoint/OneDrive connector                             │
│ • Dedicated support channel                                 │
│                                                             │
│ 🔴 ENTERPRISE — Custom pricing                              │
│ • Unlimited users                                           │
│ • On-premise deployment                                     │
│ • Custom redaction profiles                                 │
│ • SLA guarantee (99.9% uptime)                              │
│ • Custom integrations                                       │
│ • Training & onboarding                                     │
│ • Dedicated account manager                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. TECHNICAL IMPLEMENTATION PLAN

### Week-by-Week Breakdown

| Week | Focus | Key Deliverables |
|------|-------|-----------------|
| 1 | OCR + NER upgrade | PaddleOCR integration, BERT NER model |
| 2 | Smart redaction | Partial redaction, role-based visibility, pattern learning |
| 3 | Review studio UI | Split-screen interface, approval workflow, keyboard shortcuts |
| 4 | Backend review APIs | Redaction CRUD, confidence heatmap, review queue |
| 5 | Batch processing | Job queue, folder watcher, processing dashboard |
| 6 | Security hardening | SQLCipher, tamper-proof audit, RBAC, retention policies |
| 7 | Multi-modal | PDF processing, email parsing, enhanced image cleanup |
| 8 | Integrations | REST API v2, webhooks, SharePoint connector |
| 9 | Mobile overhaul | Camera guide, offline mode, voice notes |
| 10 | Analytics | Dashboard, trend charts, cost savings calculator |
| 11+ | Polish + monetization | Feature flags, licensing, payment integration |

### Database Schema Changes

```sql
-- New tables needed:

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL,  -- admin, reviewer, processor, auditor, caseworker
    department TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE batch_jobs (
    id TEXT PRIMARY KEY,
    name TEXT,
    status TEXT,  -- queued, processing, complete, failed
    total_docs INTEGER,
    processed_docs INTEGER,
    config JSON,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE batch_job_documents (
    batch_id TEXT REFERENCES batch_jobs(id),
    document_id INTEGER REFERENCES documents(id),
    status TEXT,
    PRIMARY KEY (batch_id, document_id)
);

CREATE TABLE redaction_reviews (
    id INTEGER PRIMARY KEY,
    redaction_id INTEGER REFERENCES redactions(id),
    reviewer_id INTEGER REFERENCES users(id),
    decision TEXT,  -- approved, rejected, modified
    previous_bbox JSON,
    new_bbox JSON,
    previous_type TEXT,
    new_type TEXT,
    reason TEXT,
    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE correction_patterns (
    id INTEGER PRIMARY KEY,
    redaction_type TEXT,
    adjustment_pixels_x INTEGER DEFAULT 0,
    adjustment_pixels_y INTEGER DEFAULT 0,
    adjustment_scale REAL DEFAULT 1.0,
    correction_count INTEGER DEFAULT 1,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE webhooks (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL,
    events JSON,  -- ["doc.complete", "doc.needs_review"]
    secret TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_by INTEGER REFERENCES users(id)
);

CREATE TABLE audit_log_v2 (
    id INTEGER PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),
    action TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    details JSON,
    chain_hash TEXT,  -- Tamper-proof chaining
    signature TEXT,
    previous_hash TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE retention_policies (
    id INTEGER PRIMARY KEY,
    category TEXT UNIQUE,
    retention_years INTEGER,
    auto_purge BOOLEAN DEFAULT FALSE
);
```

### API Endpoints (New)

```python
# Authentication
POST /api/auth/login
POST /api/auth/register
POST /api/auth/refresh

# Users (Admin only)
GET /api/users
POST /api/users
PUT /api/users/{id}
DELETE /api/users/{id}

# Batch Processing
POST /api/batch
GET /api/batch/{job_id}
GET /api/batch/{job_id}/progress
DELETE /api/batch/{job_id}

# Review Workflow
GET /api/review-queue
POST /api/redactions/{id}/approve
POST /api/redactions/{id}/reject
POST /api/redactions/{id}/modify
GET /api/documents/{id}/confidence-heatmap

# Exports
POST /api/documents/{id}/export/{format}
GET /api/documents/{id}/share-link

# Webhooks
POST /api/webhooks
GET /api/webhooks
DELETE /api/webhooks/{id}

# Analytics
GET /api/analytics/dashboard
GET /api/analytics/processing-volume
GET /api/analytics/accuracy-trends
GET /api/analytics/cost-savings
```

---

## 5. PROMPT FOR KIMI / CODEX / CLAUDE

Here's the mega-prompt to give to an AI coding assistant to build this:

```
You are building Synthetiq Redact v2.0, an advanced document redaction platform.

BASE CODE: We have a working prototype with:
- FastAPI + SQLAlchemy + SQLite backend
- React + Vite + Tailwind frontend  
- Flutter mobile (experimental)
- EasyOCR + spaCy + regex PII detection
- Optional Ollama/Qwen local LLM
- Category-based redaction profiles
- Per-document output folders
- Basic audit logging

YOUR MISSION: Implement the following major upgrade:

### PRIORITY 1: AI Stack Upgrade
1. Replace EasyOCR with PaddleOCR (primary) + EasyOCR (fallback)
2. Add LayoutAnalyzer to detect document regions (header, body, footer, signature)
3. Integrate a fine-tuned BERT model for UK-specific PII (NHS numbers, NI numbers, postcodes, council refs)
4. Add TrOCR for handwriting transcription (fallback to current MLX-VLM)
5. Keep all existing functionality working

### PRIORITY 2: Smart Redaction Engine  
1. Implement partial redaction policies (mask all but last 4 digits of phone, etc.)
2. Add role-based visibility (caseworker sees partial, public sees full, auditor sees all)
3. Create RedactionProfileBuilder for dynamic profiles based on sensitivity level
4. Add RedactionLearner that tracks human corrections and adjusts future redactions
5. Implement table/form structure preservation (redact cells without destroying table)

### PRIORITY 3: Human Review Studio (Backend APIs)
1. Create review queue endpoints with SLA sorting
2. Add redaction approval/rejection/modification APIs with full audit trail
3. Implement confidence heatmap generation
4. Add batch operations (approve all high-confidence, etc.)
5. Create tamper-proof audit log chain with Ed25519 signatures

### PRIORITY 4: Security & Enterprise
1. Encrypt SQLite with SQLCipher
2. Implement RBAC (Role-Based Access Control) 
3. Add retention policies with secure deletion
4. Create forensic watermarking for exported images
5. Add user authentication system

### PRIORITY 5: Batch & Automation
1. Build job queue system for batch document processing
2. Add folder watcher for auto-processing
3. Create batch progress dashboard API
4. Implement webhook system for external integrations

TECH STACK REQUIREMENTS:
- Keep local-first philosophy (no cloud APIs required)
- Python 3.11+ backend
- React 18+ frontend
- All existing tests must pass
- Add new tests for all new functionality
- Maintain backwards compatibility with v1.0 API

DELIVERABLES:
1. Complete backend code with all new endpoints
2. Frontend components for review studio
3. Updated database schema migration
4. Test suite covering new functionality
5. API documentation (OpenAPI/Swagger)
6. Deployment guide for enterprise setup

Start with PRIORITY 1 and work sequentially. Build each piece fully before moving to next.
```

---

## 6. RISK ASSESSMENT

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| PaddleOCR accuracy worse on some docs | Medium | High | Keep EasyOCR as fallback, A/B test |
| BERT model too slow on CPU | Medium | Medium | Quantize to INT8, use ONNX Runtime |
| Review UI too complex for users | Medium | High | User testing at Week 3, iterate |
| SQLite can't handle volume | Low | High | Migration path to PostgreSQL documented |
| Mobile app size too large | Medium | Medium | Separate app builds, dynamic model loading |
| Council procurement takes months | High | High | Start with free pilots, convert to paid |

---

## 7. SUCCESS METRICS

**Technical:**
- Auto-approval rate > 80% (currently unknown, target high)
- OCR confidence on handwriting > 0.75 (currently < 0.50)
- Processing time < 15s per document
- Zero data loss or corruption

**Business:**
- 10 council pilots within 6 months
- 3 paid conversions within 12 months
- £5K MRR by end of year 1

---

## 8. CONCLUSION

Synthetiq Redact has a **solid foundation** — local-first, privacy-first, with real AI processing.

The v2.0 upgrade transforms it from a **hackathon demo** into a **production platform** that councils will actually pay for.

Key differentiators:
1. **Truly local** — no cloud dependencies, works offline
2. **Smart AI** — context-aware, learning, role-based
3. **Council-ready** — audit trails, encryption, retention, compliance
4. **Field-capable** — mobile app for on-site workers
5. **Integrable** — API, webhooks, SharePoint, no-code tools

We move! Let's build this! 🔥⚡
