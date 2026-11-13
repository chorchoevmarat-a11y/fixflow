import 'dart:io';

import 'package:fixflow_mobile/core/models.dart';
import 'package:fixflow_mobile/core/store.dart';
import 'package:fixflow_mobile/core/sync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  late Directory dir;
  setUp(
      () async => dir = await Directory.systemTemp.createTemp('fixflow_idem_'));
  tearDown(() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  });

  test(
      'replaying after a dropped connection yields exactly one note and one photo per item',
      () async {
    final store = await LocalStore.open(dir);
    final server = FakeServer()
      ..failImageAt = 1; // connection drops during the 2nd photo
    final sync = SyncService(server, store);
    final a = await fakePhoto(dir, 'a.jpg');
    final b = await fakePhoto(dir, 'b.jpg');
    await sync.enqueue(
      userId: 'u1',
      orgId: 'o1',
      job: Job(jobJson()),
      body: 'Two photos of the belt.',
      internal: false,
      photoPaths: [a.path, b.path],
      commandId: 'note-idem-0001',
    );

    final first = await sync.replay(userId: 'u1', orgId: 'o1');
    expect(first.stoppedOffline, isTrue);
    expect(first.delivered, 0);
    // Progress was persisted: the note exists and photo 0 is done, photo 1 is not.
    final partial = store.queue.single;
    expect(partial.state, QueueState.pending);
    expect(partial.noteId, isNotNull);
    expect(partial.uploadedImages, 1);
    expect(server.notesByCommand, hasLength(1));

    // Reconnect: replay again. Nothing is duplicated.
    final second = await sync.replay(userId: 'u1', orgId: 'o1');
    expect(second.delivered, 1);
    expect(store.queue, isEmpty);
    expect(server.notesByCommand, hasLength(1));
    expect(server.imagesByCommand.keys,
        unorderedEquals(['note-idem-0001-img-0', 'note-idem-0001-img-1']));
    expect(server.noteCreates, 1,
        reason: 'the note was created once; the resume skipped it');
  });

  test('duplicate delivery of the same command id is a no-op on the server',
      () async {
    final server = FakeServer();
    final one = await server.createNote(
        requestId: 'r', body: 'x', internal: false, commandId: 'note-dup-0001');
    final two = await server.createNote(
        requestId: 'r', body: 'x', internal: false, commandId: 'note-dup-0001');
    expect(two, one);
    expect(server.notesByCommand, hasLength(1));
  });

  test(
      'a server error does not drop the draft: 5xx keeps it pending for the next sync',
      () async {
    final store = await LocalStore.open(dir);
    final server = FakeServer()
      ..createNoteError =
          const ApiException(503, 'DATABASE_UNAVAILABLE', 'try again');
    final sync = SyncService(server, store);
    await sync.enqueue(
        userId: 'u1',
        orgId: 'o1',
        job: Job(jobJson()),
        body: 'keep me',
        internal: false,
        photoPaths: const [],
        commandId: 'note-5xx-00001');

    final report = await sync.replay(userId: 'u1', orgId: 'o1');
    expect(report.stoppedOffline, isTrue);
    expect(store.queue.single.state, QueueState.pending);
    expect(store.queue.single.attempts, 1);

    server.createNoteError = null;
    expect((await sync.replay(userId: 'u1', orgId: 'o1')).delivered, 1);
  });
}
