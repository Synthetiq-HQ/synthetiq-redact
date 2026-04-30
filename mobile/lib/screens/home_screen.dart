import 'package:flutter/material.dart';
import '../theme.dart';
import '../models/document.dart';
import '../services/api_service.dart';
import '../widgets/document_card.dart';
import 'document_detail_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<Document> _docs = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final docs = await ApiService().listDocuments();
      if (mounted) setState(() { _docs = docs; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  int get _total => _docs.length;
  int get _complete => _docs.where((d) => d.isComplete).length;
  int get _pending => _docs.where((d) => d.needsReview).length;

  @override
  Widget build(BuildContext context) {
    final recent = _docs.take(5).toList();

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: kPrimary.withOpacity(0.15),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.shield_outlined, color: kPrimary, size: 18),
            ),
            const SizedBox(width: 10),
            const Text('ClearDoc'),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_outlined, color: kTextSecondary),
            onPressed: _load,
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        color: kPrimary,
        child: _loading
            ? const Center(child: CircularProgressIndicator(color: kPrimary))
            : _error != null
                ? _ErrorView(error: _error!, onRetry: _load)
                : ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      // Greeting
                      const Text(
                        'Good morning, Officer',
                        style: TextStyle(
                          color: kTextPrimary,
                          fontSize: 22,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Hillingdon Council Document Processing',
                        style: TextStyle(color: kTextSecondary, fontSize: 13),
                      ),
                      const SizedBox(height: 20),

                      // Stats row
                      Row(
                        children: [
                          Expanded(child: _StatCard(label: 'Total Docs', value: '$_total', icon: Icons.folder_outlined, color: kBlue)),
                          const SizedBox(width: 10),
                          Expanded(child: _StatCard(label: 'Needs Review', value: '$_pending', icon: Icons.rate_review_outlined, color: kAmber)),
                          const SizedBox(width: 10),
                          Expanded(child: _StatCard(label: 'Complete', value: '$_complete', icon: Icons.check_circle_outline, color: kPrimary)),
                        ],
                      ),
                      const SizedBox(height: 24),

                      // Quick actions
                      const Text(
                        'QUICK ACTIONS',
                        style: TextStyle(color: kTextSecondary, fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 1.2),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: _ActionButton(
                              icon: Icons.document_scanner_outlined,
                              label: 'Scan Document',
                              color: kPrimary,
                              onTap: () {},
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: _ActionButton(
                              icon: Icons.upload_file_outlined,
                              label: 'View All Docs',
                              color: kSurface2,
                              textColor: kTextPrimary,
                              onTap: () {},
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 28),

                      // Recent docs
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'RECENT DOCUMENTS',
                            style: TextStyle(color: kTextSecondary, fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 1.2),
                          ),
                          if (_total > 5)
                            TextButton(
                              onPressed: () {},
                              child: const Text('See all', style: TextStyle(color: kPrimary, fontSize: 13)),
                            ),
                        ],
                      ),
                      const SizedBox(height: 10),

                      if (recent.isEmpty)
                        _EmptyDocs()
                      else
                        ...recent.map((doc) => Padding(
                              padding: const EdgeInsets.only(bottom: 10),
                              child: DocumentCard(
                                doc: doc,
                                onTap: () => Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => DocumentDetailScreen(docId: doc.id),
                                  ),
                                ),
                              ),
                            )),
                    ],
                  ),
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  const _StatCard({required this.label, required this.value, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) {
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
          Icon(icon, color: color, size: 22),
          const SizedBox(height: 8),
          Text(value, style: TextStyle(color: color, fontSize: 24, fontWeight: FontWeight.w800)),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(color: kTextSecondary, fontSize: 11)),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final Color textColor;
  final VoidCallback onTap;

  const _ActionButton({
    required this.icon,
    required this.label,
    required this.color,
    this.textColor = Colors.white,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          children: [
            Icon(icon, color: textColor, size: 26),
            const SizedBox(height: 8),
            Text(label, style: TextStyle(color: textColor, fontSize: 13, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final String error;
  final VoidCallback onRetry;
  const _ErrorView({required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.wifi_off_outlined, color: kTextSecondary, size: 48),
            const SizedBox(height: 16),
            const Text('Cannot reach backend', style: TextStyle(color: kTextPrimary, fontSize: 16, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Text(error, style: const TextStyle(color: kTextSecondary, fontSize: 13), textAlign: TextAlign.center),
            const SizedBox(height: 24),
            ElevatedButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}

class _EmptyDocs extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: kBorder),
      ),
      child: Column(
        children: [
          const Icon(Icons.inbox_outlined, color: kTextSecondary, size: 40),
          const SizedBox(height: 12),
          const Text('No documents yet', style: TextStyle(color: kTextPrimary, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          const Text('Upload your first document using Scan', style: TextStyle(color: kTextSecondary, fontSize: 13)),
        ],
      ),
    );
  }
}
