import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fixflow_mobile/shared/widgets/conflict_dialog.dart';

void main() {
  group('Conflict State & Resolution Tests', () {
    testWidgets('ConflictResolutionDialog displays local and server state', (tester) async {
      bool? userChoseLocal;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () async {
                  userChoseLocal = await ConflictResolutionDialog.show(
                    context,
                    title: 'Sync Conflict Detected',
                    entityName: 'Job #42 Status',
                    localValue: 'Status: Completed (Technician offline)',
                    serverValue: 'Status: Reassigned to Technician 2 (Dispatcher)',
                  );
                },
                child: const Text('Open Dialog'),
              ),
            ),
          ),
        ),
      );

      // Open conflict dialog
      await tester.tap(find.text('Open Dialog'));
      await tester.pumpAndSettle();

      expect(find.text('Sync Conflict Detected'), findsOneWidget);
      expect(find.text('Status: Completed (Technician offline)'), findsOneWidget);
      expect(find.text('Status: Reassigned to Technician 2 (Dispatcher)'), findsOneWidget);

      // Tap Accept Server
      await tester.tap(find.text('Accept Server'));
      await tester.pumpAndSettle();

      expect(userChoseLocal, false);
    });

    testWidgets('ConflictResolutionDialog returns true when choosing Keep My Changes', (tester) async {
      bool? userChoseLocal;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () async {
                  userChoseLocal = await ConflictResolutionDialog.show(
                    context,
                    title: 'Conflict Detected',
                    entityName: 'Job #42',
                    localValue: 'Local Note',
                    serverValue: 'Server Note',
                  );
                },
                child: const Text('Open Dialog'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open Dialog'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Keep My Changes (Overwrite)'));
      await tester.pumpAndSettle();

      expect(userChoseLocal, true);
    });
  });
}
