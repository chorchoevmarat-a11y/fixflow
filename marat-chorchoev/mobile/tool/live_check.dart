// Throwaway end-to-end check of the REAL HTTP client against a running API.
// Run: dart run tool/live_check.dart http://localhost:8000
import 'dart:convert';
import 'dart:io';

import 'package:fixflow_mobile/core/api.dart';
import 'package:fixflow_mobile/core/models.dart';

Future<void> main(List<String> args) async {
  final base = args.isEmpty ? 'http://localhost:8000' : args.first;
  String? token;
  String? org;
  final api = HttpFixflowApi(baseUrl: base, token: () => token, orgId: () => org);

  final login = await api.login('tech1@salymbekov.example.com', 'FixFlow-Demo-2026!');
  token = login.token;
  org = login.memberships.first.organizationId;
  stdout.writeln('login ok: ${login.fullName}, role ${login.memberships.first.role}');

  final jobs = await api.assignedJobs();
  stdout.writeln('assigned jobs: ${jobs.length}');
  final job = jobs.firstWhere((j) => j.assignmentId != null);
  stdout.writeln('using ${job.reference} (${job.status}) assignment ${job.assignmentId}');

  final command = 'note-livecheck-${DateTime.now().millisecondsSinceEpoch}';
  final first = await api.createNote(
    requestId: job.id,
    body: 'Live check from the Dart client.',
    internal: true,
    commandId: command,
    assignmentId: job.assignmentId,
  );
  final replay = await api.createNote(
    requestId: job.id,
    body: 'Live check from the Dart client.',
    internal: true,
    commandId: command,
    assignmentId: job.assignmentId,
  );
  stdout.writeln('note id first=$first replay=$replay same=${first == replay}');

  // A 1x1 PNG.
  final png = base64Decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==');
  final file = File('${Directory.systemTemp.path}/fixflow_live.png')..writeAsBytesSync(png);
  for (var i = 0; i < 2; i++) {
    await api.uploadImage(
      requestId: job.id,
      kind: 'NOTE',
      path: file.path,
      commandId: '$command-img-0',
      noteId: first,
      assignmentId: job.assignmentId,
    );
  }
  final notes = await api.notes(job.id);
  final mine = notes.where((n) => n.body == 'Live check from the Dart client.').length;
  stdout.writeln('notes on job with that text: $mine (expect 1 per run of this script)');

  // A conflict must surface as a typed error, not as success.
  try {
    await api.createNote(requestId: job.id, body: 'x', internal: false, commandId: command);
    stdout.writeln('FAIL: reuse with different payload was accepted');
  } on ApiException catch (e) {
    stdout.writeln('reuse with different payload -> ${e.status} ${e.code}');
  }
  try {
    await api.jobDetail('00000000-0000-4000-8000-000000000000');
  } on ApiException catch (e) {
    stdout.writeln('unknown job -> ${e.status} ${e.code}');
  }
  final profile = await api.myProfile();
  stdout.writeln('profile: ${profile.fullName}, ${profile.skills.length} skills, ${profile.availability.length} hours rows');
  final notifications = await api.notifications();
  stdout.writeln('notifications: ${notifications.length}');
  await api.logout();
  stdout.writeln('logout ok');
}
