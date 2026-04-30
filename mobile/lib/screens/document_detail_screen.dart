import 'package:flutter/material.dart';
import '../theme.dart';
import '../models/document.dart';
import '../services/api_service.dart';

class DocumentDetailScreen extends StatefulWidget {
  final int docId;
  const DocumentDetailScreen({super.key, required this.docId});
  @override
  State<DocumentDetailScreen> createState() => _DocumentDetailScreenState();
}

class _DocumentDetailScreenState extends State<DocumentDetailScreen>
    with SingleTickerProviderStateMixin {
  Document? _doc;
  bool _loading = true;
  String? _error;
  bool _showRedacted = true;
  late TabController _tabCtrl;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 2, vsync: this);
    _tabCtrl.addListener(() => setState(() => _showRedacted = _tabCtrl.index == 0));
    _load();
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final doc = await ApiService().getDocument(widget.docId);
      if (mounted) setState(() { _doc = doc; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _approve() async {
    try {
      await ApiService().approveDocument(widget.docId);
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Document approved'), backgroundColor: kPrimary),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e'), backgroundColor: kRed),
      );
    }
  }

  Future<void> _flagReview() async {
    try {
      await ApiService().flagForReview(widget.docId);
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Flagged for human review'), backgroundColor: kAmber),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e'), backgroundColor: kRed),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_doc?.filename ?? 'Document ${widget.docId}', maxLines: 1, overflow: TextOverflow.ellipsis),
        leading: const BackButton(),
        bottom: TabBar(
          controller: _tabCtrl,
          labelColor: kPrimary,
          unselectedLabelColor: kTextSecondary,
          indicatorColor: kPrimary,
          tabs: const [
            Tab(text: 'REDACTED'),
            Tab(text: 'ORIGINAL'),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: kPrimary))
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline, color: kRed, size: 40),
                      const SizedBox(height: 12),
                      Text(_error!, style: const TextStyle(color: kTextSecondary)),
                      const SizedBox(height: 16),
                      ElevatedButton(onPressed: _load, child: const Text('Retry')),
                    ],
                  ),
                )
              : _doc == null
                  ? const SizedBox()
                  : ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        // Image view with tab-controlled toggle
                        _ImageCard(docId: widget.docId, showRedacted: _showRedacted),
                        const SizedBox(height: 16),

                        // Status + review flag
                        _StatusRow(doc: _doc!),
                        const SizedBox(height: 16),

                        // Info grid
                        _InfoGrid(doc: _doc!),
                        const SizedBox(height: 16),

                        // Risk flags
                        if (_doc!.riskFlags.isNotEmpty) ...[
                          _RiskFlagsCard(flags: _doc!.riskFlags),
                          const SizedBox(height: 16),
                        ],

                        // Redaction profile
                        if (_doc!.redactionProfile != null) ...[
                          _ProfileCard(profile: _doc!.redactionProfile!),
                          const SizedBox(height: 16),
                        ],

                        // Action buttons
                        _ActionButtons(doc: _doc!, onApprove: _approve, onFlag: _flagReview, docId: widget.docId),
                        const SizedBox(height: 24),
                      ],
                    ),
    );
  }
}

// ─── Sub-widgets ──────────────────────────────────────────────────────────────

class _ImageCard extends StatelessWidget {
  final int docId;
  final bool showRedacted;
  const _ImageCard({required this.docId, required this.showRedacted});

  @override
  Widget build(BuildContext context) {
    final url = ApiService().imageUrl(docId, redacted: showRedacted);
    return Container(
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: kBorder),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          // Label
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: const BoxDecoration(
              border: Border(bottom: BorderSide(color: kBorder)),
            ),
            child: Row(
              children: [
                Icon(
                  showRedacted ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                  color: showRedacted ? kAmber : kPrimary,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Text(
                  showRedacted ? 'Redacted Version' : 'Original (Confidential)',
                  style: TextStyle(
                    color: showRedacted ? kAmber : kPrimary,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          // Image
          InteractiveViewer(
            child: Image.network(
              url,
              loadingBuilder: (_, child, progress) => progress == null
                  ? child
                  : SizedBox(
                      height: 200,
                      child: Center(
                        child: CircularProgressIndicator(
                          value: progress.expectedTotalBytes != null
                              ? progress.cumulativeBytesLoaded / progress.expectedTotalBytes!
                              : null,
                          color: kPrimary,
                        ),
                      ),
                    ),
              errorBuilder: (_, __, ___) => Container(
                height: 140,
                color: kSurface2,
                child: const Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.broken_image_outlined, color: kTextSecondary, size: 32),
                      SizedBox(height: 8),
                      Text('Image not available yet', style: TextStyle(color: kTextSecondary, fontSize: 13)),
                    ],
                  ),
                ),
              ),
              width: double.infinity,
              fit: BoxFit.fitWidth,
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  final Document doc;
  const _StatusRow({required this.doc});

  @override
  Widget build(BuildContext context) {
    Color color;
    if (doc.hasError) color = kRed;
    else if (doc.needsReview) color = kAmber;
    else if (doc.isProcessing) color = kBlue;
    else color = kPrimary;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Icon(
            doc.hasError ? Icons.error_outline
                : doc.needsReview ? Icons.rate_review_outlined
                : doc.isProcessing ? Icons.hourglass_empty_outlined
                : Icons.check_circle_outline,
            color: color,
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(doc.displayStatus, style: TextStyle(color: color, fontWeight: FontWeight.w600)),
          ),
          if (doc.flagNeedsReview)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: kAmber.withOpacity(0.15),
                borderRadius: BorderRadius.circular(6),
              ),
              child: const Text('Human Review', style: TextStyle(color: kAmber, fontSize: 11)),
            ),
        ],
      ),
    );
  }
}

class _InfoGrid extends StatelessWidget {
  final Document doc;
  const _InfoGrid({required this.doc});

  @override
  Widget build(BuildContext context) {
    final items = <(String, String)>[
      ('Category', doc.displayCategory),
      ('Department', doc.department ?? '—'),
      ('Urgency', doc.urgencyScore != null ? '${(doc.urgencyScore! * 100).round()}%' : '—'),
      ('Sentiment', doc.sentiment ?? '—'),
      ('Language', doc.languageDetected ?? '—'),
      ('Translated', doc.translated ? 'Yes' : 'No'),
      ('AI Confidence', doc.confidenceScore != null ? '${(doc.confidenceScore! * 100).round()}%' : '—'),
      ('OCR Confidence', doc.ocrConfidence != null ? '${(doc.ocrConfidence! * 100).round()}%' : '—'),
    ];

    return Container(
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: kBorder),
      ),
      child: Column(
        children: List.generate(items.length, (i) {
          final item = items[i];
          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(item.$1, style: const TextStyle(color: kTextSecondary, fontSize: 13)),
                    Text(
                      item.$2,
                      style: const TextStyle(color: kTextPrimary, fontSize: 13, fontWeight: FontWeight.w500),
                    ),
                  ],
                ),
              ),
              if (i < items.length - 1) const Divider(height: 1, color: kBorder),
            ],
          );
        }),
      ),
    );
  }
}

class _RiskFlagsCard extends StatelessWidget {
  final List<String> flags;
  const _RiskFlagsCard({required this.flags});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: kRed.withOpacity(0.06),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: kRed.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.warning_amber_outlined, color: kRed, size: 18),
              SizedBox(width: 8),
              Text('Risk Flags', style: TextStyle(color: kRed, fontWeight: FontWeight.w600, fontSize: 14)),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8, runSpacing: 8,
            children: flags.map((f) => Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: kRed.withOpacity(0.12),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(f, style: const TextStyle(color: kRed, fontSize: 12)),
            )).toList(),
          ),
        ],
      ),
    );
  }
}

class _ProfileCard extends StatelessWidget {
  final String profile;
  const _ProfileCard({required this.profile});

  @override
  Widget build(BuildContext context) {
    final profiles = profile.split(',').where((p) => p.isNotEmpty).toList();
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: kBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Redaction Profile', style: TextStyle(color: kTextSecondary, fontSize: 13)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8, runSpacing: 8,
            children: profiles.map((p) => Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: kPrimary.withOpacity(0.12),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                p.replaceAll('_', ' '),
                style: const TextStyle(color: kPrimary, fontSize: 12),
              ),
            )).toList(),
          ),
        ],
      ),
    );
  }
}

class _ActionButtons extends StatelessWidget {
  final Document doc;
  final VoidCallback onApprove;
  final VoidCallback onFlag;
  final int docId;
  const _ActionButtons({required this.doc, required this.onApprove, required this.onFlag, required this.docId});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Download export text
        OutlinedButton.icon(
          onPressed: () {
            final url = ApiService().exportUrl(docId);
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text('Export URL: $url'), backgroundColor: kSurface2),
            );
          },
          icon: const Icon(Icons.download_outlined, size: 18),
          label: const Text('Download Redacted Text'),
          style: OutlinedButton.styleFrom(
            foregroundColor: kTextPrimary,
            side: const BorderSide(color: kBorder),
            minimumSize: const Size(double.infinity, 48),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
        const SizedBox(height: 10),

        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: onFlag,
                icon: const Icon(Icons.flag_outlined, size: 18, color: kAmber),
                label: const Text('Flag Review', style: TextStyle(color: kAmber)),
                style: OutlinedButton.styleFrom(
                  side: BorderSide(color: kAmber.withOpacity(0.4)),
                  minimumSize: const Size(0, 48),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: ElevatedButton.icon(
                onPressed: doc.isComplete ? onApprove : null,
                icon: const Icon(Icons.check_circle_outline, size: 18),
                label: const Text('Approve'),
                style: ElevatedButton.styleFrom(
                  minimumSize: const Size(0, 48),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
