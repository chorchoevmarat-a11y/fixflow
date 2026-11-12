import 'dart:convert';
import 'package:drift/drift.dart';
import '../../core/api_client.dart';
import '../../core/database.dart';
import '../sync/offline_queue_manager.dart';

class JobModel {
  final String id;
  final String title;
  final String description;
  final String status;
  final String priority;
  final String customerId;
  final String customerName;
  final String locationAddress;
  final String assignedTechnicianId;
  final DateTime? scheduledStart;
  final DateTime? scheduledEnd;
  final DateTime? slaDeadline;
  final Map<String, dynamic> rawData;

  JobModel({
    required this.id,
    required this.title,
    required this.description,
    required this.status,
    required this.priority,
    required this.customerId,
    required this.customerName,
    required this.locationAddress,
    required this.assignedTechnicianId,
    this.scheduledStart,
    this.scheduledEnd,
    this.slaDeadline,
    this.rawData = const {},
  });

  factory JobModel.fromJson(Map<String, dynamic> json) {
    return JobModel(
      id: json['id'] as String,
      title: json['title'] as String? ?? 'Untitled Job',
      description: json['description'] as String? ?? '',
      status: json['status'] as String? ?? 'assigned',
      priority: json['priority'] as String? ?? 'medium',
      customerId: json['customer_id'] as String? ?? '',
      customerName: json['customer_name'] as String? ?? 'Unknown Customer',
      locationAddress: json['location_address'] as String? ?? 'No address provided',
      assignedTechnicianId: json['assigned_technician_id'] as String? ?? '',
      scheduledStart: json['scheduled_start'] != null
          ? DateTime.tryParse(json['scheduled_start'] as String)
          : null,
      scheduledEnd: json['scheduled_end'] != null
          ? DateTime.tryParse(json['scheduled_end'] as String)
          : null,
      slaDeadline: json['sla_deadline'] != null
          ? DateTime.tryParse(json['sla_deadline'] as String)
          : null,
      rawData: json,
    );
  }

  factory JobModel.fromDb(CachedJob dbJob) {
    Map<String, dynamic> raw = {};
    try {
      raw = jsonDecode(dbJob.rawJson) as Map<String, dynamic>;
    } catch (_) {}

    return JobModel(
      id: dbJob.id,
      title: dbJob.title,
      description: dbJob.description,
      status: dbJob.status,
      priority: dbJob.priority,
      customerId: dbJob.customerId,
      customerName: dbJob.customerName,
      locationAddress: dbJob.locationAddress,
      assignedTechnicianId: dbJob.assignedTechnicianId,
      scheduledStart: dbJob.scheduledStart,
      scheduledEnd: dbJob.scheduledEnd,
      slaDeadline: dbJob.slaDeadline,
      rawData: raw,
    );
  }

  JobModel copyWith({
    String? status,
    String? title,
    String? description,
    String? priority,
  }) {
    return JobModel(
      id: id,
      title: title ?? this.title,
      description: description ?? this.description,
      status: status ?? this.status,
      priority: priority ?? this.priority,
      customerId: customerId,
      customerName: customerName,
      locationAddress: locationAddress,
      assignedTechnicianId: assignedTechnicianId,
      scheduledStart: scheduledStart,
      scheduledEnd: scheduledEnd,
      slaDeadline: slaDeadline,
      rawData: rawData,
    );
  }
}

class JobsRepository {
  final ApiClient _client;
  final AppDatabase _db;
  final OfflineQueueManager _queue;

  JobsRepository(this._client, this._db, this._queue);

  /// Fetch jobs with local cache fallback
  Future<List<JobModel>> getJobs() async {
    try {
      final response = await _client.get<List<dynamic>>('/jobs');
      final jobs = (response.data ?? [])
          .map((item) => JobModel.fromJson(item as Map<String, dynamic>))
          .toList();

      // Cache locally
      for (final job in jobs) {
        await _db.upsertJob(
          CachedJobsCompanion.insert(
            id: job.id,
            title: job.title,
            description: job.description,
            status: job.status,
            priority: job.priority,
            customerId: job.customerId,
            customerName: job.customerName,
            locationAddress: job.locationAddress,
            assignedTechnicianId: job.assignedTechnicianId,
            scheduledStart: Value(job.scheduledStart),
            scheduledEnd: Value(job.scheduledEnd),
            slaDeadline: Value(job.slaDeadline),
            rawJson: jsonEncode(job.rawData),
            cachedAt: Value(DateTime.now()),
          ),
        );
      }
      return jobs;
    } catch (_) {
      // Offline fallback: load from Drift
      final cached = await _db.getAllJobs();
      return cached.map(JobModel.fromDb).toList();
    }
  }

  /// Get specific job detail
  Future<JobModel?> getJob(String jobId) async {
    try {
      final response = await _client.get<Map<String, dynamic>>('/jobs/$jobId');
      final job = JobModel.fromJson(response.data!);
      await _db.upsertJob(
        CachedJobsCompanion.insert(
          id: job.id,
          title: job.title,
          description: job.description,
          status: job.status,
          priority: job.priority,
          customerId: job.customerId,
          customerName: job.customerName,
          locationAddress: job.locationAddress,
          assignedTechnicianId: job.assignedTechnicianId,
          scheduledStart: Value(job.scheduledStart),
          scheduledEnd: Value(job.scheduledEnd),
          slaDeadline: Value(job.slaDeadline),
          rawJson: jsonEncode(job.rawData),
          cachedAt: Value(DateTime.now()),
        ),
      );
      return job;
    } catch (_) {
      final cached = await _db.getJobById(jobId);
      return cached != null ? JobModel.fromDb(cached) : null;
    }
  }

  /// Transition job status (optimistic local update + queue if offline)
  Future<void> updateJobStatus({
    required String jobId,
    required String nextStatus,
    String? note,
  }) async {
    // 1. Optimistically update local cache
    final local = await _db.getJobById(jobId);
    if (local != null) {
      await _db.upsertJob(
        CachedJobsCompanion(
          id: Value(local.id),
          title: Value(local.title),
          description: Value(local.description),
          status: Value(nextStatus),
          priority: Value(local.priority),
          customerId: Value(local.customerId),
          customerName: Value(local.customerName),
          locationAddress: Value(local.locationAddress),
          assignedTechnicianId: Value(local.assignedTechnicianId),
          scheduledStart: Value(local.scheduledStart),
          scheduledEnd: Value(local.scheduledEnd),
          slaDeadline: Value(local.slaDeadline),
          rawJson: Value(local.rawJson),
          cachedAt: Value(DateTime.now()),
        ),
      );
    }

    // 2. Try online API call
    try {
      await _client.post(
        '/jobs/$jobId/status',
        data: {'status': nextStatus, if (note != null) 'note': note},
      );
    } catch (_) {
      // 3. Queue command offline
      await _queue.enqueueCommand(
        commandType: 'update_status',
        jobId: jobId,
        payload: {'status': nextStatus, if (note != null) 'note': note},
      );
    }
  }
}
