import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:image_picker/image_picker.dart';
import '../theme.dart';
import '../services/api_service.dart';
import '../utils/camera.dart';
import 'document_detail_screen.dart';

const _categories = [
  ('', 'Auto-detect'),
  ('housing_repairs', 'Housing Repairs'),
  ('council_tax', 'Council Tax'),
  ('parking', 'Parking'),
  ('complaint', 'Complaint'),
  ('waste', 'Waste / Environment'),
  ('adult_social_care', 'Adult Social Care'),
  ('children_safeguarding', 'Children Safeguarding'),
  ('foi_legal', 'FOI / Legal'),
];

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});
  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  Uint8List? _fileBytes;
  String? _fileName;
  String _selectedCategory = '';
  bool _translate = false;
  bool _uploading = false;
  String? _error;
  String _progressMsg = '';
  int _progressPct = 0;
  Timer? _pollTimer;

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  // ── Camera capture ────────────────────────────────────────────────────────

  Future<void> _takePhoto() async {
    setState(() => _error = null);
    try {
      if (kIsWeb) {
        // Web: use native browser file input with camera capture
        final result = await captureFromCamera();
        if (result.bytes != null && result.bytes!.isNotEmpty) {
          setState(() {
            _fileBytes = result.bytes;
            _fileName = result.name ?? 'photo_${DateTime.now().millisecondsSinceEpoch}.jpg';
          });
        }
      } else {
        // Native: use image_picker camera
        final picker = ImagePicker();
        final img = await picker.pickImage(
          source: ImageSource.camera,
          imageQuality: 75,
          maxWidth: 2048,
          maxHeight: 2048,
        );
        if (img != null) {
          final bytes = await img.readAsBytes();
          if (mounted) {
            setState(() {
              _fileBytes = bytes;
              _fileName = img.name;
            });
          }
        }
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Camera error: ${e.toString().split('\n').first}');
    }
  }

  // ── File picker ───────────────────────────────────────────────────────────

  Future<void> _pickFile() async {
    setState(() => _error = null);
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['jpg', 'jpeg', 'png', 'pdf'],
        withData: true,
      );
      if (result != null && result.files.isNotEmpty) {
        final file = result.files.first;
        if (file.bytes != null) {
          setState(() {
            _fileBytes = file.bytes;
            _fileName = file.name;
          });
        }
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not open file: ${e.toString().split('\n').first}');
    }
  }

  // ── Gallery picker (native only) ──────────────────────────────────────────

  Future<void> _pickFromGallery() async {
    setState(() => _error = null);
    try {
      final picker = ImagePicker();
      final img = await picker.pickImage(
        source: ImageSource.gallery,
        imageQuality: 75,
        maxWidth: 2048,
        maxHeight: 2048,
      );
      if (img != null) {
        final bytes = await img.readAsBytes();
        if (mounted) {
          setState(() {
            _fileBytes = bytes;
            _fileName = img.name;
          });
        }
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Gallery error: ${e.toString().split('\n').first}');
    }
  }

  // ── Upload & progress ─────────────────────────────────────────────────────

  Future<void> _upload() async {
    if (_fileBytes == null || _fileName == null) return;
    setState(() {
      _uploading = true;
      _error = null;
      _progressMsg = 'Uploading...';
      _progressPct = 5;
    });

    try {
      final docId = await ApiService().uploadDocument(
        filename: _fileName!,
        fileBytes: _fileBytes!,
        mimeType: _fileName!.toLowerCase().endsWith('.pdf')
            ? 'application/pdf'
            : 'image/jpeg',
        translate: _translate,
        selectedCategory: _selectedCategory,
      );
      setState(() {
        _progressMsg = 'Processing...';
        _progressPct = 15;
      });
      _startPolling(docId);
    } catch (e) {
      setState(() {
        _error = e.toString();
        _uploading = false;
      });
    }
  }

  void _startPolling(int docId) {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) async {
      try {
        final doc = await ApiService().getDocument(docId);
        if (!mounted) return;
        const statusPct = {
          'uploaded': 10, 'preprocessing': 22, 'ocr': 38,
          'redaction': 56, 'translation': 66, 'classification': 78,
          'routing': 90, 'complete': 100, 'needs_review': 100, 'error': 100,
        };
        setState(() {
          _progressMsg = doc.displayStatus;
          _progressPct = statusPct[doc.status] ?? 50;
        });
        if (doc.status == 'complete' || doc.status == 'needs_review' || doc.status == 'error') {
          _pollTimer?.cancel();
          await Future.delayed(const Duration(milliseconds: 500));
          if (!mounted) return;
          Navigator.of(context).pushReplacement(
            MaterialPageRoute(builder: (_) => DocumentDetailScreen(docId: docId)),
          );
        }
      } catch (_) {}
    });
  }

  void _reset() {
    _pollTimer?.cancel();
    setState(() {
      _fileBytes = null;
      _fileName = null;
      _uploading = false;
      _progressMsg = '';
      _progressPct = 0;
      _error = null;
    });
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Document')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [

            if (_uploading) ...[
              const SizedBox(height: 16),
              _ProgressCard(message: _progressMsg, percent: _progressPct),
            ] else ...[

              // ── Preview ──────────────────────────────────────────────────
              if (_fileBytes != null) ...[
                _PreviewCard(
                  bytes: _fileBytes!,
                  fileName: _fileName ?? '',
                  onRemove: _reset,
                ),
                const SizedBox(height: 16),
              ] else ...[
                // ── Capture buttons ───────────────────────────────────────
                _CaptureArea(
                  onCamera: _takePhoto,
                  onUpload: _pickFile,
                  onGallery: kIsWeb ? null : _pickFromGallery,
                ),
                const SizedBox(height: 16),
              ],

              // ── Category selector ─────────────────────────────────────
              _SectionLabel(label: 'Document Category'),
              const SizedBox(height: 6),
              _CategoryPicker(
                value: _selectedCategory,
                onChanged: (v) => setState(() => _selectedCategory = v),
              ),
              const SizedBox(height: 12),

              // ── Translate toggle ──────────────────────────────────────
              _TranslateToggle(
                value: _translate,
                onChanged: (v) => setState(() => _translate = v),
              ),
              const SizedBox(height: 20),

              // ── Process button ────────────────────────────────────────
              SizedBox(
                height: 52,
                child: ElevatedButton.icon(
                  onPressed: _fileBytes == null ? null : _upload,
                  icon: const Icon(Icons.auto_fix_high_outlined, size: 20),
                  label: Text(
                    _fileBytes == null ? 'Select a document first' : 'Process Document',
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: _fileBytes == null ? kSurface2 : kPrimary,
                    foregroundColor: _fileBytes == null ? kTextSecondary : Colors.white,
                  ),
                ),
              ),
            ],

            // ── Error ─────────────────────────────────────────────────────
            if (_error != null) ...[
              const SizedBox(height: 12),
              _ErrorBanner(message: _error!),
            ],

            const SizedBox(height: 28),
            const Center(
              child: Text(
                'Hillingdon Council · Synthetic demo data only',
                style: TextStyle(color: kTextSecondary, fontSize: 11),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Widgets ──────────────────────────────────────────────────────────────────

class _SectionLabel extends StatelessWidget {
  final String label;
  const _SectionLabel({required this.label});
  @override
  Widget build(BuildContext context) => Text(
        label,
        style: const TextStyle(
          color: kTextSecondary,
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 1.1,
        ),
      );
}

class _CaptureArea extends StatelessWidget {
  final VoidCallback onCamera;
  final VoidCallback onUpload;
  final VoidCallback? onGallery;
  const _CaptureArea({required this.onCamera, required this.onUpload, this.onGallery});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Primary — camera
        GestureDetector(
          onTap: onCamera,
          child: Container(
            height: 160,
            decoration: BoxDecoration(
              color: kPrimary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: kPrimary.withValues(alpha: 0.4), width: 2),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: const [
                Icon(Icons.camera_alt_outlined, color: kPrimary, size: 44),
                SizedBox(height: 12),
                Text(
                  'Scan with Camera',
                  style: TextStyle(color: kPrimary, fontSize: 16, fontWeight: FontWeight.w700),
                ),
                SizedBox(height: 4),
                Text(
                  'Tap to open camera',
                  style: TextStyle(color: kTextSecondary, fontSize: 13),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),

        // Secondary buttons row
        Row(
          children: [
            Expanded(
              child: _SecondaryBtn(
                icon: Icons.upload_file_outlined,
                label: 'Upload File',
                subtitle: 'JPG · PNG · PDF',
                onTap: onUpload,
              ),
            ),
            if (onGallery != null) ...[
              const SizedBox(width: 10),
              Expanded(
                child: _SecondaryBtn(
                  icon: Icons.photo_library_outlined,
                  label: 'Gallery',
                  subtitle: 'From photos',
                  onTap: onGallery!,
                ),
              ),
            ],
          ],
        ),
      ],
    );
  }
}

class _SecondaryBtn extends StatelessWidget {
  final IconData icon;
  final String label;
  final String subtitle;
  final VoidCallback onTap;
  const _SecondaryBtn({required this.icon, required this.label, required this.subtitle, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: kBorder),
        ),
        child: Column(
          children: [
            Icon(icon, color: kTextSecondary, size: 26),
            const SizedBox(height: 6),
            Text(label, style: const TextStyle(color: kTextPrimary, fontSize: 13, fontWeight: FontWeight.w600)),
            const SizedBox(height: 2),
            Text(subtitle, style: const TextStyle(color: kTextSecondary, fontSize: 11)),
          ],
        ),
      ),
    );
  }
}

class _PreviewCard extends StatelessWidget {
  final Uint8List bytes;
  final String fileName;
  final VoidCallback onRemove;
  const _PreviewCard({required this.bytes, required this.fileName, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(14),
          child: Image.memory(
            bytes,
            width: double.infinity,
            height: 260,
            fit: BoxFit.cover,
          ),
        ),
        // Remove button
        Positioned(
          top: 10, right: 10,
          child: GestureDetector(
            onTap: onRemove,
            child: Container(
              padding: const EdgeInsets.all(7),
              decoration: const BoxDecoration(color: kRed, shape: BoxShape.circle),
              child: const Icon(Icons.close, color: Colors.white, size: 16),
            ),
          ),
        ),
        // Filename badge
        Positioned(
          bottom: 10, left: 10, right: 60,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.65),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              fileName,
              style: const TextStyle(color: Colors.white, fontSize: 12),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
        // Ready badge
        Positioned(
          bottom: 10, right: 10,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            decoration: BoxDecoration(
              color: kPrimary.withValues(alpha: 0.9),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Text('Ready', style: TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600)),
          ),
        ),
      ],
    );
  }
}

class _CategoryPicker extends StatelessWidget {
  final String value;
  final void Function(String) onChanged;
  const _CategoryPicker({required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: kBorder),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: value,
          isExpanded: true,
          dropdownColor: kSurface,
          style: const TextStyle(color: kTextPrimary, fontSize: 14),
          icon: const Icon(Icons.keyboard_arrow_down, color: kTextSecondary),
          items: _categories.map((c) => DropdownMenuItem(
            value: c.$1,
            child: Text(c.$2, style: TextStyle(color: c.$1.isEmpty ? kTextSecondary : kTextPrimary)),
          )).toList(),
          onChanged: (v) => onChanged(v ?? ''),
        ),
      ),
    );
  }
}

class _TranslateToggle extends StatelessWidget {
  final bool value;
  final void Function(bool) onChanged;
  const _TranslateToggle({required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => onChanged(!value),
      child: Container(
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: value ? kPrimary.withValues(alpha: 0.5) : kBorder),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(
          children: [
            Icon(Icons.translate_outlined, color: value ? kPrimary : kTextSecondary, size: 20),
            const SizedBox(width: 12),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Translate to English', style: TextStyle(color: kTextPrimary, fontSize: 14, fontWeight: FontWeight.w500)),
                  Text('Detects and translates non-English text', style: TextStyle(color: kTextSecondary, fontSize: 12)),
                ],
              ),
            ),
            Switch(
              value: value,
              onChanged: onChanged,
              activeTrackColor: kPrimary,
              activeThumbColor: Colors.white,
            ),
          ],
        ),
      ),
    );
  }
}

class _ProgressCard extends StatelessWidget {
  final String message;
  final int percent;
  const _ProgressCard({required this.message, required this.percent});

  static const _steps = [
    ('preprocessing', 'Preprocessing image'),
    ('ocr', 'Extracting text (OCR)'),
    ('redaction', 'Detecting sensitive data'),
    ('translation', 'Language detection'),
    ('classification', 'Classifying document'),
    ('routing', 'Routing & urgency'),
  ];

  String get _currentStepLabel {
    final lower = message.toLowerCase();
    for (final s in _steps) {
      if (lower.contains(s.$1)) return s.$2;
    }
    return message.isEmpty ? 'Processing...' : message;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: kBorder),
      ),
      child: Column(
        children: [
          // Animated spinner
          Stack(
            alignment: Alignment.center,
            children: [
              SizedBox(
                width: 72, height: 72,
                child: CircularProgressIndicator(
                  value: percent > 0 ? percent / 100 : null,
                  strokeWidth: 5,
                  color: kPrimary,
                  backgroundColor: kBorder,
                ),
              ),
              Text(
                percent > 0 ? '$percent%' : '',
                style: const TextStyle(color: kPrimary, fontWeight: FontWeight.w700, fontSize: 14),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Text(
            _currentStepLabel,
            style: const TextStyle(color: kTextPrimary, fontSize: 15, fontWeight: FontWeight.w600),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: percent > 0 ? percent / 100 : null,
              backgroundColor: kBorder,
              valueColor: const AlwaysStoppedAnimation(kPrimary),
              minHeight: 7,
            ),
          ),
          const SizedBox(height: 20),
          // Pipeline steps
          ..._steps.map((s) {
            final stepPct = _steps.indexOf(s) * 16 + 10;
            final done = percent > stepPct;
            final active = percent > stepPct - 10 && !done;
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                children: [
                  Icon(
                    done ? Icons.check_circle : (active ? Icons.radio_button_checked : Icons.radio_button_unchecked),
                    color: done ? kPrimary : (active ? kBlue : kBorder),
                    size: 16,
                  ),
                  const SizedBox(width: 10),
                  Text(
                    s.$2,
                    style: TextStyle(
                      color: done ? kPrimary : (active ? kTextPrimary : kTextSecondary),
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  final String message;
  const _ErrorBanner({required this.message});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: kRed.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: kRed.withValues(alpha: 0.4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.error_outline, color: kRed, size: 18),
          const SizedBox(width: 8),
          Expanded(child: Text(message, style: const TextStyle(color: kRed, fontSize: 13))),
        ],
      ),
    );
  }
}
