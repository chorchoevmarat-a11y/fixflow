import 'dart:io';

import 'package:fixflow_mobile/core/models.dart';
import 'package:fixflow_mobile/core/store.dart';
import 'package:fixflow_mobile/core/sync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('fixflow_queue_');
  });
  tearDown(() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  });

  test('queued notes and photos survive a process restart', () async {
    final server = FakeServer();
    var store = await LocalStore.open(dir);
    var sync = SyncService(server, store);
    final photo = await fakePhoto(dir, 'camera.jpg');

    await sync.enqueue(
      userId: 'u1',
      orgId: 'o1',
      job: Job(jobJson()),
      body: 'Belt is worn; replacement needed.',
      internal: false,
      photoPaths: [photo.path],
      commandId: 'note-offline-0001',
    );
    // The camera's temp file may disappear; the copy kept by the app must not.
    await photo.delete();

    // "Restart": a brand-new store instance reads the same directory.
    store = await LocalStore.open(dir);
    final queue = store.queue;
    expect(queue, hasLength(1));
    expect(queue.single.id, 'note-offline-0001');
    expect(queue.single.body, 'Belt is worn; replacement needed.');
    expect(queue.single.state, QueueState.pending);
    expect(queue.single.assignmentId, 'asg-1');
    expect(File(queue.single.imagePaths.single).existsSync(), isTrue);

    // After the restart the note is delivered exactly once.
    sync = SyncService(server, store);
    final report = await sync.replay(userId: 'u1', orgId: 'o1');
    expect(report.delivered, 1);
    expect(store.queue, isEmpty);
    expect(server.notesByCommand, hasLength(1));
    expect(server.imagesByCommand, hasLength(1));
  });

  test(
      'a note interrupted mid-delivery is pending again after restart, not lost',
      () async {
    var store = await LocalStore.open(dir);
    final sync = SyncService(FakeServer(), store);
    await sync.enqueue(
        userId: 'u1',
        orgId: 'o1',
        job: Job(jobJson()),
        body: 'draft',
        internal: false,
        photoPaths: const [],
        commandId: 'note-crash-0001');
    final all = store.queue;
    all.single.state = QueueState.syncing; // app was killed while sending
    await store.saveQueue(all);

    store = await LocalStore.open(dir);
    expect(store.queue.single.state, QueueState.pending);
  });

  test('queues are scoped to the user and organization', () async {
    final store = await LocalStore.open(dir);
    final server = FakeServer();
    final sync = SyncService(server, store);
    await sync.enqueue(
        userId: 'u1',
        orgId: 'o1',
        job: Job(jobJson()),
        body: 'mine',
        internal: false,
        photoPaths: const [],
        commandId: 'note-scope-0001');

    final other = await sync.replay(userId: 'u2', orgId: 'o1');
    expect(other.delivered, 0);
    expect(server.notesByCommand, isEmpty);
    expect(store.queue, hasLength(1));
  });

  test('a corrupted state file does not brick the app', () async {
    await File('${dir.path}/state.json').writeAsString('{not json');
    final store = await LocalStore.open(dir);
    expect(store.queue, isEmpty);
  });
}
