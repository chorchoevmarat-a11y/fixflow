import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../core/database.dart';
import '../sync/offline_queue_manager.dart';
import 'jobs_repository.dart';

final jobsRepositoryProvider = Provider<JobsRepository>((ref) {
  final client = ref.watch(apiClientProvider);
  final db = ref.watch(databaseProvider);
  final queue = ref.watch(offlineQueueManagerProvider);
  return JobsRepository(client, db, queue);
});

class JobsState {
  final bool isLoading;
  final List<JobModel> jobs;
  final String? errorMessage;
  final String? filterStatus;

  const JobsState({
    this.isLoading = false,
    this.jobs = const [],
    this.errorMessage,
    this.filterStatus,
  });

  JobsState copyWith({
    bool? isLoading,
    List<JobModel>? jobs,
    String? errorMessage,
    String? filterStatus,
  }) {
    return JobsState(
      isLoading: isLoading ?? this.isLoading,
      jobs: jobs ?? this.jobs,
      errorMessage: errorMessage,
      filterStatus: filterStatus ?? this.filterStatus,
    );
  }

  List<JobModel> get filteredJobs {
    if (filterStatus == null || filterStatus == 'all') {
      return jobs;
    }
    return jobs.where((j) => j.status == filterStatus).toList();
  }
}

class JobsNotifier extends StateNotifier<JobsState> {
  final JobsRepository _repository;

  JobsNotifier(this._repository) : super(const JobsState(isLoading: true)) {
    loadJobs();
  }

  Future<void> loadJobs() async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      final list = await _repository.getJobs();
      state = state.copyWith(isLoading: false, jobs: list);
    } catch (e) {
      state = state.copyWith(isLoading: false, errorMessage: e.toString());
    }
  }

  void setFilter(String? status) {
    state = state.copyWith(filterStatus: status);
  }

  Future<void> updateStatus({
    required String jobId,
    required String nextStatus,
    String? note,
  }) async {
    // Optimistic update in state list
    final updatedList = state.jobs.map((j) {
      if (j.id == jobId) {
        return j.copyWith(status: nextStatus);
      }
      return j;
    }).toList();
    state = state.copyWith(jobs: updatedList);

    await _repository.updateJobStatus(
      jobId: jobId,
      nextStatus: nextStatus,
      note: note,
    );
  }
}

final jobsNotifierProvider =
    StateNotifierProvider<JobsNotifier, JobsState>((ref) {
  final repo = ref.watch(jobsRepositoryProvider);
  return JobsNotifier(repo);
});

final jobDetailProvider =
    FutureProvider.family<JobModel?, String>((ref, jobId) async {
  final repo = ref.watch(jobsRepositoryProvider);
  return repo.getJob(jobId);
});
