import 'package:intl/intl.dart';

/// Typed failure from the backend (or the network).
class ApiException implements Exception {
  const ApiException(this.status, this.code, this.message);

  /// HTTP status, or 0 when the server could not be reached.
  final int status;
  final String code;
  final String message;

  bool get isNetwork => status == 0;
  bool get isUnauthorized => status == 401;
  bool get isForbidden => status == 403;
  bool get isNotFound => status == 404;
  bool get isConflict => status == 409;
  bool get isServerError => status >= 500;

  @override
  String toString() => 'ApiException($status $code): $message';
}

class Membership {
  const Membership({
    required this.organizationId,
    required this.organizationName,
    required this.role,
    required this.timezone,
    this.technicianId,
  });

  final String organizationId;
  final String organizationName;
  final String role;
  final String timezone;
  final String? technicianId;

  factory Membership.fromJson(Map<String, dynamic> json) => Membership(
        organizationId: json['organization_id'] as String,
        organizationName: json['organization_name'] as String,
        role: json['role'] as String,
        timezone: (json['timezone'] as String?) ?? 'UTC',
        technicianId: json['technician_id'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'organization_id': organizationId,
        'organization_name': organizationName,
        'role': role,
        'timezone': timezone,
        'technician_id': technicianId,
      };
}

class LoginResult {
  const LoginResult({
    required this.token,
    required this.expiresAt,
    required this.userId,
    required this.email,
    required this.fullName,
    required this.memberships,
  });

  final String token;
  final DateTime expiresAt;
  final String userId;
  final String email;
  final String fullName;
  final List<Membership> memberships;
}

/// A job as the technician sees it. Built from the request detail JSON, which is also
/// exactly what is cached on the device for offline use.
class Job {
  const Job(this.json);

  final Map<String, dynamic> json;

  String get id => json['id'] as String;
  String get reference => json['reference'] as String;
  String get title => json['title'] as String;
  String get status => json['status'] as String;
  String get priority => json['priority'] as String;
  String get description => (json['description'] as String?) ?? '';
  Map<String, dynamic> get property =>
      (json['property'] as Map).cast<String, dynamic>();
  String get propertyName => property['name'] as String? ?? '';
  String get address => property['address'] as String? ?? '';
  String? get accessNotes => property['contact_instructions'] as String?;
  Map<String, dynamic>? get asset =>
      (json['asset'] as Map?)?.cast<String, dynamic>();
  String get assetLabel {
    final a = asset;
    return a == null ? '—' : '${a['code']} · ${a['name']}';
  }

  String get categoryName => (json['category'] as Map)['name'] as String;
  int get estimatedMinutes =>
      ((json['category'] as Map)['default_duration_minutes'] as int?) ?? 0;
  Map<String, dynamic>? get assignment =>
      (json['assignment'] as Map?)?.cast<String, dynamic>();
  String? get assignmentId => assignment?['id'] as String?;
  DateTime? get startAt => _parse(assignment?['start_at']);
  DateTime? get endAt => _parse(assignment?['end_at']);
  Map<String, dynamic> get sla => (json['sla'] as Map).cast<String, dynamic>();
  String get slaState => sla['state'] as String;
  DateTime? get slaDueAt => _parse(sla['due_at']);
  Map<String, dynamic>? get estimate =>
      (json['estimate'] as Map?)?.cast<String, dynamic>();
  String? get startBlockedReason => json['start_blocked_reason'] as String?;
  String? get blockerReason => json['blocker_reason'] as String?;
  List<String> get allowedActions =>
      ((json['allowed_actions'] as List?) ?? const []).cast<String>();
  bool can(String action) => allowedActions.contains(action);

  static DateTime? _parse(Object? value) =>
      value is String ? DateTime.tryParse(value)?.toLocal() : null;

  String get appointmentText {
    final s = startAt;
    final e = endAt;
    if (s == null || e == null) return 'Not scheduled';
    final day = DateFormat('EEE d MMM').format(s);
    final from = DateFormat('HH:mm').format(s);
    final to = DateFormat('HH:mm').format(e);
    return '$day, $from–$to';
  }
}

class NoteItem {
  const NoteItem({
    required this.id,
    required this.author,
    required this.body,
    required this.createdAt,
    required this.internal,
  });

  final String id;
  final String author;
  final String body;
  final DateTime createdAt;
  final bool internal;

  factory NoteItem.fromJson(Map<String, dynamic> json) => NoteItem(
        id: json['id'] as String,
        author: json['author_name'] as String,
        body: json['body'] as String,
        createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
        internal: json['visibility'] == 'INTERNAL',
      );
}

class NotificationItem {
  const NotificationItem({
    required this.id,
    required this.title,
    required this.body,
    required this.createdAt,
    required this.read,
    this.requestId,
  });

  final String id;
  final String title;
  final String body;
  final DateTime createdAt;
  final bool read;
  final String? requestId;

  factory NotificationItem.fromJson(Map<String, dynamic> json) =>
      NotificationItem(
        id: json['id'] as String,
        title: json['title'] as String,
        body: (json['body'] as String?) ?? '',
        createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
        read: json['read_at'] != null,
        requestId: json['request_id'] as String?,
      );
}

class InventoryItem {
  const InventoryItem(
      {required this.id,
      required this.code,
      required this.name,
      required this.unit,
      required this.stock});

  final String id;
  final String code;
  final String name;
  final String unit;
  final int stock;

  factory InventoryItem.fromJson(Map<String, dynamic> json) => InventoryItem(
        id: json['id'] as String,
        code: json['code'] as String,
        name: json['name'] as String,
        unit: json['unit'] as String,
        stock: json['stock_quantity'] as int,
      );
}

class AvailabilitySlot {
  const AvailabilitySlot(this.weekday, this.startsAt, this.endsAt);
  final int weekday;
  final String startsAt;
  final String endsAt;
}

class TechnicianProfile {
  const TechnicianProfile(
      {required this.fullName,
      required this.skills,
      required this.availability,
      required this.timeOff});

  final String fullName;
  final List<String> skills;
  final List<AvailabilitySlot> availability;
  final List<String> timeOff;
}

/// Lifecycle of an offline note while it waits to be delivered.
enum QueueState { pending, syncing, conflict, failed }

/// A note (with optional photos) written on the device. The [id] is the stable client
/// command id: every delivery attempt reuses it, so the server stores the note once.
class QueuedNote {
  QueuedNote({
    required this.id,
    required this.userId,
    required this.orgId,
    required this.requestId,
    required this.reference,
    required this.title,
    required this.assignmentId,
    required this.body,
    required this.internal,
    required this.imagePaths,
    required this.createdAt,
    this.state = QueueState.pending,
    this.reason,
    this.noteId,
    this.uploadedImages = 0,
    this.attempts = 0,
  });

  final String id;
  final String userId;
  final String orgId;
  final String requestId;
  final String reference;
  final String title;
  final String? assignmentId;
  final String body;
  final bool internal;
  final List<String> imagePaths;
  final DateTime createdAt;
  QueueState state;
  String? reason;

  /// Server id of the note once created; lets an interrupted delivery resume.
  String? noteId;
  int uploadedImages;
  int attempts;

  String imageCommandId(int index) => '$id-img-$index';

  Map<String, dynamic> toJson() => {
        'id': id,
        'userId': userId,
        'orgId': orgId,
        'requestId': requestId,
        'reference': reference,
        'title': title,
        'assignmentId': assignmentId,
        'body': body,
        'internal': internal,
        'imagePaths': imagePaths,
        'createdAt': createdAt.toIso8601String(),
        'state': state.name,
        'reason': reason,
        'noteId': noteId,
        'uploadedImages': uploadedImages,
        'attempts': attempts,
      };

  factory QueuedNote.fromJson(Map<String, dynamic> json) {
    var state = QueueState.values.firstWhere(
      (s) => s.name == json['state'],
      orElse: () => QueueState.pending,
    );
    // A crash mid-delivery leaves "syncing" behind; it is simply pending again.
    if (state == QueueState.syncing) state = QueueState.pending;
    return QueuedNote(
      id: json['id'] as String,
      userId: json['userId'] as String,
      orgId: json['orgId'] as String,
      requestId: json['requestId'] as String,
      reference: json['reference'] as String,
      title: json['title'] as String,
      assignmentId: json['assignmentId'] as String?,
      body: json['body'] as String,
      internal: (json['internal'] as bool?) ?? false,
      imagePaths: ((json['imagePaths'] as List?) ?? const []).cast<String>(),
      createdAt: DateTime.parse(json['createdAt'] as String),
      state: state,
      reason: json['reason'] as String?,
      noteId: json['noteId'] as String?,
      uploadedImages: (json['uploadedImages'] as int?) ?? 0,
      attempts: (json['attempts'] as int?) ?? 0,
    );
  }
}
