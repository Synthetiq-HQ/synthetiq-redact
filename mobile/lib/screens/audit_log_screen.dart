import 'package:flutter/material.dart';
import '../theme.dart';
import '../models/document.dart';
import '../services/api_service.dart';
import 'document_detail_screen.dart';

class AuditLogScreen extends StatefulWidget {
  const AuditLogScreen({super.key});
  @override
  State<AuditLogScreen> createState() => _AuditLogScreenState();
}

class _AuditLogScreenState extends State<AuditLogScreen> {
  List<Document> _docs = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final docs = await ApiService().listDocuments();
      if (mounted) setState(() { _docs = docs; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  // Build a flat activity list from documents
  List<_LogEntry> get _entries {
    final entries = <_LogEntry>[];
    for (final doc in _docs) {
      entries.add(_LogEntry(
        docId: doc.id,
        filename: doc.filename,
        action: doc.displayStatus,
        detail: doc.department ?? doc.displayCategory,
        status: doc.status,
        timestamp: doc.createdAt,
      ));
    }
    return entries;
  }

  @override
  Widget build(BuildContext context) {
    final entries = _entries;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Activity Log'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_outlined, color: kTextSecondary),
            onPressed: _load,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: kPrimary))
          : entries.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.history_outlined, color: kTextSecondary, size: 48),
                      const SizedBox(height: 12),
                      const Text('No activity yet', style: TextStyle(color: kTextSecondary)),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  color: kPrimary,
                  child: ListView.builder(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                    itemCount: entries.length,
                    itemBuilder: (ctx, i) {
                      final e = entries[i];
                      final showDate = i == 0 ||
                          _datePart(entries[i - 1].timestamp) != _datePart(e.timestamp);

                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (showDate) ...[
                            if (i > 0) const SizedBox(height: 8),
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 8),
                              child: Text(
                                _datePart(e.timestamp),
                                style: const TextStyle(
                                  color: kTextSecondary,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: 1.1,
                                ),
                              ),
                            ),
                          ],
                          _LogEntryTile(
                            entry: e,
                            onTap: () => Navigator.push(
                              ctx,
                              MaterialPageRoute(
                                builder: (_) => DocumentDetailScreen(docId: e.docId),
                              ),
                            ),
                          ),
                          const SizedBox(height: 8),
                        ],
                      );
                    },
                  ),
                ),
    );
  }

  String _datePart(String? ts) {
    if (ts == null) return 'TODAY';
    try {
      final dt = DateTime.parse(ts).toLocal();
      final now = DateTime.now();
      if (dt.day == now.day && dt.month == now.month && dt.year == now.year) return 'TODAY';
      if (dt.day == now.day - 1 && dt.month == now.month) return 'YESTERDAY';
      return '${dt.day}/${dt.month}/${dt.year}';
    } catch (_) {
      return 'TODAY';
    }
  }
}

class _LogEntry {
  final int docId;
  final String filename;
  final String action;
  final String detail;
  final String status;
  final String? timestamp;

  const _LogEntry({
    required this.docId,
    required this.filename,
    required this.action,
    required this.detail,
    required this.status,
    this.timestamp,
  });
}

class _LogEntryTile extends StatelessWidget {
  final _LogEntry entry;
  final VoidCallback onTap;
  const _LogEntryTile({required this.entry, required this.onTap});

  Color get _dotColor {
    switch (entry.status) {
      case 'complete': return kPrimary;
      case 'needs_review': return kAmber;
      case 'error': return kRed;
      default: return kBlue;
    }
  }

  String get _timeStr {
    if (entry.timestamp == null) return '';
    try {
      final dt = DateTime.parse(entry.timestamp!).toLocal();
      final h = dt.hour.toString().padLeft(2, '0');
      final m = dt.minute.toString().padLeft(2, '0');
      return '$h:$m';
    } catch (_) {
      return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Timeline dot
          Column(
            children: [
              Container(
                width: 10,
                height: 10,
                margin: const EdgeInsets.only(top: 4),
                decoration: BoxDecoration(color: _dotColor, shape: BoxShape.circle),
              ),
              Container(width: 2, height: 40, color: kBorder),
            ],
          ),
          const SizedBox(width: 12),

          // Content
          Expanded(
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: kSurface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: kBorder),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          entry.action,
                          style: TextStyle(
                            color: _dotColor,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          entry.filename,
                          style: const TextStyle(color: kTextPrimary, fontSize: 13),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 2),
                        Text(entry.detail, style: const TextStyle(color: kTextSecondary, fontSize: 12)),
                      ],
                    ),
                  ),
                  Text(_timeStr, style: const TextStyle(color: kTextSecondary, fontSize: 11)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
