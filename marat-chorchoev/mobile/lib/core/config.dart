class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static const String apiVersion = '/api/v1';

  static String get apiUrl => '$apiBaseUrl$apiVersion';
}
