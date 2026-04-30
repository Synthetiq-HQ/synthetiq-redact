import 'package:flutter/material.dart';
import '../models/document.dart';
import '../theme.dart';

class DocumentCard extends StatelessWidget {
  final Document doc;
  final VoidCallback? onTap;

  const DocumentCard({super.key, required this.doc, this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: doc.needsReview
                ? kAmber.withOpacity(0.4)
                : doc.hasError
                    ? kRed.withOpacity(0.4)
                    : kBorder,
          ),
        ),
        child: Row(
          children: [
            // File type icon
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: _statusColor.withOpacity(0.12),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(_fileIcon, color: _statusColor, size: 22),
            ),
            const SizedBox(width: 12),

            // Info
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    doc.filename,
                    style: const TextStyle(
                      color: kTextPrimary,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      _CategoryBadge(doc.displayCategory),
                      const SizedBox(width: 6),
                      _StatusBadge(doc),
                    ],
                  ),
                ],
              ),
            ),

            // Chevron
            const Icon(Icons.chevron_right, color: kTextSecondary, size: 20),
          ],
        ),
      ),
    );
  }

  IconData get _fileIcon {
    if (doc.hasError) return Icons.error_outline;
    if (doc.isProcessing) return Icons.hourglass_top_outlined;
    if (doc.needsReview) return Icons.rate_review_outlined;
    return Icons.description_outlined;
  }

  Color get _statusColor {
    if (doc.hasError) return kRed;
    if (doc.needsReview) return kAmber;
    if (doc.isProcessing) return kBlue;
    return kPrimary;
  }
}

class _CategoryBadge extends StatelessWidget {
  final String label;
  const _CategoryBadge(this.label);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: kSurface2,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: const TextStyle(color: kTextSecondary, fontSize: 11),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final Document doc;
  const _StatusBadge(this.doc);

  @override
  Widget build(BuildContext context) {
    Color color;
    if (doc.hasError) {
      color = kRed;
    } else if (doc.needsReview) {
      color = kAmber;
    } else if (doc.isProcessing) {
      color = kBlue;
    } else {
      color = kPrimary;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        doc.displayStatus,
        style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }
}
