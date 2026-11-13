import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../core/models.dart';
import '../core/providers.dart';
import 'complete_screen.dart';
import 'materials_screen.dart';
import 'note_compose_screen.dart';
import 'widgets.dart';

class JobDetailScreen extends ConsumerStatefulWidget {
  const JobDetailScreen({super.key, required this.jobId});

  final String jobId;

  @override
  ConsumerState<JobDetailScreen> createState() => _JobDetailScreenState();
}

class _JobDetailScreenState extends ConsumerState<JobDetailScreen> {
  List<NoteItem> _notes = const [];
  String? _notesError;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    Future.microtask(_loadNotes);
  }

  Future<void> _loadNotes() async {
    try {
      final notes = await ref.read(apiProvider).notes(widget.jobId);
      if (mounted) setState(() => _notes = notes);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _notesError = e.isNetwork
            ? 'Notes need a connection. Your queued notes are listed below.'
            : e.message);
      }
    }
  }

  /// Online-only lifecycle command. The screen only changes after the server accepts it.
  Future<void> _run(String action,
      {Map<String, dynamic> body = const {}, String? success}) async {
    if (_busy) return;
    setState(() => _busy = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(apiProvider).transition(widget.jobId, action, body: body);
      ref.read(onlineProvider.notifier).report(true);
      if (action == 'decline') {
        await ref.read(jobsProvider.notifier).remove(widget.jobId);
        if (mounted) Navigator.of(context).pop();
      } else {
        final fresh = await ref.read(apiProvider).jobDetail(widget.jobId);
        await ref.read(jobsProvider.notifier).replace(fresh);
      }
      messenger.showSnackBar(SnackBar(content: Text(success ?? 'Done')));
    } on ApiException catch (e) {
      if (e.isNetwork) ref.read(onlineProvider.notifier).report(false);
      if (e.isUnauthorized) {
        await ref.read(sessionProvider.notifier).markExpired();
      }
      messenger.showSnackBar(SnackBar(
          content: Text(e.isNetwork
              ? 'No connection — nothing was changed.'
              : e.message)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _ask(String action, String title, String label,
      {String? success}) async {
    final controller = TextEditingController();
    final text = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 3,
          decoration: InputDecoration(labelText: label),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              if (controller.text.trim().length >= 3) {
                Navigator.pop(context, controller.text.trim());
              }
            },
            child: const Text('Confirm'),
          ),
        ],
      ),
    );
    if (text != null) {
      await _run(action,
          body: {action == 'unblock' ? 'resolution_note' : 'reason': text},
          success: success);
    }
  }

  @override
  Widget build(BuildContext context) {
    final jobs = ref.watch(jobsProvider);
    final online = ref.watch(onlineProvider);
    final queue = ref.watch(queueProvider);
    Job? job;
    for (final j in jobs.jobs) {
      if (j.id == widget.jobId) job = j;
    }
    if (job == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Job')),
        body: const StateMessage(
          icon: Icons.lock_outline,
          title: 'This job is no longer available',
          message: 'It was reassigned, closed, or removed from your list.',
        ),
      );
    }
    final j = job;
    final unsent = [
      for (final n in queue.notes)
        if (n.requestId == j.id) n
    ];
    const offlineHint = 'Needs a connection';

    Widget action(String label, bool allowed, VoidCallback run,
        {bool primary = false}) {
      final enabled = allowed && online && !_busy;
      final button = primary
          ? FilledButton(onPressed: enabled ? run : null, child: Text(label))
          : OutlinedButton(onPressed: enabled ? run : null, child: Text(label));
      return Tooltip(message: online ? '' : offlineHint, child: button);
    }

    return Scaffold(
      appBar: AppBar(title: Text(j.reference)),
      floatingActionButton: FloatingActionButton.extended(
        icon: const Icon(Icons.note_add_outlined),
        label: const Text('Add note'),
        onPressed: () => Navigator.of(context).push(
            MaterialPageRoute<void>(builder: (_) => NoteComposeScreen(job: j))),
      ),
      body: Column(
        children: [
          const StatusBanner(),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                await ref.read(jobsProvider.notifier).refresh();
                await _loadNotes();
              },
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
                children: [
                  JobCard(job: j),
                  const SizedBox(height: 8),
                  Text(j.description),
                  const SizedBox(height: 12),
                  _Facts(job: j),
                  if (j.blockerReason != null) ...[
                    const SizedBox(height: 8),
                    Text('Blocked: ${j.blockerReason}',
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error)),
                  ],
                  if (j.startBlockedReason != null) ...[
                    const SizedBox(height: 8),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Text(
                            'You cannot start yet: ${j.startBlockedReason}'),
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  Text('Actions',
                      style: Theme.of(context).textTheme.titleMedium),
                  if (!online)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 4),
                      child: Text(
                        'You are offline. Accepting, starting, completing and using materials need a connection — '
                        'they are not faked locally. You can still write notes and attach photos.',
                      ),
                    ),
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    action('Accept', j.can('accept'),
                        () => _run('accept', success: 'Job accepted'),
                        primary: true),
                    action('Start work', j.can('start'),
                        () => _run('start', success: 'Work started'),
                        primary: true),
                    action(
                        'Decline',
                        j.can('decline'),
                        () => _ask('decline', 'Decline this job?', 'Reason',
                            success: 'Job declined')),
                    action(
                        'Report blocker',
                        j.can('block'),
                        () => _ask('block', 'What is blocking the job?',
                            'Blocker reason',
                            success: 'Marked as blocked')),
                    action(
                        'Resume work',
                        j.can('unblock'),
                        () => _ask('unblock', 'How was it resolved?',
                            'Resolution note',
                            success: 'Work resumed')),
                    action(
                        'Use materials',
                        j.can('consume_material'),
                        () => Navigator.of(context).push(
                            MaterialPageRoute<void>(
                                builder: (_) => MaterialsScreen(job: j)))),
                    action(
                        'Complete job',
                        j.can('complete'),
                        () => Navigator.of(context).push(
                            MaterialPageRoute<void>(
                                builder: (_) => CompleteScreen(job: j))),
                        primary: true),
                  ]),
                  const SizedBox(height: 16),
                  Text('Notes', style: Theme.of(context).textTheme.titleMedium),
                  if (_notesError != null) Text(_notesError!),
                  for (final n in unsent)
                    Card(
                      color:
                          Theme.of(context).colorScheme.surfaceContainerHighest,
                      child: ListTile(
                        title: Text(n.body),
                        subtitle: Text(
                          switch (n.state) {
                            QueueState.conflict => 'Conflict — ${n.reason}',
                            QueueState.failed => 'Failed — ${n.reason}',
                            _ =>
                              'Pending sync · queued ${DateFormat('HH:mm').format(n.createdAt.toLocal())}'
                                  '${n.imagePaths.isEmpty ? '' : ' · ${n.imagePaths.length} photo(s)'}',
                          },
                        ),
                        leading: Icon(n.state == QueueState.conflict
                            ? Icons.warning_amber
                            : Icons.schedule_send),
                      ),
                    ),
                  for (final n in _notes)
                    Card(
                      child: ListTile(
                        title: Text(n.body),
                        subtitle: Text(
                            '${n.author} · ${DateFormat('d MMM HH:mm').format(n.createdAt)}${n.internal ? ' · internal' : ''}'),
                      ),
                    ),
                  if (_notes.isEmpty && unsent.isEmpty && _notesError == null)
                    const Text('No notes yet.'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Facts extends StatelessWidget {
  const _Facts({required this.job});

  final Job job;

  @override
  Widget build(BuildContext context) {
    final rows = <(String, String)>[
      ('Appointment', job.appointmentText),
      ('Address', '${job.propertyName}, ${job.address}'),
      if (job.accessNotes != null) ('Access', job.accessNotes!),
      ('Equipment', job.assetLabel),
      ('Category', job.categoryName),
      (
        'Estimated work',
        job.estimatedMinutes > 0 ? '${job.estimatedMinutes} min' : '—'
      ),
      (
        'Estimate',
        job.estimate == null
            ? 'None'
            : 'v${job.estimate!['version']} · ${humanize(job.estimate!['status'] as String)}'
      ),
      (
        'SLA due',
        job.slaDueAt == null
            ? 'Paused'
            : DateFormat('EEE d MMM HH:mm').format(job.slaDueAt!)
      ),
    ];
    return Column(
      children: [
        for (final (label, value) in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                    width: 120,
                    child: Text(label,
                        style: Theme.of(context).textTheme.bodySmall)),
                Expanded(child: Text(value)),
              ],
            ),
          ),
      ],
    );
  }
}
