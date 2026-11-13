import 'api.dart';
import 'models.dart';
import 'store.dart';

/// Result of one replay pass.
class SyncReport {
  const SyncReport({
    this.delivered = 0,
    this.conflicts = 0,
    this.failed = 0,
    this.stoppedOffline = false,
    this.sessionExpired = false,
  });

  final int delivered;
  final int conflicts;
  final int failed;
  final bool stoppedOffline;
  final bool sessionExpired;
}

/// Delivers queued notes and photos to the server.
///
/// Safety properties:
/// * every note and every photo has a stable client command id stored with the draft,
///   so retrying after a timeout, crash, or reconnect never creates a second copy;
/// * progress (note id, photos done) is persisted after each step, so an interrupted
///   delivery resumes instead of restarting;
/// * a note is removed only after the server confirmed all of it;
/// * if the job was reassigned, closed, or access was lost, the draft is kept and
///   marked as a conflict — it is never published to somebody else's assignment and
///   never deleted without an explicit user action (MOB-06 / MOB-07).
class SyncService {
  SyncService(this.api, this.store);

  final FixflowApi api;
  final LocalStore store;

  List<QueuedNote> _queue() => store.queue;

  Future<void> _save(QueuedNote changed) async {
    final all = _queue();
    final index = all.indexWhere((n) => n.id == changed.id);
    if (index >= 0) all[index] = changed;
    await store.saveQueue(all);
  }

  /// Add a note to the queue, copying its photos into app storage.
  Future<QueuedNote> enqueue({
    required String userId,
    required String orgId,
    required Job job,
    required String body,
    required bool internal,
    required List<String> photoPaths,
    required String commandId,
  }) async {
    final kept = <String>[];
    for (var i = 0; i < photoPaths.length; i++) {
      kept.add(await store.keepAttachment(photoPaths[i], '$commandId-$i'));
    }
    final note = QueuedNote(
      id: commandId,
      userId: userId,
      orgId: orgId,
      requestId: job.id,
      reference: job.reference,
      title: job.title,
      assignmentId: job.assignmentId,
      body: body,
      internal: internal,
      imagePaths: kept,
      createdAt: DateTime.now().toUtc(),
    );
    await store.saveQueue([..._queue(), note]);
    return note;
  }

  Future<void> discard(String commandId) async {
    final all = _queue();
    final index = all.indexWhere((n) => n.id == commandId);
    if (index < 0) return;
    await store.deleteAttachments(all[index].imagePaths);
    all.removeAt(index);
    await store.saveQueue(all);
  }

  /// Put a conflicted or failed draft back in line for another attempt.
  Future<void> retry(String commandId) async {
    final all = _queue();
    final index = all.indexWhere((n) => n.id == commandId);
    if (index < 0) return;
    all[index]
      ..state = QueueState.pending
      ..reason = null;
    await store.saveQueue(all);
  }

  /// Replay every pending note of this user and organization, oldest first.
  Future<SyncReport> replay(
      {required String userId, required String orgId}) async {
    var delivered = 0, conflicts = 0, failed = 0;
    final ids = [
      for (final n in _queue())
        if (n.userId == userId &&
            n.orgId == orgId &&
            n.state == QueueState.pending)
          n.id,
    ];
    for (final id in ids) {
      final current = _queue().where((n) => n.id == id);
      if (current.isEmpty) continue;
      final note = current.first;
      note
        ..state = QueueState.syncing
        ..attempts += 1;
      await _save(note);
      try {
        await _deliver(note);
        await discard(note.id);
        delivered++;
      } on ApiException catch (e) {
        if (e.isNetwork || e.isServerError) {
          note.state = QueueState.pending; // try again later; nothing was lost
          await _save(note);
          return SyncReport(
              delivered: delivered,
              conflicts: conflicts,
              failed: failed,
              stoppedOffline: true);
        }
        if (e.isUnauthorized) {
          note.state = QueueState.pending;
          await _save(note);
          return SyncReport(
              delivered: delivered,
              conflicts: conflicts,
              failed: failed,
              sessionExpired: true);
        }
        final conflict = _conflictReason(e);
        if (conflict != null) {
          note
            ..state = QueueState.conflict
            ..reason = conflict;
          conflicts++;
        } else {
          note
            ..state = QueueState.failed
            ..reason = e.message;
          failed++;
        }
        await _save(note);
      } catch (_) {
        // Anything unexpected (TLS failure, malformed reply, unreadable file...): never leave
        // the note stuck in "syncing". It is shown as failed and can be retried explicitly;
        // the rest of the queue keeps going.
        note
          ..state = QueueState.failed
          ..reason =
              'Something unexpected went wrong while sending. Tap Retry to try again.';
        failed++;
        await _save(note);
      }
    }
    return SyncReport(
        delivered: delivered, conflicts: conflicts, failed: failed);
  }

  Future<void> _deliver(QueuedNote note) async {
    note.noteId ??= await api.createNote(
      requestId: note.requestId,
      body: note.body,
      internal: note.internal,
      commandId: note.id,
      assignmentId: note.assignmentId,
    );
    await _save(note);
    while (note.uploadedImages < note.imagePaths.length) {
      final index = note.uploadedImages;
      await api.uploadImage(
        requestId: note.requestId,
        kind: 'NOTE',
        path: note.imagePaths[index],
        commandId: note.imageCommandId(index),
        noteId: note.noteId,
        assignmentId: note.assignmentId,
      );
      note.uploadedImages = index + 1;
      await _save(note);
    }
  }

  /// A comprehensible reason when the server says this draft can no longer be applied.
  static String? _conflictReason(ApiException e) {
    switch (e.code) {
      case 'ASSIGNMENT_REVOKED':
        return 'This job was reassigned or unassigned while you were offline. '
            'Your note was not published to the new assignment.';
      case 'REQUEST_CLOSED':
        return 'This request was closed or canceled while you were offline.';
      case 'REQUEST_NOT_FOUND':
      case 'NOT_FOUND':
        return 'You no longer have access to this job.';
      case 'ROLE_FORBIDDEN':
      case 'MEMBERSHIP_DEACTIVATED':
        return 'Your access changed while you were offline.';
    }
    if (e.isForbidden) {
      return 'You no longer have permission to add notes here.';
    }
    if (e.isNotFound) return 'You no longer have access to this job.';
    return null;
  }
}
