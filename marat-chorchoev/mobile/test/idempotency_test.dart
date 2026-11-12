import 'package:flutter_test/flutter_test.dart';

class MockIdempotentServer {
  final Map<String, dynamic> _processedKeys = {};

  Map<String, dynamic> handleRequest({
    required String idempotencyKey,
    required String path,
    required Map<String, dynamic> body,
  }) {
    if (_processedKeys.containsKey(idempotencyKey)) {
      // Return cached response without re-executing
      return {
        'status_code': 200,
        'cached': true,
        'data': _processedKeys[idempotencyKey],
      };
    }

    // Process new command
    final result = {
      'id': 'result-for-${body['status'] ?? 'action'}',
      'job_id': body['job_id'],
      'processed_at': DateTime.now().toIso8601String(),
    };

    _processedKeys[idempotencyKey] = result;
    return {
      'status_code': 200,
      'cached': false,
      'data': result,
    };
  }

  int get executedCount => _processedKeys.length;
}

void main() {
  group('Idempotency & Duplicate Replay Tests', () {
    late MockIdempotentServer server;

    setUp(() {
      server = MockIdempotentServer();
    });

    test('Identical idempotency key prevents duplicate execution', () {
      const key = 'command-uuid-4455';
      final payload = {'job_id': 'job-10', 'status': 'completed'};

      // First replay attempt
      final response1 = server.handleRequest(
        idempotencyKey: key,
        path: '/jobs/job-10/status',
        body: payload,
      );

      expect(response1['cached'], false);
      expect(server.executedCount, 1);

      // Second replay attempt with identical key (e.g. after network retry or reconnection)
      final response2 = server.handleRequest(
        idempotencyKey: key,
        path: '/jobs/job-10/status',
        body: payload,
      );

      expect(response2['cached'], true);
      expect(server.executedCount, 1);
      expect(response2['data'], response1['data']);
    });

    test('Different idempotency keys execute as independent commands', () {
      final payload = {'job_id': 'job-10', 'status': 'completed'};

      server.handleRequest(
        idempotencyKey: 'key-1',
        path: '/jobs/job-10/status',
        body: payload,
      );

      server.handleRequest(
        idempotencyKey: 'key-2',
        path: '/jobs/job-10/status',
        body: payload,
      );

      expect(server.executedCount, 2);
    });
  });
}
