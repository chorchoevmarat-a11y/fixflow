import 'dart:io';

import 'package:fixflow_mobile/core/api.dart';
import 'package:fixflow_mobile/core/models.dart';

Map<String, dynamic> jobJson({
  String id = 'job-1',
  String reference = 'REQ-00042',
  String status = 'SCHEDULED',
  String? assignmentId = 'asg-1',
  List<String> actions = const ['accept', 'decline'],
}) =>
    {
      'id': id,
      'reference': reference,
      'title': 'Air handler is noisy',
      'status': status,
      'priority': 'HIGH',
      'description': 'The rooftop unit rattles loudly whenever the fan starts.',
      'property': {
        'id': 'p1',
        'name': 'Manas Business Tower',
        'address': '101 Manas Avenue, Bishkek',
        'contact_instructions': 'Security desk, floor 1'
      },
      'asset': {
        'id': 'a1',
        'code': 'AHU-001',
        'name': 'Rooftop air handling unit 1'
      },
      'category': {
        'id': 'c1',
        'name': 'HVAC service',
        'default_duration_minutes': 120
      },
      'assignment': assignmentId == null
          ? null
          : {
              'id': assignmentId,
              'start_at': '2026-11-16T05:00:00+00:00',
              'end_at': '2026-11-16T07:00:00+00:00',
              'is_active': true
            },
      'sla': {
        'state': 'AT_RISK',
        'due_at': '2026-11-17T08:00:00+00:00',
        'remaining_seconds': 3600
      },
      'estimate': null,
      'allowed_actions': actions,
    };

/// A fake backend that is idempotent on client command ids exactly like the real one:
/// replaying a command returns the original result and never stores a second copy.
class FakeServer implements FixflowApi {
  final notesByCommand = <String, String>{}; // commandId -> note id
  final imagesByCommand = <String, String>{}; // commandId -> note id
  int noteCreates = 0; // delivery attempts that reached the server
  int imageUploads = 0;

  /// Throw this from createNote (conflict / network simulation).
  ApiException? createNoteError;

  /// Throw this non-API error from createNote (TLS failure, malformed reply, I/O error...).
  Object? createNoteThrows;

  /// Fail the Nth image upload once (simulates a dropped connection mid-delivery).
  int? failImageAt;
  bool _failedOnce = false;

  @override
  Future<String> createNote({
    required String requestId,
    required String body,
    required bool internal,
    required String commandId,
    String? assignmentId,
  }) async {
    noteCreates++;
    final error = createNoteError;
    if (error != null) throw error;
    final unexpected = createNoteThrows;
    if (unexpected != null) throw unexpected;
    return notesByCommand.putIfAbsent(
        commandId, () => 'note-${notesByCommand.length + 1}');
  }

  @override
  Future<void> uploadImage({
    required String requestId,
    required String kind,
    required String path,
    required String commandId,
    String? noteId,
    String? assignmentId,
  }) async {
    imageUploads++;
    if (failImageAt != null &&
        !_failedOnce &&
        commandId.endsWith('-img-$failImageAt')) {
      _failedOnce = true;
      throw const ApiException(0, 'NETWORK_ERROR', 'Cannot reach the server.');
    }
    imagesByCommand.putIfAbsent(commandId, () => noteId ?? '');
    if (!File(path).existsSync()) {
      throw const ApiException(422, 'FILE_EMPTY', 'missing file');
    }
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError(invocation.memberName.toString());
}

Future<File> fakePhoto(Directory dir, String name) async {
  final file = File('${dir.path}/$name');
  await file.writeAsBytes(List<int>.filled(64, 7));
  return file;
}
