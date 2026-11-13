import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

import 'api.dart';
import 'config.dart';
import 'models.dart';
import 'store.dart';
import 'sync.dart';

const _uuid = Uuid();

String newCommandId(String prefix) => '$prefix-${_uuid.v4()}';

// ---------------------------------------------------------------- infrastructure

/// Overridden in `main()` with the opened store.
final storeProvider =
    Provider<LocalStore>((ref) => throw UnimplementedError('storeProvider'));

/// Bearer token storage. Production uses the Android keystore; tests use memory.
abstract class SecretStore {
  Future<String?> read();
  Future<void> write(String token);
  Future<void> clear();
}

class KeystoreSecretStore implements SecretStore {
  const KeystoreSecretStore();
  static const _storage = FlutterSecureStorage();
  @override
  Future<String?> read() => _storage.read(key: 'fixflow.token');
  @override
  Future<void> write(String token) =>
      _storage.write(key: 'fixflow.token', value: token);
  @override
  Future<void> clear() => _storage.delete(key: 'fixflow.token');
}

class MemorySecretStore implements SecretStore {
  String? token;
  @override
  Future<String?> read() async => token;
  @override
  Future<void> write(String value) async => token = value;
  @override
  Future<void> clear() async => token = null;
}

final secretStoreProvider =
    Provider<SecretStore>((ref) => const KeystoreSecretStore());

/// Token read before the first frame so the session can be restored synchronously.
final initialTokenProvider = Provider<String?>((ref) => null);

// ---------------------------------------------------------------- session

class SessionState {
  const SessionState({
    this.serverUrl = AppConfig.defaultBaseUrl,
    this.token,
    this.userId,
    this.email,
    this.fullName,
    this.memberships = const [],
    this.orgId,
    this.expiresAt,
    this.expired = false,
    this.choosingOrg = false,
  });

  final String serverUrl;
  final String? token;
  final String? userId;
  final String? email;
  final String? fullName;
  final List<Membership> memberships;
  final String? orgId;
  final DateTime? expiresAt;

  /// The server (or the clock) ended the session; the sign-in screen explains it.
  final bool expired;

  /// Signed in, but the person must still pick one of several memberships (AUTH-03).
  final bool choosingOrg;

  bool get signedIn =>
      token != null && userId != null && orgId != null && !choosingOrg;
  Membership? get membership {
    for (final m in memberships) {
      if (m.organizationId == orgId) return m;
    }
    return null;
  }

  String get scope => '$userId:$orgId';

  SessionState copyWith({
    String? serverUrl,
    String? token,
    String? orgId,
    bool? expired,
    bool? choosingOrg,
  }) =>
      SessionState(
        serverUrl: serverUrl ?? this.serverUrl,
        token: token ?? this.token,
        userId: userId,
        email: email,
        fullName: fullName,
        memberships: memberships,
        orgId: orgId ?? this.orgId,
        expiresAt: expiresAt,
        expired: expired ?? this.expired,
        choosingOrg: choosingOrg ?? this.choosingOrg,
      );
}

class SessionNotifier extends Notifier<SessionState> {
  @override
  SessionState build() {
    final store = ref.read(storeProvider);
    final saved = store.session;
    final token = ref.read(initialTokenProvider);
    final url = store.serverUrl ?? AppConfig.defaultBaseUrl;
    if (saved == null || token == null) return SessionState(serverUrl: url);
    final expiresAt = DateTime.tryParse(saved['expiresAt'] as String? ?? '');
    final expired =
        expiresAt != null && expiresAt.isBefore(DateTime.now().toUtc());
    return SessionState(
      serverUrl: url,
      token: expired ? null : token,
      userId: saved['userId'] as String?,
      email: saved['email'] as String?,
      fullName: saved['fullName'] as String?,
      memberships: [
        for (final m in (saved['memberships'] as List? ?? const []))
          Membership.fromJson((m as Map).cast<String, dynamic>()),
      ],
      orgId: saved['orgId'] as String?,
      expiresAt: expiresAt,
      expired: expired,
    );
  }

  /// Returns an error message, or null on success.
  Future<String?> signIn(
      String serverUrl, String email, String password) async {
    final url = serverUrl.trim().replaceAll(RegExp(r'/+$'), '');
    final api =
        HttpFixflowApi(baseUrl: url, token: () => null, orgId: () => null);
    try {
      final result = await api.login(email.trim(), password);
      final technicianOrgs =
          result.memberships.where((m) => m.role == 'TECHNICIAN').toList();
      if (technicianOrgs.isEmpty) {
        return 'This account has no technician role. Dispatchers and requesters use the web app.';
      }
      final store = ref.read(storeProvider);
      await store.setServerUrl(url);
      await ref.read(secretStoreProvider).write(result.token);
      final orgId = technicianOrgs.length == 1
          ? technicianOrgs.first.organizationId
          : null;
      state = SessionState(
        serverUrl: url,
        token: result.token,
        userId: result.userId,
        email: result.email,
        fullName: result.fullName,
        memberships: technicianOrgs,
        orgId: orgId ?? technicianOrgs.first.organizationId,
        expiresAt: result.expiresAt,
        choosingOrg: orgId == null,
      );
      if (orgId != null) await _persist();
      return null;
    } on ApiException catch (e) {
      if (e.code == 'BAD_ADDRESS') return e.message;
      if (e.isNetwork) {
        return 'Cannot reach $url. Check the server address and your connection.';
      }
      return e.message;
    } catch (_) {
      return 'Sign-in failed unexpectedly. Check the server address and try again.';
    }
  }

  Future<void> chooseOrg(String orgId) async {
    // A different organization never inherits cached data of the previous one.
    final previous = state.orgId;
    state = state.copyWith(orgId: orgId, choosingOrg: false);
    if (previous != null && previous != orgId) {
      await ref.read(storeProvider).dropJobs('${state.userId}:$previous');
    }
    await _persist();
  }

  Future<void> _persist() async {
    await ref.read(storeProvider).setSession({
      'userId': state.userId,
      'email': state.email,
      'fullName': state.fullName,
      'orgId': state.orgId,
      'expiresAt': state.expiresAt?.toUtc().toIso8601String(),
      'memberships': [for (final m in state.memberships) m.toJson()],
    });
  }

  /// The server rejected the token (expired, revoked, deactivated).
  Future<void> markExpired() async {
    if (state.token == null) return;
    await ref.read(secretStoreProvider).clear();
    state = SessionState(
      serverUrl: state.serverUrl,
      userId: state.userId,
      email: state.email,
      fullName: state.fullName,
      memberships: state.memberships,
      orgId: state.orgId,
      expired: true,
    );
  }

  Future<void> signOut() async {
    // Built here instead of `ref.read(apiProvider)`: apiProvider depends on this notifier,
    // so reading it from inside the notifier is a circular dependency. Riverpod throws
    // CircularDependencyError and the Sign out button silently did nothing.
    final token = state.token;
    final orgId = state.orgId;
    final api = HttpFixflowApi(
        baseUrl: state.serverUrl, token: () => token, orgId: () => orgId);
    try {
      // Best effort and bounded: an unreachable server must not hold up signing out.
      await api.logout().timeout(const Duration(seconds: 5));
    } catch (_) {
      // Offline sign-out still clears the device; the server session simply expires.
    }
    final store = ref.read(storeProvider);
    // Cached jobs of this account are removed; unsent notes are deliberately kept so
    // signing out never destroys work (they send after the next sign-in).
    if (state.userId != null && state.orgId != null) {
      await store.dropJobs(state.scope);
    }
    await store.setSession(null);
    await ref.read(secretStoreProvider).clear();
    state = SessionState(serverUrl: state.serverUrl);
  }
}

final sessionProvider =
    NotifierProvider<SessionNotifier, SessionState>(SessionNotifier.new);

final apiProvider = Provider<FixflowApi>((ref) {
  return HttpFixflowApi(
    baseUrl: ref.watch(sessionProvider.select((s) => s.serverUrl)),
    token: () => ref.read(sessionProvider).token,
    orgId: () => ref.read(sessionProvider).orgId,
  );
});

// ---------------------------------------------------------------- connectivity

class OnlineNotifier extends Notifier<bool> {
  StreamSubscription<List<ConnectivityResult>>? _sub;

  @override
  bool build() {
    ref.onDispose(() => _sub?.cancel());
    try {
      _sub = Connectivity().onConnectivityChanged.listen((results) {
        state = results.any((r) => r != ConnectivityResult.none);
      });
    } catch (_) {
      // Platform channel unavailable (tests): stay optimistic; API errors still flip it.
    }
    return true;
  }

  /// Real reachability beats link state: a failed call proves we are effectively offline.
  void report(bool online) {
    if (state != online) state = online;
  }
}

final onlineProvider =
    NotifierProvider<OnlineNotifier, bool>(OnlineNotifier.new);

// ---------------------------------------------------------------- jobs

class JobsState {
  const JobsState({
    this.jobs = const [],
    this.loading = false,
    this.lastSync,
    this.error,
  });

  final List<Job> jobs;
  final bool loading;
  final DateTime? lastSync;
  final ApiException? error;

  JobsState copyWith(
          {List<Job>? jobs,
          bool? loading,
          DateTime? lastSync,
          ApiException? error,
          bool clearError = false}) =>
      JobsState(
        jobs: jobs ?? this.jobs,
        loading: loading ?? this.loading,
        lastSync: lastSync ?? this.lastSync,
        error: clearError ? null : (error ?? this.error),
      );
}

class JobsNotifier extends Notifier<JobsState> {
  @override
  JobsState build() {
    final session = ref.watch(sessionProvider);
    if (!session.signedIn) return const JobsState();
    final store = ref.read(storeProvider);
    // Cached jobs are available instantly and offline (MOB-04).
    return JobsState(
        jobs: store.cachedJobs(session.scope),
        lastSync: store.lastSync(session.scope));
  }

  Future<void> refresh() async {
    final session = ref.read(sessionProvider);
    if (!session.signedIn) return;
    state = state.copyWith(loading: true, clearError: true);
    try {
      final jobs = await ref.read(apiProvider).assignedJobs();
      await ref.read(storeProvider).saveJobs(session.scope, jobs);
      ref.read(onlineProvider.notifier).report(true);
      state = JobsState(jobs: jobs, lastSync: DateTime.now());
    } on ApiException catch (e) {
      if (e.isNetwork) ref.read(onlineProvider.notifier).report(false);
      if (e.isUnauthorized) {
        await ref.read(sessionProvider.notifier).markExpired();
      }
      state = state.copyWith(loading: false, error: e);
    }
  }

  /// Replace one job after an online action so the screen reflects server truth.
  Future<void> replace(Job updated) async {
    final session = ref.read(sessionProvider);
    final jobs = [for (final j in state.jobs) j.id == updated.id ? updated : j];
    await ref.read(storeProvider).saveJobs(session.scope, jobs);
    state = state.copyWith(jobs: jobs);
  }

  Future<void> remove(String id) async {
    final session = ref.read(sessionProvider);
    final jobs = [
      for (final j in state.jobs)
        if (j.id != id) j
    ];
    await ref.read(storeProvider).saveJobs(session.scope, jobs);
    state = state.copyWith(jobs: jobs);
  }
}

final jobsProvider =
    NotifierProvider<JobsNotifier, JobsState>(JobsNotifier.new);

// ---------------------------------------------------------------- offline queue

class QueueState2 {
  const QueueState2(
      {this.notes = const [], this.syncing = false, this.lastReport});
  final List<QueuedNote> notes;
  final bool syncing;
  final SyncReport? lastReport;

  int get pending => notes
      .where(
          (n) => n.state == QueueState.pending || n.state == QueueState.syncing)
      .length;
  int get conflicts =>
      notes.where((n) => n.state == QueueState.conflict).length;
  int get failed => notes.where((n) => n.state == QueueState.failed).length;
}

class QueueNotifier extends Notifier<QueueState2> {
  SyncService get _sync =>
      SyncService(ref.read(apiProvider), ref.read(storeProvider));

  @override
  QueueState2 build() {
    final session = ref.watch(sessionProvider);
    if (!session.signedIn) return const QueueState2();
    ref.listen<bool>(onlineProvider, (previous, online) {
      if (online && previous == false) unawaited(syncNow());
    });
    return QueueState2(notes: _mine(session));
  }

  List<QueuedNote> _mine(SessionState session) => [
        for (final n in ref.read(storeProvider).queue)
          if (n.userId == session.userId && n.orgId == session.orgId) n,
      ];

  void _reload() => state = QueueState2(
        notes: _mine(ref.read(sessionProvider)),
        syncing: state.syncing,
        lastReport: state.lastReport,
      );

  Future<void> enqueue({
    required Job job,
    required String body,
    required bool internal,
    required List<String> photoPaths,
    required String commandId,
  }) async {
    final session = ref.read(sessionProvider);
    await _sync.enqueue(
      userId: session.userId!,
      orgId: session.orgId!,
      job: job,
      body: body,
      internal: internal,
      photoPaths: photoPaths,
      commandId: commandId,
    );
    _reload();
    unawaited(syncNow());
  }

  Future<void> syncNow() async {
    final session = ref.read(sessionProvider);
    if (!session.signedIn || state.syncing) return;
    state = QueueState2(
        notes: state.notes, syncing: true, lastReport: state.lastReport);
    try {
      final report =
          await _sync.replay(userId: session.userId!, orgId: session.orgId!);
      if (report.stoppedOffline) {
        ref.read(onlineProvider.notifier).report(false);
      }
      if (report.delivered > 0) ref.read(onlineProvider.notifier).report(true);
      if (report.sessionExpired) {
        await ref.read(sessionProvider.notifier).markExpired();
      }
      state = QueueState2(
          notes: _mine(ref.read(sessionProvider)), lastReport: report);
    } catch (_) {
      state = QueueState2(notes: _mine(ref.read(sessionProvider)));
    }
  }

  Future<void> discard(String id) async {
    await _sync.discard(id);
    _reload();
  }

  Future<void> retry(String id) async {
    await _sync.retry(id);
    _reload();
    unawaited(syncNow());
  }
}

final queueProvider =
    NotifierProvider<QueueNotifier, QueueState2>(QueueNotifier.new);
