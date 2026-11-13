import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/models.dart';
import '../core/providers.dart';

/// One widget for every non-happy state: loading, empty, error, forbidden, expired.
class StateMessage extends StatelessWidget {
  const StateMessage({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.actionLabel,
    this.onAction,
  });

  final IconData icon;
  final String title;
  final String? message;
  final String? actionLabel;
  final VoidCallback? onAction;

  factory StateMessage.forError(ApiException error, {VoidCallback? onRetry}) {
    if (error.isNetwork) {
      return StateMessage(
        icon: Icons.cloud_off,
        title: 'You are offline',
        message: 'Showing the last synchronized data. ${error.message}',
        actionLabel: 'Try again',
        onAction: onRetry,
      );
    }
    if (error.isForbidden) {
      return const StateMessage(
        icon: Icons.lock_outline,
        title: 'Permission denied',
        message:
            'Your account is not allowed to see this. Ask a dispatcher if this looks wrong.',
      );
    }
    return StateMessage(
      icon: Icons.error_outline,
      title: 'Something went wrong',
      message: error.message,
      actionLabel: 'Try again',
      onAction: onRetry,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: Theme.of(context).colorScheme.outline),
            const SizedBox(height: 12),
            Text(title,
                style: Theme.of(context).textTheme.titleMedium,
                textAlign: TextAlign.center),
            if (message != null) ...[
              const SizedBox(height: 6),
              Text(message!, textAlign: TextAlign.center),
            ],
            if (actionLabel != null) ...[
              const SizedBox(height: 16),
              FilledButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}

/// Offline and queue status strip shown above the main screens.
class StatusBanner extends ConsumerWidget {
  const StatusBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final online = ref.watch(onlineProvider);
    final queue = ref.watch(queueProvider);
    final scheme = Theme.of(context).colorScheme;
    final parts = <String>[];
    if (!online) {
      parts.add('Offline — showing saved jobs. Notes you write are queued.');
    }
    if (queue.pending > 0) {
      parts.add('${queue.pending} note(s) waiting to sync');
    }
    if (queue.conflicts > 0) {
      parts.add('${queue.conflicts} note(s) need your decision');
    }
    if (queue.failed > 0) parts.add('${queue.failed} note(s) failed');
    if (parts.isEmpty) return const SizedBox.shrink();
    final urgent = queue.conflicts > 0 || queue.failed > 0;
    return Semantics(
      liveRegion: true,
      child: Material(
        color: urgent ? scheme.errorContainer : scheme.secondaryContainer,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              Icon(online ? Icons.sync : Icons.cloud_off, size: 18),
              const SizedBox(width: 8),
              Expanded(child: Text(parts.join(' · '))),
              if (!online)
                // A successful refresh flips the app back online, which also sends the queue.
                TextButton(
                    onPressed: () => ref.read(jobsProvider.notifier).refresh(),
                    child: const Text('Retry'))
              else if (queue.pending > 0 && !queue.syncing)
                TextButton(
                    onPressed: () => ref.read(queueProvider.notifier).syncNow(),
                    child: const Text('Sync now')),
              if (queue.syncing)
                const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Status chips always carry text, not just color (accessibility).
class Chip2 extends StatelessWidget {
  const Chip2(this.label, {super.key, this.color});
  final String label;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        border: Border.all(color: color ?? scheme.outline),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(label,
          style: TextStyle(fontSize: 12, color: color ?? scheme.onSurface)),
    );
  }
}

String humanize(String value) {
  final text = value.replaceAll('_', ' ').toLowerCase();
  return text.isEmpty ? text : text[0].toUpperCase() + text.substring(1);
}

/// A job in the inbox: appointment, address, asset, status and SLA at a glance.
class JobCard extends StatelessWidget {
  const JobCard({super.key, required this.job, this.onTap});

  final Job job;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final slaColor = switch (job.slaState) {
      'OVERDUE' => scheme.error,
      'AT_RISK' => const Color(0xFFE5B445),
      _ => null,
    };
    final slaLabel = switch (job.slaState) {
      'OVERDUE' => 'SLA overdue',
      'AT_RISK' => 'SLA at risk',
      _ => 'SLA on track',
    };
    return Card(
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${job.reference} · ${job.title}',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 6),
              Row(children: [
                const Icon(Icons.schedule, size: 16),
                const SizedBox(width: 6),
                Expanded(child: Text(job.appointmentText)),
              ]),
              Row(children: [
                const Icon(Icons.place_outlined, size: 16),
                const SizedBox(width: 6),
                Expanded(child: Text('${job.propertyName} — ${job.address}')),
              ]),
              if (job.asset != null)
                Row(children: [
                  const Icon(Icons.precision_manufacturing_outlined, size: 16),
                  const SizedBox(width: 6),
                  Expanded(child: Text(job.assetLabel)),
                ]),
              const SizedBox(height: 8),
              Wrap(spacing: 6, runSpacing: 4, children: [
                Chip2(humanize(job.status)),
                Chip2('${humanize(job.priority)} priority',
                    color: job.priority == 'HIGH' ? scheme.error : null),
                Chip2(slaLabel, color: slaColor),
                Chip2(job.categoryName),
              ]),
            ],
          ),
        ),
      ),
    );
  }
}
