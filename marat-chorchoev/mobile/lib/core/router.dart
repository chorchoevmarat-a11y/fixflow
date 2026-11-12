import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../features/auth/auth_state.dart';
import '../features/auth/login_screen.dart';
import '../features/auth/org_selector_screen.dart';
import '../features/jobs/jobs_screen.dart';
import '../features/jobs/job_detail_screen.dart';
import '../features/notes/note_compose_screen.dart';
import '../features/inventory/material_usage_screen.dart';
import '../features/notifications/notifications_screen.dart';
import '../features/profile/profile_screen.dart';

// ─── Route names ─────────────────────────────────────────────────────────────

class AppRoutes {
  static const login = '/login';
  static const orgSelector = '/org-selector';
  static const jobs = '/jobs';
  static const jobDetail = '/jobs/:id';
  static const noteCompose = '/jobs/:id/note';
  static const materialUsage = '/jobs/:id/materials';
  static const notifications = '/notifications';
  static const profile = '/profile';
}

// ─── Router provider ─────────────────────────────────────────────────────────

final routerProvider = Provider<GoRouter>((ref) {
  final authNotifier = ref.watch(authStateNotifierProvider.notifier);

  return GoRouter(
    initialLocation: AppRoutes.login,
    refreshListenable: authNotifier,
    redirect: (context, state) {
      final authState = ref.read(authStateNotifierProvider);
      final isLoggingIn = state.matchedLocation == AppRoutes.login;
      final isSelectingOrg = state.matchedLocation == AppRoutes.orgSelector;

      return authState.when(
        initial: () => null,
        loading: () => null,
        needsOrgSelection: (_) =>
            isSelectingOrg ? null : AppRoutes.orgSelector,
        authenticated: (_) =>
            (isLoggingIn || isSelectingOrg) ? AppRoutes.jobs : null,
        unauthenticated: () => isLoggingIn ? null : AppRoutes.login,
        error: (_) => AppRoutes.login,
      );
    },
    routes: [
      GoRoute(
        path: AppRoutes.login,
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: AppRoutes.orgSelector,
        builder: (context, state) => const OrgSelectorScreen(),
      ),
      ShellRoute(
        builder: (context, state, child) => _MainShell(child: child),
        routes: [
          GoRoute(
            path: AppRoutes.jobs,
            builder: (context, state) => const JobsScreen(),
            routes: [
              GoRoute(
                path: ':id',
                builder: (context, state) =>
                    JobDetailScreen(jobId: state.pathParameters['id']!),
                routes: [
                  GoRoute(
                    path: 'note',
                    builder: (context, state) =>
                        NoteComposeScreen(jobId: state.pathParameters['id']!),
                  ),
                  GoRoute(
                    path: 'materials',
                    builder: (context, state) => MaterialUsageScreen(
                      jobId: state.pathParameters['id']!,
                    ),
                  ),
                ],
              ),
            ],
          ),
          GoRoute(
            path: AppRoutes.notifications,
            builder: (context, state) => const NotificationsScreen(),
          ),
          GoRoute(
            path: AppRoutes.profile,
            builder: (context, state) => const ProfileScreen(),
          ),
        ],
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      body: Center(child: Text('Page not found: ${state.error}')),
    ),
  );
});

// ─── Main shell with bottom nav ───────────────────────────────────────────────

class _MainShell extends StatelessWidget {
  final Widget child;
  const _MainShell({required this.child});

  static const _tabs = [
    AppRoutes.jobs,
    AppRoutes.notifications,
    AppRoutes.profile,
  ];

  int _currentIndex(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    if (location.startsWith(AppRoutes.jobs)) return 0;
    if (location.startsWith(AppRoutes.notifications)) return 1;
    if (location.startsWith(AppRoutes.profile)) return 2;
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: child,
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex(context),
        onTap: (i) => context.go(_tabs[i]),
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.work), label: 'Jobs'),
          BottomNavigationBarItem(
            icon: Icon(Icons.notifications),
            label: 'Alerts',
          ),
          BottomNavigationBarItem(icon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
}
