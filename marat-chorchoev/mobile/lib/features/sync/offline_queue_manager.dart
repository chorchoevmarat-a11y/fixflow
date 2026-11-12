import 'dart:convert';
import 'package:drift/drift.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import '../../core/database.dart';

final offlineQueueManagerProvider = Provider<OfflineQueueManager>((ref) {
  final db = ref.watch(databaseProvider);
  return OfflineQueueManager(db);
});

class OfflineCommand {
  final int localId;
  final String commandId;
  final String commandType;
  final String jobId;
  final Map<String, dynamic> payload;
  final DateTime createdAt;
  final int retryCount;
  final String? lastError;

  OfflineCommand({
    required this.localId,
    required this.commandId,
    required this.commandType,
    required this.jobId,
    required this.payload,
    required this.createdAt,
    this.retryCount = 0,
    this.lastError,
  });
}

class OfflineQueueManager {
  final AppDatabase _db;
  final Uuid _uuid = const Uuid();

  OfflineQueueManager(this._db);

  /// Enqueue an offline command with an idempotency key (commandId)
  Future<String> enqueueCommand({
    required String commandType,
    required String jobId,
    required Map<String, dynamic> payload,
    String? commandId,
  }) async {
    final idempotencyKey = commandId ?? _uuid.v4();
    final companion = PendingCommandsCompanion.insert(
      commandId: idempotencyKey,
      commandType: commandType,
      jobId: jobId,
      payload: jsonEncode(payload),
      createdAt: Value(DateTime.now()),
      retryCount: const Value(0),
    );

    await _db.enqueuePendingCommand(companion);
    return idempotencyKey;
  }

  /// Fetch all pending commands in FIFO order
  Future<List<OfflineCommand>> getPendingCommands() async {
    final rawList = await _db.getAllPendingCommands();
    return rawList.map((cmd) {
      Map<String, dynamic> parsedPayload = {};
      try {
        parsedPayload = jsonDecode(cmd.payload) as Map<String, dynamic>;
      } catch (_) {}

      return OfflineCommand(
        localId: cmd.localId,
        commandId: cmd.commandId,
        commandType: cmd.commandType,
        jobId: cmd.jobId,
        payload: parsedPayload,
        createdAt: cmd.createdAt,
        retryCount: cmd.retryCount,
        lastError: cmd.lastError,
      );
    }).toList();
  }

  Future<int> getPendingCount() async {
    final list = await _db.getAllPendingCommands();
    return list.length;
  }

  Future<void> removeCommand(int localId) async {
    await _db.deletePendingCommand(localId);
  }

  Future<void> recordFailure(int localId, String error) async {
    await _db.incrementRetry(localId, error);
  }
}
