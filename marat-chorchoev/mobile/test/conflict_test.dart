import 'dart:io';

import 'package:fixflow_mobile/core/models.dart';
import 'package:fixflow_mobile/core/store.dart';
import 'package:fixflow_mobile/core/sync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  late Directory dir;
  setUp(() async =>
      dir = await Directory.systemTemp.createTemp('fixflow_conflict_'));
  tearDown(() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  });

  Future<(LocalStore, SyncService, FakeServer)> setup() async {
    final store = await LocalStore.open(dir);
    final server = FakeServer();
    final sync = SyncService(server, store);
    final photo = await fakePhoto(dir, 'evidence.jpg');
    await sync.enqueue(
      userId: 'u1',
      orgId: 'o1',
      job: Job(jobJson()),
      body: 'Written while offline, before the dispatcher reassigned the job.',
      internal: false,
      photoPaths: [photo.path],
      commandId: 'note-conflict-01',
    );
    return (store, sync, server);
  }

  test(
      'reassigned job: the draft is kept as a conflict with a clear reason, never published',
      () async {
    final (store, sync, server) = await setup();
    server.createNoteError = const ApiException(
        409, 'ASSIGNMENT_REVOKED', 'This job is no longer assigned to you.');

    final report = await sync.replay(userId: 'u1', orgId: 'o1');

    expect(report.conflicts, 1);
    expect(report.delivered, 0);
    final note = store.queue.single;
    expect(note.state, QueueState.conflict);
    expect(note.reason, contains('reassigned'));
    expect(note.body, startsWith('Written while offline'));
    expect(File(note.imagePaths.single).existsSync(), isTrue,
        reason: 'photo must still be on the phone');
    expect(server.notesByCommand, isEmpty);
    expect(server.imagesByCommand, isEmpty);
  });

  test(
      'a conflicted draft is not retried automatically and is only deleted by an explicit discard',
      () async {
    final (store, sync, server) = await setup();
    server.createNoteError =
        const ApiException(409, 'REQUEST_CLOSED', 'This request is CLOSED.');
    await sync.replay(userId: 'u1', orgId: 'o1');
    expect(store.queue.single.state, QueueState.conflict);

    server.createNoteError = null;
    final again = await sync.replay(userId: 'u1', orgId: 'o1');
    expect(again.delivered, 0,
        reason: 'conflicts wait for the person to decide');
    expect(store.queue, hasLength(1));

    final path = store.queue.single.imagePaths.single;
    await sync.discard('note-conflict-01');
    expect(store.queue, isEmpty);
    expect(File(path).existsSync(), isFalse);
  });

  test(
      'losing access (404) is reported as a conflict; "try again" re-queues it',
      () async {
    final (store, sync, server) = await setup();
    server.createNoteError =
        const ApiException(404, 'REQUEST_NOT_FOUND', 'Request not found.');
    await sync.replay(userId: 'u1', orgId: 'o1');
    expect(store.queue.single.state, QueueState.conflict);
    expect(store.queue.single.reason, contains('no longer have access'));

    server.createNoteError = null;
    await sync.retry('note-conflict-01');
    expect(store.queue.single.state, QueueState.pending);
    final report = await sync.replay(userId: 'u1', orgId: 'o1');
    expect(report.delivered, 1);
    expect(server.notesByCommand, hasLength(1));
  });

  test('an expired session stops the replay and keeps every draft', () async {
    final (store, sync, server) = await setup();
    server.createNoteError =
        const ApiException(401, 'SESSION_EXPIRED', 'Session expired.');
    final report = await sync.replay(userId: 'u1', orgId: 'o1');
    expect(report.sessionExpired, isTrue);
    expect(store.queue.single.state, QueueState.pending);
  });

  test('a validation failure is shown as failed with the server message',
      () async {
    final (store, sync, server) = await setup();
    server.createNoteError =
        const ApiException(422, 'VALIDATION_ERROR', 'Some fields are invalid.');
    final report = await sync.replay(userId: 'u1', orgId: 'o1');
    expect(report.failed, 1);
    expect(store.queue.single.state, QueueState.failed);
    expect(store.queue.single.reason, 'Some fields are invalid.');
  });
}
