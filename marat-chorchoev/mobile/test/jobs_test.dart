import 'package:fixflow_mobile/core/models.dart';
import 'package:fixflow_mobile/ui/widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  testWidgets(
      'assignment inbox card shows appointment, address, asset, status, priority and SLA',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: JobCard(job: Job(jobJson())))),
    );

    expect(find.textContaining('REQ-00042'), findsOneWidget);
    expect(find.textContaining('Air handler is noisy'), findsOneWidget);
    expect(find.textContaining('Main Academic Building'), findsOneWidget);
    expect(find.textContaining('AHU-001'), findsOneWidget);
    expect(find.text('Scheduled'), findsOneWidget);
    expect(find.text('High priority'), findsOneWidget);
    // Status is text, not only color.
    expect(find.text('SLA at risk'), findsOneWidget);
    expect(find.byIcon(Icons.schedule), findsOneWidget);
  });

  test('job exposes the server-allowed actions that drive the buttons', () {
    final job = Job(jobJson(actions: ['accept', 'decline']));
    expect(job.can('accept'), isTrue);
    expect(job.can('start'), isFalse);
    expect(job.assignmentId, 'asg-1');
    expect(job.estimatedMinutes, 120);
  });

  testWidgets('state message explains an offline error with a retry action',
      (tester) async {
    var retried = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: StateMessage.forError(
            const ApiException(0, 'NETWORK_ERROR', 'Cannot reach the server.'),
            onRetry: () => retried = true,
          ),
        ),
      ),
    );
    expect(find.text('You are offline'), findsOneWidget);
    await tester.tap(find.text('Try again'));
    expect(retried, isTrue);
  });
}
