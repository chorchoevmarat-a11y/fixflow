import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../core/router.dart';
import '../../shared/widgets/loading_states.dart';
import '../../shared/widgets/sla_indicator.dart';
import 'jobs_notifier.dart';
import 'jobs_repository.dart';
import 'status_actions_widget.dart';

class JobDetailScreen extends ConsumerStatefulWidget {
  final String jobId;

  const JobDetailScreen({super.key, required this.jobId});

  @override
  ConsumerState<JobDetailScreen> createState() => _JobDetailScreenState();
}

class _JobDetailScreenState extends ConsumerState<JobDetailScreen> {
  @override
  Widget build(BuildContext context) {
    final jobAsync = ref.watch(jobDetailProvider(widget.jobId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Job Details'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              ref.invalidate(jobDetailProvider(widget.jobId));
            },
          ),
        ],
      ),
      body: jobAsync.when(
        loading: () => const LoadingView(message: 'Loading job details...'),
        error: (err, _) => ErrorView(
          message: err.toString(),
          onRetry: () => ref.invalidate(jobDetailProvider(widget.jobId)),
        ),
        data: (job) {
          if (job == null) {
            return const EmptyView(
              title: 'Job Not Found',
              subtitle: 'This job could not be retrieved from the server or offline storage.',
            );
          }
          return _buildDetailContent(context, job);
        },
      ),
    );
  }

  Widget _buildDetailContent(BuildContext context, JobModel job) {
    final theme = Theme.of(context);
    final dateFormat = DateFormat('MMM dd, yyyy - hh:mm a');

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      _buildBadge(job.priority.toUpperCase(), Colors.orange),
                      _buildBadge(job.status.replaceAll('_', ' ').toUpperCase(), Colors.blue),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    job.title,
                    style: theme.textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  SlaIndicator(
                    slaDeadline: job.slaDeadline,
                    isCompleted: job.status.toLowerCase() == 'completed',
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Status Transition Actions
          StatusActionsWidget(
            currentStatus: job.status,
            onTransition: (nextStatus) async {
              await ref.read(jobsNotifierProvider.notifier).updateStatus(
                    jobId: job.id,
                    nextStatus: nextStatus,
                  );
              ref.invalidate(jobDetailProvider(widget.jobId));
              if (mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('Status updated to ${nextStatus.replaceAll('_', ' ')}')),
                );
              }
            },
            onAddNote: () => context.push('${AppRoutes.jobs}/${job.id}/note'),
            onLogMaterials: () => context.push('${AppRoutes.jobs}/${job.id}/materials'),
          ),
          const SizedBox(height: 16),

          // Customer & Location Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Customer & Location',
                    style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const Divider(),
                  const SizedBox(height: 8),
                  _buildInfoRow(Icons.person, 'Customer', job.customerName),
                  const SizedBox(height: 12),
                  _buildInfoRow(Icons.location_on, 'Location', job.locationAddress),
                  if (job.scheduledStart != null) ...[
                    const SizedBox(height: 12),
                    _buildInfoRow(
                      Icons.calendar_today,
                      'Scheduled Window',
                      '${dateFormat.format(job.scheduledStart!)} - ${job.scheduledEnd != null ? dateFormat.format(job.scheduledEnd!) : 'Open'}',
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Description Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Description',
                    style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const Divider(),
                  const SizedBox(height: 8),
                  Text(
                    job.description.isNotEmpty ? job.description : 'No additional description provided.',
                    style: theme.textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  Widget _buildInfoRow(IconData icon, String label, String value) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 20, color: Colors.grey.shade600),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: const TextStyle(fontSize: 12, color: Colors.grey, fontWeight: FontWeight.w500),
              ),
              const SizedBox(height: 2),
              Text(
                value,
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildBadge(String label, MaterialColor color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.shade50,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.shade200),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.bold,
          color: color.shade800,
        ),
      ),
    );
  }
}
