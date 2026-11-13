import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../core/models.dart';
import '../core/providers.dart';
import 'widgets.dart';

/// Every queued note with its delivery state and the recovery choices (MOB-05 / MOB-07).
class UnsentNotesScreen extends ConsumerWidget {
  const UnsentNotesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final queue = ref.watch(queueProvider);
    final online = ref.watch(onlineProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Unsent notes')),
      body: Column(
        children: [
          const StatusBanner(),
          Expanded(
            child: queue.notes.isEmpty
                ? const StateMessage(
                    icon: Icons.check_circle_outline,
                    title: 'Everything is synced')
                : ListView(
                    padding: const EdgeInsets.all(12),
                    children: [
                      for (final n in queue.notes)
                        _NoteTile(note: n, online: online)
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}

class _NoteTile extends ConsumerWidget {
  const _NoteTile({required this.note, required this.online});

  final QueuedNote note;
  final bool online;

  Future<void> _confirmDiscard(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Discard this note?'),
        content: const Text(
            'The text and photos are deleted from this phone. This cannot be undone.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Keep it')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Discard')),
        ],
      ),
    );
    if (ok == true) await ref.read(queueProvider.notifier).discard(note.id);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final (label, color) = switch (note.state) {
      QueueState.pending => (
          online ? 'Pending sync' : 'Pending sync — offline',
          null
        ),
      QueueState.syncing => ('Sending…', null),
      QueueState.conflict => ('Conflict', scheme.error),
      QueueState.failed => ('Failed', scheme.error),
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${note.reference} · ${note.title}',
                style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(note.body),
            const SizedBox(height: 6),
            Text(
              'Queued ${DateFormat('d MMM HH:mm').format(note.createdAt.toLocal())}'
              '${note.imagePaths.isEmpty ? '' : ' · ${note.imagePaths.length} photo(s)'}'
              ' · attempts ${note.attempts}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 6),
            Chip2(label, color: color),
            if (note.reason != null) ...[
              const SizedBox(height: 6),
              Text(note.reason!, style: TextStyle(color: scheme.error)),
            ],
            const SizedBox(height: 8),
            Wrap(spacing: 8, children: [
              if (note.state == QueueState.conflict ||
                  note.state == QueueState.failed)
                OutlinedButton(
                  onPressed: online
                      ? () => ref.read(queueProvider.notifier).retry(note.id)
                      : null,
                  child: const Text('Try again'),
                ),
              if (note.state == QueueState.pending && online)
                OutlinedButton(
                  onPressed: () => ref.read(queueProvider.notifier).syncNow(),
                  child: const Text('Retry now'),
                ),
              TextButton(
                  onPressed: () => _confirmDiscard(context, ref),
                  child: const Text('Discard')),
            ]),
          ],
        ),
      ),
    );
  }
}
