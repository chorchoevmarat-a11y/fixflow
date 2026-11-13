import 'dart:convert';
import 'dart:io';

import 'package:fixflow_mobile/core/providers.dart';
import 'package:fixflow_mobile/core/store.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory dir;
  late HttpServer server;
  late bool hangLogout;
  final logoutCalls = <String?>[];

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('fixflow_signout_');
    hangLogout = false;
    logoutCalls.clear();
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((req) async {
      if (req.uri.path == '/api/v1/auth/logout') {
        logoutCalls.add(req.headers.value('authorization'));
        if (hangLogout) return; // never answers
      }
      req.response
        ..statusCode = 200
        ..headers.contentType = ContentType.json
        ..write(jsonEncode({'status': 'signed_out'}));
      await req.response.close();
    });
  });

  tearDown(() async {
    await server.close(force: true);
    if (await dir.exists()) await dir.delete(recursive: true);
  });

  /// A signed-in app state, wired exactly like `main()` does it.
  Future<(ProviderContainer, LocalStore, MemorySecretStore)> signedIn(
      String serverUrl) async {
    final store = await LocalStore.open(dir);
    await store.setServerUrl(serverUrl);
    await store.setSession({
      'userId': 'u1',
      'email': 'tech1@example.com',
      'fullName': 'Tech One',
      'orgId': 'o1',
      'expiresAt': DateTime.now()
          .toUtc()
          .add(const Duration(hours: 1))
          .toIso8601String(),
      'memberships': [
        {
          'organization_id': 'o1',
          'organization_name': 'Org One',
          'role': 'TECHNICIAN',
          'timezone': 'Asia/Bishkek',
        }
      ],
    });
    final secrets = MemorySecretStore()..token = 'secret-token';
    final container = ProviderContainer(overrides: [
      storeProvider.overrideWithValue(store),
      secretStoreProvider.overrideWithValue(secrets),
      initialTokenProvider.overrideWithValue('secret-token'),
    ]);
    addTearDown(container.dispose);
    // As in the running app, screens already use the API client.
    container.read(apiProvider);
    expect(container.read(sessionProvider).signedIn, isTrue);
    return (container, store, secrets);
  }

  test('sign out clears the device and revokes the server session', () async {
    final (container, store, secrets) =
        await signedIn('http://127.0.0.1:${server.port}');

    await container.read(sessionProvider.notifier).signOut();

    expect(container.read(sessionProvider).signedIn, isFalse);
    expect(store.session, isNull, reason: 'session must be gone after restart');
    expect(secrets.token, isNull,
        reason: 'token must be removed from keystore');
    expect(logoutCalls, ['Bearer secret-token']);
  });

  test('sign out while the server is unreachable still signs out', () async {
    final (container, store, secrets) = await signedIn('http://127.0.0.1:1');

    await container.read(sessionProvider.notifier).signOut();

    expect(container.read(sessionProvider).signedIn, isFalse);
    expect(store.session, isNull);
    expect(secrets.token, isNull);
  });

  test('sign out does not hang when the server never answers', () async {
    hangLogout = true;
    final (container, store, _) =
        await signedIn('http://127.0.0.1:${server.port}');
    final watch = Stopwatch()..start();

    await container.read(sessionProvider.notifier).signOut();

    expect(watch.elapsed, lessThan(const Duration(seconds: 8)),
        reason: 'the server call is best effort and must not block sign-out');
    expect(container.read(sessionProvider).signedIn, isFalse);
    expect(store.session, isNull);
  });
}
