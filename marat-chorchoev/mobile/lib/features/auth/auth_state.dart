import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../core/config.dart';
import 'auth_repository.dart';

// ─── Models ──────────────────────────────────────────────────────────────────

class UserProfile {
  final String id;
  final String email;
  final String fullName;
  final String role;
  final String? organizationId;
  final String? organizationName;

  const UserProfile({
    required this.id,
    required this.email,
    required this.fullName,
    required this.role,
    this.organizationId,
    this.organizationName,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) => UserProfile(
    id: json['id'] as String,
    email: json['email'] as String,
    fullName: json['full_name'] as String,
    role: json['role'] as String,
    organizationId: json['organization_id'] as String?,
    organizationName: json['organization_name'] as String?,
  );
}

class OrgChoice {
  final String id;
  final String name;

  const OrgChoice({required this.id, required this.name});

  factory OrgChoice.fromJson(Map<String, dynamic> json) => OrgChoice(
    id: json['id'] as String,
    name: json['name'] as String,
  );
}

// ─── Auth state ───────────────────────────────────────────────────────────────

@immutable
sealed class AuthState {
  const AuthState();

  T when<T>({
    required T Function() initial,
    required T Function() loading,
    required T Function(List<OrgChoice> orgs) needsOrgSelection,
    required T Function(UserProfile user) authenticated,
    required T Function() unauthenticated,
    required T Function(String message) error,
  }) {
    return switch (this) {
      AuthInitial() => initial(),
      AuthLoading() => loading(),
      AuthNeedsOrgSelection(orgs: final o) => needsOrgSelection(o),
      AuthAuthenticated(user: final u) => authenticated(u),
      AuthUnauthenticated() => unauthenticated(),
      AuthError(message: final m) => error(m),
    };
  }
}

class AuthInitial extends AuthState {
  const AuthInitial();
}

class AuthLoading extends AuthState {
  const AuthLoading();
}

class AuthNeedsOrgSelection extends AuthState {
  final List<OrgChoice> orgs;
  const AuthNeedsOrgSelection(this.orgs);
}

class AuthAuthenticated extends AuthState {
  final UserProfile user;
  const AuthAuthenticated(this.user);
}

class AuthUnauthenticated extends AuthState {
  const AuthUnauthenticated();
}

class AuthError extends AuthState {
  final String message;
  const AuthError(this.message);
}

// ─── Notifier ─────────────────────────────────────────────────────────────────

class AuthStateNotifier extends StateNotifier<AuthState>
    with ChangeNotifier {
  final AuthRepository _repo;

  AuthStateNotifier(this._repo) : super(const AuthInitial()) {
    _init();
  }

  Future<void> _init() async {
    state = const AuthLoading();
    try {
      final token = await readToken();
      if (token == null) {
        state = const AuthUnauthenticated();
        return;
      }
      final profile = await _repo.getProfile();
      state = AuthAuthenticated(profile);
    } catch (_) {
      await clearToken();
      state = const AuthUnauthenticated();
    }
    notifyListeners();
  }

  Future<void> login(String email, String password) async {
    state = const AuthLoading();
    try {
      final result = await _repo.login(email: email, password: password);
      if (result.orgs != null && result.orgs!.isNotEmpty) {
        state = AuthNeedsOrgSelection(result.orgs!);
      } else {
        await persistToken(result.accessToken);
        final profile = await _repo.getProfile();
        state = AuthAuthenticated(profile);
      }
    } on ApiException catch (e) {
      state = AuthError(e.message);
    } catch (e) {
      state = AuthError(e.toString());
    }
    notifyListeners();
  }

  Future<void> selectOrg(String orgId, String pendingToken) async {
    state = const AuthLoading();
    try {
      final result = await _repo.switchOrg(orgId: orgId, token: pendingToken);
      await persistToken(result.accessToken);
      final profile = await _repo.getProfile();
      state = AuthAuthenticated(profile);
    } on ApiException catch (e) {
      state = AuthError(e.message);
    } catch (e) {
      state = AuthError(e.toString());
    }
    notifyListeners();
  }

  Future<void> logout() async {
    await clearToken();
    state = const AuthUnauthenticated();
    notifyListeners();
  }

  @override
  void addListener(VoidCallback listener) {
    super.addListener(listener);
  }
}

// ─── Providers ───────────────────────────────────────────────────────────────

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(ref.watch(apiClientProvider)),
);

final authStateNotifierProvider =
    StateNotifierProvider<AuthStateNotifier, AuthState>((ref) {
  return AuthStateNotifier(ref.watch(authRepositoryProvider));
});

final currentUserProvider = Provider<UserProfile?>((ref) {
  final state = ref.watch(authStateNotifierProvider);
  return state is AuthAuthenticated ? state.user : null;
});
