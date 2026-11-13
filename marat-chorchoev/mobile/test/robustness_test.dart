import 'dart:convert';
import 'dart:io';

import 'package:fixflow_mobile/core/api.dart';
import 'package:fixflow_mobile/core/models.dart';
import 'package:fixflow_mobile/core/store.dart';
import 'package:fixflow_mobile/core/sync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  late Directory dir;
  setUp(() async =>
      dir = await Directory.systemTemp.createTemp('fixflow_robust_'));
  tearDown(() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  });

  Future<void> enqueueTwo(SyncService sync) async {
    for (final id in ['note-robust-01', 'note-robust-02']) {
      await sync.enqueue(
        userId: 'u1',
        orgId: 'o1',
        job: Job(jobJson()),
        body: 'A note long enough to be real: $id',
        internal: false,
        photoPaths: const [],
        commandId: id,
      );
    }
  }

  test(
      'an unexpected (non-API) error never leaves a note stuck in "syncing"; the queue keeps going',
      () async {
    final store = await LocalStore.open(dir);
    final server = FakeServer()
      ..createNoteThrows = const HandshakeException('TLS failed');
    final sync = SyncService(server, store);
    await enqueueTwo(sync);

    final report = await sync.replay(userId: 'u1', orgId: 'o1');

    expect(store.queue.any((n) => n.state == QueueState.syncing), isFalse,
        reason: 'must not be stuck in syncing');
    expect(report.failed, 2,
        reason: 'both are marked failed, retry is explicit');
    expect(store.queue.every((n) => n.state == QueueState.failed), isTrue);
    expect(store.queue.first.reason, isNotEmpty);
    // and a retry works once the problem is gone
    server.createNoteThrows = null;
    await sync.retry('note-robust-01');
    final again = await sync.replay(userId: 'u1', orgId: 'o1');
    expect(again.delivered, 1);
  });

  test(
      'many overlapping saves never throw and the last state is what is on disk',
      () async {
    final store = await LocalStore.open(dir);
    final futures = <Future<void>>[
      for (var i = 0; i < 40; i++) store.setServerUrl('http://host-$i:8000'),
    ];
    await Future.wait(futures); // must not throw (shared temp file race)
    final reopened = await LocalStore.open(dir);
    expect(reopened.serverUrl, 'http://host-39:8000');
  });

  group('API client with a bad address or a misbehaving server', () {
    late HttpServer server;
    late int port;

    setUp(() async {
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      port = server.port;
      server.listen((req) async {
        final r = req.response;
        switch (req.uri.path) {
          case '/html200':
            r.statusCode = 200;
            r.headers.contentType = ContentType.html;
            r.write('<html>captive portal</html>');
          case '/wrongshape':
            r.statusCode = 200;
            r.headers.contentType = ContentType.json;
            r.write(jsonEncode({'hello': 'world'}));
          case '/badutf8':
            r.statusCode = 200;
            r.headers.contentType = ContentType.json;
            r.add([0xff, 0xfe, 0xfd]);
        }
        await r.close();
      });
    });
    tearDown(() => server.close(force: true));

    Future<Object?> loginAgainst(String base) async {
      final api =
          HttpFixflowApi(baseUrl: base, token: () => null, orgId: () => null);
      try {
        await api.login('a@b.com', 'x');
        return null;
      } catch (e) {
        return e;
      }
    }

    for (final base in [
      '192.168.1.5:8000',
      'localhost:8000',
      '',
      'http://',
      'http://my server:8000',
      'ftp://localhost:8000',
    ]) {
      test('malformed address "$base" becomes a readable ApiException',
          () async {
        final error = await loginAgainst(base);
        expect(error, isA<ApiException>(), reason: '$error');
        expect((error! as ApiException).message, isNotEmpty);
      });
    }

    test('TLS handshake failure is a network error', () async {
      final error = await loginAgainst('https://localhost:$port');
      expect(error, isA<ApiException>(), reason: '$error');
      expect((error! as ApiException).isNetwork, isTrue);
    });

    for (final path in ['html200', 'wrongshape', 'badutf8']) {
      test('server answering /$path is a BAD_RESPONSE, not a crash', () async {
        final error = await loginAgainst('http://localhost:$port/$path');
        expect(error, isA<ApiException>(), reason: '$error');
        expect((error! as ApiException).code, 'BAD_RESPONSE');
      });
    }

    test(
        'uploading a photo that no longer exists is a clear 422, not a retry loop',
        () async {
      final api = HttpFixflowApi(
          baseUrl: 'http://localhost:$port',
          token: () => null,
          orgId: () => null);
      Object? error;
      try {
        await api.uploadImage(
            requestId: 'r',
            kind: 'NOTE',
            path: '${dir.path}/gone.jpg',
            commandId: 'cmd-gone-0001');
      } catch (e) {
        error = e;
      }
      expect(error, isA<ApiException>(), reason: '$error');
      expect((error! as ApiException).status, 422);
      expect((error as ApiException).code, 'FILE_MISSING');
    });
  });
}
