import '../../core/api_client.dart';
import 'auth_state.dart';

class LoginResult {
  final String accessToken;
  final List<OrgChoice>? orgs;

  const LoginResult({required this.accessToken, this.orgs});
}

class AuthRepository {
  final ApiClient _client;

  AuthRepository(this._client);

  Future<LoginResult> login({
    required String email,
    required String password,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/login',
      data: {'email': email, 'password': password},
    );
    final data = response.data!;
    final token = data['access_token'] as String;
    final orgList = data['organizations'] as List<dynamic>?;

    return LoginResult(
      accessToken: token,
      orgs: orgList?.map((o) => OrgChoice.fromJson(o as Map<String, dynamic>)).toList(),
    );
  }

  Future<LoginResult> switchOrg({
    required String orgId,
    required String token,
  }) async {
    _client.setToken(token);
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/switch-org',
      data: {'organization_id': orgId},
    );
    final data = response.data!;
    return LoginResult(accessToken: data['access_token'] as String);
  }

  Future<UserProfile> getProfile() async {
    final response = await _client.get<Map<String, dynamic>>('/auth/me');
    return UserProfile.fromJson(response.data!);
  }

  Future<void> logout() async {
    try {
      await _client.post('/auth/logout');
    } catch (_) {
      // best-effort
    }
  }
}
