import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/router.dart';
import '../../shared/widgets/connectivity_banner.dart';
import '../../shared/widgets/loading_states.dart';
import '../../shared/widgets/sla_indicator.dart';
import '../sync/offline_queue_manager.dart';
import '../sync/sync_service.dart';
import 'jobs_notifier.dart';
import 'jobs_repository.dart';

class JobsScreen extends ConsumerStatefulWidget {
  const JobsScreen({super.key});

  @override
  ConsumerState<JobsScreen> createState() => _JobsScreenState();
}

class _JobsScreenState extends ConsumerState<JobsScreen> {
  final List<String> _filters = [
    'all',
    'assigned',
    'en_route',
    'in_progress',
    'on_hold',
    'completed',
  ];

  @override
  Widget build(BuildContext context) {
    final jobsState = ref.watch(jobsNotifierProvider);
    final syncStatusAsync = ref.watch(syncStatusProvider);
    final pendingCount = syncStatusAsync.value?.pendingCount ?? 0;
    final isSyncing = syncStatusAsync.value?.isSyncing ?? false;

    return Scaffold(
      appBar: AppBar(
        title: const Text('My Assignments'),
        actions: [
          IconButton(
            icon: isSyncing
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
            onPressed: () {
              ref.read(jobsNotifierProvider.notifier).loadJobs();
              ref.read(syncServiceProvider).replayQueue();
            },
            tooltip: 'Refresh & Sync',
          ),
        ],
      ),
      body: Column(
        children: [
          ConnectivityBanner(
            isOffline: false,
            pendingSyncCount: pendingCount,
            onSyncNow: () => ref.read(syncServiceProvider).replayQueue(),
          ),
          _buildFilterBar(jobsState.filterStatus ?? 'all'),
          Expanded(
            child: _buildContent(jobsState),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterBar(String activeFilter) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: _filters.map((filter) {
          final isSelected = activeFilter == filter;
          final label = filter == 'all'
              ? 'All'
              : filter.replaceAll('_', ' ').toUpperCase();
          return Padding(
            padding: const EdgeInsets.only(right: 8.0),
            child: FilterChip(
              label: Text(label),
              selected: isSelected,
              onSelected: (_) {
                ref.read(jobsNotifierProvider.notifier).setFilter(filter);
              },
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildContent(JobsState state) {
    if (state.isLoading && state.jobs.isEmpty) {
      return const LoadingView(message: 'Loading assigned jobs...');
    }

    if (state.errorMessage != null && state.jobs.isEmpty) {
      return ErrorView(
        message: state.errorMessage!,
        onRetry: () => ref.read(jobsNotifierProvider.notifier).loadJobs(),
      );
    }

    final filtered = state.filteredJobs;
    if (filtered.isEmpty) {
      return RefreshIndicator(
        onRefresh: () => ref.read(jobsNotifierProvider.notifier).loadJobs(),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: const [
            SizedBox(height: 80),
            EmptyView(
              title: 'No Jobs Found',
              subtitle: 'You have no assigned jobs in this status.',
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: () => ref.read(jobsNotifierProvider.notifier).loadJobs(),
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: filtered.length,
        separatorBuilder: (_, __) => const SizedBox(height: 12),
        itemBuilder: (context, index) {
          final job = filtered[index];
          return _buildJobCard(context, job);
        },
      ),
    );
  }

  Widget _buildJobCard(BuildContext context, JobModel job) {
    final theme = Theme.of(context);
    final isCompleted = job.status.toLowerCase() == 'completed';

    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => context.push('${AppRoutes.jobs}/${job.id}'),
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildPriorityBadge(job.priority),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      job.title,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 8),
                  _buildStatusBadge(job.status),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(Icons.person_outline, size: 16, color: theme.colorScheme.onSurfaceVariant),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      job.customerName,
                      style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w500),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Icon(Icons.location_on_outlined, size: 16, color: theme.colorScheme.onSurfaceVariant),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      job.locationAddress,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  SlaIndicator(
                    slaDeadline: job.slaDeadline,
                    isCompleted: isCompleted,
                  ),
                  const Icon(Icons.chevron_right, size: 20, color: Colors.grey),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPriorityBadge(String priority) {
    Color color;
    switch (priority.toLowerCase()) {
      case 'urgent':
        color = Colors.red;
        break;
      case 'high':
        color = Colors.deepOrange;
        break;
      case 'medium':
        color = Colors.amber.shade800;
        break;
      default:
        color = Colors.grey;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        priority.toUpperCase(),
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.bold,
          color: color,
        ),
      ),
    );
  }

  Widget _buildStatusBadge(String status) {
    Color bg;
    Color fg;
    switch (status.toLowerCase()) {
      case 'completed':
        bg = Colors.green.shade50;
        fg = Colors.green.shade800;
        break;
      case 'in_progress':
        bg = Colors.blue.shade50;
        fg = Colors.blue.shade800;
        break;
      case 'en_route':
        bg = Colors.purple.shade50;
        fg = Colors.purple.shade800;
        break;
      case 'on_hold':
        bg = Colors.orange.shade50;
        fg = Colors.orange.shade900;
        break;
      default:
        bg = Colors.grey.shade100;
        fg = Colors.grey.shade800;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        status.replaceAll('_', ' ').toUpperCase(),
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: fg,
        ),
      ),
    );
  }
}
