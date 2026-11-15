import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';

import 'app.dart';
import 'core/providers.dart';
import 'core/store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final directory = await getApplicationDocumentsDirectory();
  final store = await LocalStore.open(directory);
  const secrets = KeystoreSecretStore();
  final token = await secrets.read();
  runApp(
    ProviderScope(
      overrides: [
        storeProvider.overrideWithValue(store),
        initialTokenProvider.overrideWithValue(token),
      ],
      child: const FixflowApp(),
    ),
  );
}
