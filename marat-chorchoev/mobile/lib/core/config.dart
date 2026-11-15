/// Build-time default API address.
///
/// * Android emulator: `http://10.0.2.2:8000` (the emulator's alias for the host machine)
/// * Physical device: pass `--dart-define=API_BASE_URL=http://<your-LAN-IP>:8000`
///   at build time, or simply type the address on the sign-in screen — it is stored on
///   the device, so no rebuild and no secret in the APK is ever needed.
class AppConfig {
  static const String defaultBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );
  static const String apiPrefix = '/api/v1';
}
