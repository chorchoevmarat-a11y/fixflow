import 'package:flutter/material.dart';

enum SlaStatus { onTrack, atRisk, breached, completed }

class SlaIndicator extends StatelessWidget {
  final DateTime? slaDeadline;
  final bool isCompleted;

  const SlaIndicator({
    super.key,
    required this.slaDeadline,
    this.isCompleted = false,
  });

  SlaStatus get status {
    if (isCompleted) return SlaStatus.completed;
    if (slaDeadline == null) return SlaStatus.onTrack;

    final now = DateTime.now();
    final difference = slaDeadline!.difference(now);

    if (difference.isNegative) {
      return SlaStatus.breached;
    } else if (difference.inHours < 4) {
      return SlaStatus.atRisk;
    }
    return SlaStatus.onTrack;
  }

  @override
  Widget build(BuildContext context) {
    if (slaDeadline == null && !isCompleted) {
      return const SizedBox.shrink();
    }

    final theme = Theme.of(context);
    Color bgColor;
    Color fgColor;
    String label;
    IconData icon;

    switch (status) {
      case SlaStatus.completed:
        bgColor = Colors.green.shade50;
        fgColor = Colors.green.shade800;
        label = 'SLA Met';
        icon = Icons.check_circle_outline;
        break;
      case SlaStatus.breached:
        bgColor = Colors.red.shade50;
        fgColor = Colors.red.shade800;
        label = 'SLA Breached';
        icon = Icons.error_outline;
        break;
      case SlaStatus.atRisk:
        bgColor = Colors.orange.shade50;
        fgColor = Colors.orange.shade900;
        final diff = slaDeadline!.difference(DateTime.now());
        label = 'SLA Risk (${diff.inHours}h left)';
        icon = Icons.warning_amber_rounded;
        break;
      case SlaStatus.onTrack:
        bgColor = Colors.blue.shade50;
        fgColor = Colors.blue.shade800;
        final diff = slaDeadline!.difference(DateTime.now());
        final days = diff.inDays;
        label = days > 0 ? 'SLA: ${days}d left' : 'SLA: ${diff.inHours}h left';
        icon = Icons.schedule;
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: fgColor.withOpacity(0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: fgColor),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: fgColor,
            ),
          ),
        ],
      ),
    );
  }
}
