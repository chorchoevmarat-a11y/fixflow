import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'auth_state.dart';

class OrgSelectorScreen extends ConsumerWidget {
  const OrgSelectorScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authStateNotifierProvider);

    final orgs =
        authState is AuthNeedsOrgSelection ? authState.orgs : <OrgChoice>[];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Select Organization'),
        automaticallyImplyLeading: false,
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              'Your account has access to multiple organizations. Choose one to continue.',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(
            child: ListView.separated(
              itemCount: orgs.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, i) {
                final org = orgs[i];
                return ListTile(
                  leading: CircleAvatar(
                    backgroundColor:
                        Theme.of(context).colorScheme.primaryContainer,
                    child: Text(
                      org.name.isNotEmpty ? org.name[0].toUpperCase() : 'O',
                      style: TextStyle(
                        color:
                            Theme.of(context).colorScheme.onPrimaryContainer,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  title: Text(org.name),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () {
                    // The pending token was stored when login returned orgs.
                    // We retrieve it from secure storage via repo in notifier.
                    ref
                        .read(authStateNotifierProvider.notifier)
                        .selectOrg(org.id, '');
                  },
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextButton(
              onPressed: () =>
                  ref.read(authStateNotifierProvider.notifier).logout(),
              child: const Text('Sign out'),
            ),
          ),
        ],
      ),
    );
  }
}
