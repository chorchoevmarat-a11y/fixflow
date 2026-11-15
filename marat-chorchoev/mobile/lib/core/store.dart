import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;

import 'models.dart';

/// Persistent on-device storage.
///
/// One JSON document (`state.json`) holds the session, the cached assigned jobs and the
/// queue of unsent notes; photos for queued notes are copied into `attachments/`.
/// Every change is written to a temporary file and atomically renamed over the real
/// one, so killing the app at any moment leaves either the old or the new state —
/// never a half-written file. This keeps queued work across process death (MOB-04).
class LocalStore {
  LocalStore._(this.directory, this._data);

  final Directory directory;
  final Map<String, dynamic> _data;

  static Future<LocalStore> open(Directory directory) async {
    await directory.create(recursive: true);
    final file = File(p.join(directory.path, 'state.json'));
    var data = <String, dynamic>{};
    if (await file.exists()) {
      try {
        data = (jsonDecode(await file.readAsString()) as Map)
            .cast<String, dynamic>();
      } catch (_) {
        // A damaged file must never brick the app; keep it for inspection and start clean.
        await file.rename(p.join(directory.path,
            'state.corrupt.${DateTime.now().millisecondsSinceEpoch}.json'));
      }
    }
    return LocalStore._(directory, data);
  }

  Future<void> _flushing = Future.value();

  /// Writes are queued one after another: two overlapping writes would share the same
  /// temporary file, and the second rename would fail (or publish a half-written file).
  Future<void> _flush() {
    final next = _flushing.catchError((_) {}).then((_) => _writeNow());
    _flushing = next;
    return next;
  }

  Future<void> _writeNow() async {
    final file = File(p.join(directory.path, 'state.json'));
    final temp = File('${file.path}.tmp');
    // Snapshot first: _data may change while the (async) write is in flight.
    final json = jsonEncode(_data);
    await temp.writeAsString(json, flush: true);
    await temp.rename(file.path);
  }

  // ---- settings and session -------------------------------------------------

  String? get serverUrl => _data['serverUrl'] as String?;
  Future<void> setServerUrl(String url) async {
    _data['serverUrl'] = url;
    await _flush();
  }

  Map<String, dynamic>? get session =>
      (_data['session'] as Map?)?.cast<String, dynamic>();
  Future<void> setSession(Map<String, dynamic>? value) async {
    if (value == null) {
      _data.remove('session');
    } else {
      _data['session'] = value;
    }
    await _flush();
  }

  // ---- cached jobs ------------------------------------------------------------

  /// Jobs are cached per user+organization so another account never sees them.
  List<Job> cachedJobs(String scope) {
    final all = (_data['jobs'] as Map?)?.cast<String, dynamic>() ?? {};
    final list = (all[scope] as List?) ?? const [];
    return [
      for (final item in list) Job((item as Map).cast<String, dynamic>())
    ];
  }

  DateTime? lastSync(String scope) {
    final value = ((_data['lastSync'] as Map?) ?? const {})[scope];
    return value is String ? DateTime.tryParse(value) : null;
  }

  Future<void> saveJobs(String scope, List<Job> jobs) async {
    final all = (_data['jobs'] as Map?)?.cast<String, dynamic>() ?? {};
    all[scope] = [for (final j in jobs) j.json];
    _data['jobs'] = all;
    final sync = (_data['lastSync'] as Map?)?.cast<String, dynamic>() ?? {};
    sync[scope] = DateTime.now().toUtc().toIso8601String();
    _data['lastSync'] = sync;
    await _flush();
  }

  Future<void> dropJobs(String scope) async {
    (_data['jobs'] as Map?)?.remove(scope);
    await _flush();
  }

  // ---- offline note queue ---------------------------------------------------------

  List<QueuedNote> get queue => [
        for (final item in (_data['queue'] as List?) ?? const [])
          QueuedNote.fromJson((item as Map).cast<String, dynamic>()),
      ];

  Future<void> saveQueue(List<QueuedNote> notes) async {
    _data['queue'] = [for (final n in notes) n.toJson()];
    await _flush();
  }

  /// Copy a picked photo next to the state file so it outlives the picker's temp file.
  Future<String> keepAttachment(String sourcePath, String name) async {
    final folder = Directory(p.join(directory.path, 'attachments'));
    await folder.create(recursive: true);
    final target = File(p.join(folder.path,
        '$name${p.extension(sourcePath).isEmpty ? '.jpg' : p.extension(sourcePath)}'));
    await File(sourcePath).copy(target.path);
    return target.path;
  }

  Future<void> deleteAttachments(List<String> paths) async {
    for (final path in paths) {
      try {
        await File(path).delete();
      } on FileSystemException {
        // already gone
      }
    }
  }
}
