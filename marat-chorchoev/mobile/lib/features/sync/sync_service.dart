import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../core/database.dart';
import 'offline_queue_manager.dart';

final syncServiceProvider = Provider<SyncService>((ref) {
  final client = ref.watch(apiClientProvider);
  final queue = ref.watch(offlineQueueManagerProvider);
  final db = ref.watch(databaseProvider);
  final service = SyncService(client, queue, db);
  service.init();
  ref.onDispose(() => service.dispose());
  return service;
});

final syncStatusProvider = StreamProvider<SyncStatusUpdate>((ref) {
  final service = ref.watch(syncServiceProvider);
  return service.statusStream;
});

class SyncStatusUpdate {
  final bool isSyncing;
  final int pendingCount;
  final String? lastError;
  final bool conflictDetected;

  SyncStatusUpdate({
    required this.isSyncing,
    required this.pendingCount,
    this.lastError,
    this.conflictDetected = false,
  });
}

class SyncService {
  final ApiClient _client;
  final OfflineQueueManager _queue;
  final AppDatabase _db;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;
  final _statusController = StreamController<SyncStatusUpdate>.broadcast();

  bool _isSyncing = false;
  bool get isSyncing => _isSyncing;

  Stream<SyncStatusUpdate> get statusStream => _statusController.stream;

  SyncService(this._client, this._queue, this._db);

  void init() {
    _connectivitySub = Connectivity().onConnectivityChanged.listen((results) {
      final isOnline = results.any((r) => r != ConnectivityResult.none);
      if (isOnline) {
        replayQueue();
      }
    });
  }

  void dispose() {
    _connectivitySub?.cancel();
    _statusController.close();
  }

  Future<void> replayQueue() async {
    if (_isSyncing) return;
    _isSyncing = true;
    _notifyStatus();

    try {
      final pendingList = await _queue.getPendingCommands();

      for (final command in pendingList) {
        try {
          await _executeCommand(command);
          await _queue.removeCommand(command.localId);
        } on DioException catch (dioErr) {
          if (dioErr.response?.statusCode == 409) {
            // Conflict detected!
            await _queue.recordFailure(command.localId, 'Conflict: 409 Conflict with server state');
            _notifyStatus(lastError: 'Conflict on command ${command.commandId}', conflict: true);
            // Leave command or skip to avoid blocking FIFO
            break;
          } else if (dioErr.response != null && dioErr.response!.statusCode! >= 400 && dioErr.response!.statusCode! < 500) {
            // Client error - likely invalid payload, remove so queue is not permanently blocked
            await _queue.removeCommand(command.localId);
          } else {
            // Network or server error - record failure and pause replay
            await _queue.recordFailure(command.localId, dioErr.message ?? 'Network error');
            break;
          }
        } catch (e) {
          await _queue.recordFailure(command.localId, e.toString());
          break;
        }
      }

      // Also sync any local un-synced notes
      await _syncLocalNotes();
    } finally {
      _isSyncing = false;
      _notifyStatus();
    }
  }

  Future<void> _executeCommand(OfflineCommand cmd) async {
    final options = Options(
      headers: {
        'X-Idempotency-Key': cmd.commandId,
      },
    );

    switch (cmd.commandType) {
      case 'update_status':
        await _client.dio.post(
          '/jobs/${cmd.jobId}/status',
          data: cmd.payload,
          options: options,
        );
        break;

      case 'add_note':
        await _client.dio.post(
          '/jobs/${cmd.jobId}/notes',
          data: cmd.payload,
          options: options,
        );
        break;

      case 'log_material':
        await _client.dio.post(
          '/jobs/${cmd.jobId}/materials',
          data: cmd.payload,
          options: options,
        );
        break;

      default:
        // Generic fallback route
        await _client.dio.post(
          '/jobs/${cmd.jobId}/commands',
          data: {
            'command': cmd.commandType,
            ...cmd.payload,
          },
          options: options,
        );
        break;
    }
  }

  Future<void> _syncLocalNotes() async {
    final unsynced = await _db.getUnsyncedNotes();
    for (final note in unsynced) {
      try {
        final res = await _client.dio.post(
          '/jobs/${note.jobId}/notes',
          data: {
            'content': note.content,
            'is_private': note.isPrivate == 1,
            'created_at': note.createdAt.toIso8601String(),
          },
          options: Options(headers: {'X-Idempotency-Key': note.id}),
        );
        final remoteId = (res.data is Map && res.data['id'] != null)
            ? res.data['id'].toString()
            : note.id;
        await _db.markNoteSynced(note.id, remoteId);
      } catch (_) {
        // Will retry next sync
      }
    }
  }

  Future<void> _notifyStatus({String? lastError, bool conflict = false}) async {
    final count = await _queue.getPendingCount();
    if (!_statusController.isClosed) {
      _statusController.add(
        SyncStatusUpdate(
          isSyncing: _isSyncing,
          pendingCount: count,
          lastError: lastError,
          conflictDetected: conflict,
        ),
      );
    }
  }
}
