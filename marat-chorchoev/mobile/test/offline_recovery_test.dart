import 'dart:io';

import 'package:fixflow_mobile/core/api.dart';
import 'package:fixflow_mobile/core/models.dart';
import 'package:fixflow_mobile/core/providers.dart';
import 'package:fixflow_mobile/core/store.dart';
import 'package:fixflow_mobile/ui/jobs_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// The server is unreachable until [reachable] is set; the network *link* never changes,
/// so no connectivity event ever fires (a server outage or VPN hiccup on working Wi-Fi).
class _FlakyApi implements FixflowApi {
  int calls = 0;
  bool reachable = false;

  @override
  Future<List<Job>> assignedJobs() async {
    calls++;
    if (!reachable) {
      throw const ApiException(0, 'NETWORK_ERROR', 'Cannot reach the server.');
    }
    return [];
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError(invocation.memberName.toString());
}

/// Same as the real notifier, minus the Android connectivity plugin (absent in unit tests).
class _NoPluginOnline extends OnlineNotifier {
  @override
  bool build() => true;
}

void main() {
  late Directory dir;
  setUp(() async =>
      dir = await Directory.systemTemp.createTemp('fixflow_recovery_'));
  tearDown(() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  });

  testWidgets(
      'once the app thinks it is offline, the user can always retry and recover',
      (tester) async {
    final store = (await tester.runAsync(() async {
      final s = await LocalStore.open(dir);
      await s.setSession({
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
      return s;
    }))!;
    final api = _FlakyApi();

    await tester.pumpWidget(ProviderScope(
      overrides: [
        storeProvider.overrideWithValue(store),
        secretStoreProvider.overrideWithValue(MemorySecretStore()),
        initialTokenProvider.overrideWithValue('token'),
        apiProvider.overrideWithValue(api),
        onlineProvider.overrideWith(_NoPluginOnline.new),
      ],
      child: const MaterialApp(home: JobsScreen()),
    ));
    // The store does real file I/O, so wait on the condition (up to ~15 s of real time)
    // instead of a fixed delay: a fixed delay fails when the whole suite runs in parallel.
    Future<void> settleUntil(bool Function() done) async {
      for (var i = 0; i < 150 && !done(); i++) {
        await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 100)));
        await tester.pump(const Duration(milliseconds: 50));
      }
    }

    await settleUntil(() => find.textContaining('Offline').evaluate().isNotEmpty);

    // The first load failed: the banner says offline.
    expect(find.textContaining('Offline'), findsOneWidget);
    expect(api.calls, 1);

    // The Refresh button must stay usable: it is the only way to find out the server is back.
    final refresh = tester
        .widget<IconButton>(find.widgetWithIcon(IconButton, Icons.refresh));
    expect(refresh.onPressed, isNotNull,
        reason: 'Refresh must not be disabled while offline');

    // The offline banner offers a visible way to try again.
    expect(find.text('Retry'), findsOneWidget);

    // The server comes back; one tap recovers without any connectivity event.
    api.reachable = true;
    await tester.tap(find.text('Retry'));
    // Saving the jobs cache is real file I/O: give real time to pass, then repaint.
    await settleUntil(() => find.textContaining('Offline').evaluate().isEmpty);

    expect(api.calls, 2);
    expect(find.textContaining('Offline'), findsNothing);
    expect(find.text('Retry'), findsNothing);
  });
}
