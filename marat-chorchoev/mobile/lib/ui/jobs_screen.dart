import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../core/providers.dart';
import 'job_detail_screen.dart';
import 'unsent_notes_screen.dart';
import 'widgets.dart';

class JobsScreen extends ConsumerStatefulWidget {
  const JobsScreen({super.key});

  @override
  ConsumerState<JobsScreen> createState() => _JobsScreenState();
}

class _JobsScreenState extends ConsumerState<JobsScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      ref.read(jobsProvider.notifier).refresh();
      ref.read(queueProvider.notifier).syncNow();
    });
  }

  @override
  Widget build(BuildContext context) {
    final jobs = ref.watch(jobsProvider);
    final queue = ref.watch(queueProvider);
    final online = ref.watch(onlineProvider);
    final error = jobs.error;

    Widget body;
    if (jobs.jobs.isEmpty && jobs.loading) {
      body = const Center(child: CircularProgressIndicator());
    } else if (jobs.jobs.isEmpty && error != null) {
      body = StateMessage.forError(error,
          onRetry: () => ref.read(jobsProvider.notifier).refresh());
    } else if (jobs.jobs.isEmpty) {
      body = ListView(children: const [
        SizedBox(height: 120),
        StateMessage(
          icon: Icons.inbox_outlined,
          title: 'No assigned jobs',
          message: 'New assignments from the dispatcher appear here.',
        ),
      ]);
    } else {
      body = ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: jobs.jobs.length,
        itemBuilder: (context, index) {
          final job = jobs.jobs[index];
          return JobCard(
            job: job,
            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => JobDetailScreen(jobId: job.id))),
          );
        },
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('My jobs'),
        actions: [
          if (queue.notes.isNotEmpty)
            IconButton(
              tooltip: 'Unsent notes',
              icon: Badge(
                  label: Text('${queue.notes.length}'),
                  child: const Icon(Icons.outbox)),
              onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                      builder: (_) => const UnsentNotesScreen())),
            ),
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed:
                online ? () => ref.read(jobsProvider.notifier).refresh() : null,
          ),
        ],
      ),
      body: Column(
        children: [
          const StatusBanner(),
          if (jobs.lastSync != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 6, 16, 0),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Last synchronized ${DateFormat('d MMM HH:mm').format(jobs.lastSync!.toLocal())}'
                  '${error != null && jobs.jobs.isNotEmpty ? ' · ${error.isNetwork ? 'offline' : error.message}' : ''}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => ref.read(jobsProvider.notifier).refresh(),
              child: body,
            ),
          ),
        ],
      ),
    );
  }
}
