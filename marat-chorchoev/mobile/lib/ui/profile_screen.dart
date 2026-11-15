import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import 'unsent_notes_screen.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final queue = ref.watch(queueProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(session.fullName ?? ''),
              subtitle: Text(session.email ?? '')),
          ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Server'),
              subtitle: Text(session.serverUrl)),
          if (session.memberships.length > 1)
            DropdownButtonFormField<String>(
              initialValue: session.orgId,
              decoration: const InputDecoration(labelText: 'Organization'),
              items: [
                for (final m in session.memberships)
                  DropdownMenuItem(
                      value: m.organizationId, child: Text(m.organizationName))
              ],
              onChanged: (value) {
                if (value != null && value != session.orgId) {
                  ref.read(sessionProvider.notifier).chooseOrg(value);
                }
              },
            )
          else
            ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Organization'),
                subtitle: Text(session.membership?.organizationName ?? '')),
          const Divider(),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.outbox),
            title: const Text('Unsent notes'),
            subtitle: Text('${queue.notes.length} waiting'),
            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => const UnsentNotesScreen())),
          ),
          const SizedBox(height: 16),
          OutlinedButton.icon(
            icon: const Icon(Icons.logout),
            label: const Text('Sign out'),
            onPressed: () async {
              final warn = queue.notes.isNotEmpty;
              final ok = await showDialog<bool>(
                context: context,
                builder: (_) => AlertDialog(
                  title: const Text('Sign out?'),
                  content: Text(warn
                      ? 'You have ${queue.notes.length} unsent note(s). They stay on this phone and send after you sign in again.'
                      : 'You will need to sign in again.'),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(context, false),
                        child: const Text('Cancel')),
                    FilledButton(
                        onPressed: () => Navigator.pop(context, true),
                        child: const Text('Sign out')),
                  ],
                ),
              );
              if (ok == true) {
                await ref.read(sessionProvider.notifier).signOut();
              }
            },
          ),
        ],
      ),
    );
  }
}
