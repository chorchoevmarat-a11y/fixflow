import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fixflow_mobile/features/jobs/jobs_repository.dart';
import 'package:fixflow_mobile/features/jobs/jobs_notifier.dart';
import 'package:fixflow_mobile/shared/widgets/sla_indicator.dart';

void main() {
  group('JobModel & JobsState Tests', () {
    test('JobModel.fromJson correctly parses fields', () {
      final json = {
        'id': 'job-123',
        'title': 'HVAC Repair',
        'description': 'Check rooftop unit',
        'status': 'in_progress',
        'priority': 'high',
        'customer_id': 'cust-1',
        'customer_name': 'Acme Corp',
        'location_address': '123 Main St',
        'assigned_technician_id': 'tech-9',
        'sla_deadline': '2026-12-01T12:00:00Z',
      };

      final job = JobModel.fromJson(json);

      expect(job.id, 'job-123');
      expect(job.title, 'HVAC Repair');
      expect(job.status, 'in_progress');
      expect(job.priority, 'high');
      expect(job.customerName, 'Acme Corp');
      expect(job.slaDeadline, isNotNull);
    });

    test('JobsState filters jobs correctly by status', () {
      final jobs = [
        JobModel(
          id: '1',
          title: 'Job 1',
          description: '',
          status: 'assigned',
          priority: 'medium',
          customerId: 'c1',
          customerName: 'Customer A',
          locationAddress: 'Addr 1',
          assignedTechnicianId: 't1',
        ),
        JobModel(
          id: '2',
          title: 'Job 2',
          description: '',
          status: 'in_progress',
          priority: 'high',
          customerId: 'c2',
          customerName: 'Customer B',
          locationAddress: 'Addr 2',
          assignedTechnicianId: 't1',
        ),
      ];

      final stateAll = JobsState(jobs: jobs, filterStatus: 'all');
      expect(stateAll.filteredJobs.length, 2);

      final stateInProgress = JobsState(jobs: jobs, filterStatus: 'in_progress');
      expect(stateInProgress.filteredJobs.length, 1);
      expect(stateInProgress.filteredJobs.first.id, '2');
    });
  });

  group('SlaIndicator Widget Tests', () {
    testWidgets('Displays SLA Met when completed is true', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SlaIndicator(
              slaDeadline: DateTime.now().subtract(const Duration(hours: 1)),
              isCompleted: true,
            ),
          ),
        ),
      );

      expect(find.text('SLA Met'), findsOneWidget);
    });

    testWidgets('Displays SLA Breached when deadline is past', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SlaIndicator(
              slaDeadline: DateTime.now().subtract(const Duration(hours: 2)),
              isCompleted: false,
            ),
          ),
        ),
      );

      expect(find.text('SLA Breached'), findsOneWidget);
    });
  });
}
