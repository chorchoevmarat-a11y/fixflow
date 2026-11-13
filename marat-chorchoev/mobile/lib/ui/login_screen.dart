import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _server;
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _server = TextEditingController(text: ref.read(sessionProvider).serverUrl);
  }

  @override
  void dispose() {
    _server.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || !_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    String? error;
    try {
      error = await ref
          .read(sessionProvider.notifier)
          .signIn(_server.text, _email.text, _password.text);
    } catch (_) {
      error = 'Sign-in failed unexpectedly. Please try again.';
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = error;
    });
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    if (session.choosingOrg) return const _OrganizationPicker();
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text('FixFlow',
                        style: Theme.of(context).textTheme.headlineLarge),
                    const SizedBox(height: 4),
                    const Text('Salymbekov University · Technician sign-in'),
                    const SizedBox(height: 16),
                    if (session.expired)
                      const Card(
                        child: Padding(
                          padding: EdgeInsets.all(12),
                          child: Text(
                            'Your session ended. Sign in again — notes you wrote offline are kept and will be sent.',
                          ),
                        ),
                      ),
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Semantics(
                          liveRegion: true,
                          child: Text(_error!,
                              style: TextStyle(
                                  color: Theme.of(context).colorScheme.error)),
                        ),
                      ),
                    TextFormField(
                      controller: _server,
                      decoration: const InputDecoration(
                        labelText: 'Server address',
                        helperText:
                            'Emulator: http://10.0.2.2:8000 · Phone: http://<computer-LAN-IP>:8000',
                      ),
                      keyboardType: TextInputType.url,
                      validator: (v) => (v == null ||
                              !RegExp(r'^https?://\S+$').hasMatch(v.trim()))
                          ? 'Enter a full http(s) address.'
                          : null,
                    ),
                    TextFormField(
                      controller: _email,
                      decoration: const InputDecoration(labelText: 'Email'),
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.username],
                      validator: (v) => (v == null || !v.contains('@'))
                          ? 'Enter your email address.'
                          : null,
                    ),
                    TextFormField(
                      controller: _password,
                      decoration: const InputDecoration(labelText: 'Password'),
                      obscureText: true,
                      autofillHints: const [AutofillHints.password],
                      validator: (v) => (v == null || v.isEmpty)
                          ? 'Enter your password.'
                          : null,
                      onFieldSubmitted: (_) => _submit(),
                    ),
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      child: _busy
                          ? const SizedBox(
                              height: 18,
                              width: 18,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('Sign in'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _OrganizationPicker extends ConsumerWidget {
  const _OrganizationPicker();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Choose organization')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
              'You work for more than one Salymbekov University unit. Pick one; you can switch later from Profile.'),
          const SizedBox(height: 12),
          for (final m in session.memberships)
            Card(
              child: ListTile(
                title: Text(m.organizationName),
                subtitle: Text(m.role.toLowerCase()),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => ref
                    .read(sessionProvider.notifier)
                    .chooseOrg(m.organizationId),
              ),
            ),
        ],
      ),
    );
  }
}
