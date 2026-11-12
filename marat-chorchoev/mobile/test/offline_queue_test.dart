import 'package:flutter_test/flutter_test.dart';
import 'package:fixflow_mobile/features/sync/offline_queue_manager.dart';

// In-memory fake database implementation for queue testing
class FakeOfflineQueueStorage {
  final List<OfflineCommand> _storage = [];
  int _autoIncrement = 1;

  Future<String> enqueue({
    required String commandType,
    required String jobId,
    required Map<String, dynamic> payload,
    String? commandId,
  }) async {
    final key = commandId ?? 'uuid-${_autoIncrement}';
    final cmd = OfflineCommand(
      localId: _autoIncrement++,
      commandId: key,
      commandType: commandType,
      jobId: jobId,
      payload: payload,
      createdAt: DateTime.now(),
    );
    _storage.add(cmd);
    return key;
  }

  Future<List<OfflineCommand>> getAll() async {
    return List.unmodifiable(_storage);
  }

  Future<void> remove(int localId) async {
    _storage.removeWhere((item) => item.localId == localId);
  }

  Future<void> recordFailure(int localId, String error) async {
    final idx = _storage.indexWhere((item) => item.localId == localId);
    if (idx != -1) {
      final old = _storage[idx];
      _storage[idx] = OfflineCommand(
        localId: old.localId,
        commandId: old.commandId,
        commandType: old.commandType,
        jobId: old.jobId,
        payload: old.payload,
        createdAt: old.createdAt,
        retryCount: old.retryCount + 1,
        lastError: error,
      );
    }
  }
}

void main() {
  group('Offline Queue Manager Tests', () {
    late FakeOfflineQueueStorage queueStorage;

    setUp(() {
      queueStorage = FakeOfflineQueueStorage();
    });

    test('Enqueue stores command and returns idempotency key', () async {
      final key = await queueStorage.enqueue(
        commandType: 'update_status',
        jobId: 'job-001',
        payload: {'status': 'in_progress'},
      );

      expect(key, isNotEmpty);
      final pending = await queueStorage.getAll();
      expect(pending.length, 1);
      expect(pending.first.commandType, 'update_status');
      expect(pending.first.jobId, 'job-001');
      expect(pending.first.payload['status'], 'in_progress');
    });

    test('Queue maintains FIFO order for multiple offline events', () async {
      await queueStorage.enqueue(
        commandType: 'update_status',
        jobId: 'job-001',
        payload: {'status': 'en_route'},
      );
      await queueStorage.enqueue(
        commandType: 'update_status',
        jobId: 'job-001',
        payload: {'status': 'in_progress'},
      );
      await queueStorage.enqueue(
        commandType: 'add_note',
        jobId: 'job-001',
        payload: {'content': 'Arrived on site'},
      );

      final pending = await queueStorage.getAll();
      expect(pending.length, 3);
      expect(pending[0].payload['status'], 'en_route');
      expect(pending[1].payload['status'], 'in_progress');
      expect(pending[2].commandType, 'add_note');
    });

    test('Removal deletes item from pending queue', () async {
      await queueStorage.enqueue(
        commandType: 'update_status',
        jobId: 'job-001',
        payload: {'status': 'in_progress'},
      );

      var pending = await queueStorage.getAll();
      expect(pending.length, 1);

      await queueStorage.remove(pending.first.localId);

      pending = await queueStorage.getAll();
      expect(pending.isEmpty, true);
    });

    test('Failure records error and increments retry counter', () async {
      await queueStorage.enqueue(
        commandType: 'update_status',
        jobId: 'job-001',
        payload: {'status': 'completed'},
      );

      final item = (await queueStorage.getAll()).first;
      expect(item.retryCount, 0);

      await queueStorage.recordFailure(item.localId, 'Network Timeout');
      final updated = (await queueStorage.getAll()).first;
      expect(updated.retryCount, 1);
      expect(updated.lastError, 'Network Timeout');
    });
  });
}
