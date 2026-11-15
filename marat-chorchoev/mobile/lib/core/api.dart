import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:http/http.dart' as http;

import 'config.dart';
import 'models.dart';

/// Everything the app needs from the backend. A narrow interface so the sync logic can
/// be tested against a fake that behaves like the real, idempotent server.
abstract class FixflowApi {
  Future<LoginResult> login(String email, String password);
  Future<void> logout();
  Future<List<Job>> assignedJobs();
  Future<Job> jobDetail(String requestId);
  Future<List<NoteItem>> notes(String requestId);
  Future<Job> transition(String requestId, String action,
      {Map<String, dynamic> body = const {}});

  /// Returns the server note id. Replaying the same [commandId] returns the same note.
  Future<String> createNote({
    required String requestId,
    required String body,
    required bool internal,
    required String commandId,
    String? assignmentId,
  });

  Future<void> uploadImage({
    required String requestId,
    required String kind,
    required String path,
    required String commandId,
    String? noteId,
    String? assignmentId,
  });

  Future<List<InventoryItem>> inventory();
  Future<void> consumeMaterial({
    required String requestId,
    required String itemId,
    required int quantity,
    required String commandId,
  });
  Future<List<NotificationItem>> notifications();
  Future<void> markNotificationRead(String id);
  Future<TechnicianProfile> myProfile();
}

class HttpFixflowApi implements FixflowApi {
  HttpFixflowApi({
    required this.baseUrl,
    required this.token,
    required this.orgId,
    http.Client? client,
  }) : _client = client ?? http.Client();

  final String baseUrl;
  final String? Function() token;
  final String? Function() orgId;
  final http.Client _client;

  static const _badAddress = ApiException(0, 'BAD_ADDRESS',
      'The server address is not valid. Use the form http://192.168.1.20:8000');
  static const _badResponse = ApiException(502, 'BAD_RESPONSE',
      'The server sent an unexpected answer. Check the server address.');

  Uri _uri(String path, [Map<String, String>? query]) {
    final root = baseUrl.replaceAll(RegExp(r'/+$'), '');
    return Uri.parse('$root${AppConfig.apiPrefix}$path')
        .replace(queryParameters: query);
  }

  Map<String, String> _headers({bool json = true}) {
    final t = token();
    final o = orgId();
    return {
      if (json) 'Content-Type': 'application/json',
      'Accept': 'application/json',
      if (t != null) 'Authorization': 'Bearer $t',
      if (o != null) 'X-Organization-ID': o,
    };
  }

  Future<dynamic> _send(Future<http.Response> Function() call) async {
    final http.Response response;
    try {
      response = await call().timeout(const Duration(seconds: 20));
    } on TimeoutException {
      throw const ApiException(
          0, 'NETWORK_ERROR', 'The server took too long to answer.');
    } on IOException {
      // SocketException, TLS HandshakeException, connection resets, ...
      throw const ApiException(0, 'NETWORK_ERROR', 'Cannot reach the server.');
    } on http.ClientException {
      throw const ApiException(0, 'NETWORK_ERROR', 'Cannot reach the server.');
    } on FormatException {
      throw _badAddress;
    } on ArgumentError {
      throw _badAddress; // e.g. "No host specified in URI" for a mistyped address
    } on UnsupportedError {
      throw _badAddress;
    }
    dynamic data;
    var unreadable = false;
    final bytes = response.bodyBytes;
    if (bytes.isNotEmpty) {
      try {
        data = jsonDecode(utf8.decode(bytes));
      } catch (_) {
        data = null;
        unreadable = true;
      }
    }
    if (response.statusCode >= 400) {
      final error = data is Map ? data['error'] : null;
      throw ApiException(
        response.statusCode,
        error is Map
            ? (error['code'] as String? ?? 'HTTP_ERROR')
            : 'HTTP_ERROR',
        error is Map
            ? (error['message'] as String? ?? 'Request failed.')
            : 'Request failed (${response.statusCode}).',
      );
    }
    if (unreadable) {
      throw _badResponse; // e.g. a captive portal answering 200 with HTML
    }
    return data;
  }

  Future<dynamic> _get(String path, [Map<String, String>? query]) =>
      _send(() => _client.get(_uri(path, query), headers: _headers()));

  Future<dynamic> _post(String path, Map<String, dynamic> body) => _send(() =>
      _client.post(_uri(path), headers: _headers(), body: jsonEncode(body)));

  @override
  Future<LoginResult> login(String email, String password) async {
    final data = await _send(
      () => _client.post(
        _uri('/auth/login'),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: jsonEncode({'email': email, 'password': password}),
      ),
    );
    try {
      final body = (data as Map).cast<String, dynamic>();
      final user = (body['user'] as Map).cast<String, dynamic>();
      return LoginResult(
        token: body['access_token'] as String,
        expiresAt: DateTime.parse(body['expires_at'] as String),
        userId: user['id'] as String,
        email: user['email'] as String,
        fullName: user['full_name'] as String,
        memberships: [
          for (final m in body['memberships'] as List)
            Membership.fromJson((m as Map).cast<String, dynamic>()),
        ],
      );
    } on TypeError {
      throw _badResponse;
    } on FormatException {
      throw _badResponse;
    }
  }

  @override
  Future<void> logout() async {
    await _post('/auth/logout', {});
  }

  @override
  Future<List<Job>> assignedJobs() async {
    final list = await _get('/requests',
        {'page_size': '100', 'open_only': 'true', 'sort': 'due'}) as Map;
    final ids = [
      for (final row in list['items'] as List) (row as Map)['id'] as String,
    ];
    final jobs = <Job>[];
    // The list row is lightweight; fetch each detail so the offline view has everything.
    // A few at a time: one-by-one made the inbox slow on a mobile connection.
    for (var i = 0; i < ids.length; i += 5) {
      final batch = ids.sublist(i, math.min(i + 5, ids.length));
      final details =
          await Future.wait([for (final id in batch) jobDetail(id)]);
      for (final job in details) {
        // The server also lets a technician see jobs they finished (history), e.g. a
        // reopened one now handled by someone else. The inbox shows only current work.
        if (job.json['assigned_to_me'] == true) jobs.add(job);
      }
    }
    return jobs;
  }

  @override
  Future<Job> jobDetail(String requestId) async => Job(
      ((await _get('/requests/$requestId')) as Map).cast<String, dynamic>());

  @override
  Future<List<NoteItem>> notes(String requestId) async => [
        for (final n in (await _get('/requests/$requestId/notes')) as List)
          NoteItem.fromJson((n as Map).cast<String, dynamic>()),
      ];

  @override
  Future<Job> transition(String requestId, String action,
      {Map<String, dynamic> body = const {}}) async {
    final data = await _post('/requests/$requestId/$action', body);
    // decline returns a small stub because the technician loses access.
    if (data is Map && data.containsKey('reference')) {
      return Job(data.cast<String, dynamic>());
    }
    return Job({
      'id': requestId,
      'reference': '',
      'title': '',
      'status': (data as Map)['status']
    });
  }

  @override
  Future<String> createNote({
    required String requestId,
    required String body,
    required bool internal,
    required String commandId,
    String? assignmentId,
  }) async {
    final data = await _post('/requests/$requestId/notes', {
      'body': body,
      'visibility': internal ? 'INTERNAL' : 'PUBLIC',
      'client_command_id': commandId,
      if (assignmentId != null) 'assignment_id': assignmentId,
    }) as Map;
    return data['id'] as String;
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
    if (!await File(path).exists()) {
      throw const ApiException(422, 'FILE_MISSING',
          'A photo for this note is no longer stored on the device.');
    }
    await _send(() async {
      final request =
          http.MultipartRequest('POST', _uri('/requests/$requestId/files'))
            ..headers.addAll(_headers(json: false))
            ..fields['kind'] = kind
            ..fields['client_command_id'] = commandId;
      if (noteId != null) request.fields['note_id'] = noteId;
      if (assignmentId != null) request.fields['assignment_id'] = assignmentId;
      request.files.add(await http.MultipartFile.fromPath('file', path));
      return http.Response.fromStream(await _client.send(request));
    });
  }

  @override
  Future<List<InventoryItem>> inventory() async {
    final data = await _get('/inventory', {'page_size': '100'}) as Map;
    return [
      for (final i in data['items'] as List)
        InventoryItem.fromJson((i as Map).cast<String, dynamic>())
    ];
  }

  @override
  Future<void> consumeMaterial({
    required String requestId,
    required String itemId,
    required int quantity,
    required String commandId,
  }) async {
    await _post('/requests/$requestId/materials', {
      'item_id': itemId,
      'quantity': quantity,
      'client_command_id': commandId,
    });
  }

  @override
  Future<List<NotificationItem>> notifications() async {
    final data = await _get('/notifications', {'page_size': '50'}) as Map;
    return [
      for (final n in data['items'] as List)
        NotificationItem.fromJson((n as Map).cast<String, dynamic>())
    ];
  }

  @override
  Future<void> markNotificationRead(String id) async {
    await _post('/notifications/$id/read', {});
  }

  @override
  Future<TechnicianProfile> myProfile() async {
    final data = await _get('/technicians/me') as Map;
    return TechnicianProfile(
      fullName: data['full_name'] as String,
      skills: [
        for (final s in data['skills'] as List) (s as Map)['name'] as String
      ],
      availability: [
        for (final a in data['availability'] as List)
          AvailabilitySlot((a as Map)['weekday'] as int,
              a['starts_at'] as String, a['ends_at'] as String),
      ],
      timeOff: [
        for (final t in data['time_off'] as List)
          '${(t as Map)['start_at']} → ${t['end_at']}${t['reason'] != null ? ' (${t['reason']})' : ''}',
      ],
    );
  }
}
