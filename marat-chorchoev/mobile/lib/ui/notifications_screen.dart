import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../core/models.dart';
import '../core/providers.dart';
import 'widgets.dart';

class NotificationsScreen extends ConsumerStatefulWidget {
  const NotificationsScreen({super.key});

  @override
  ConsumerState<NotificationsScreen> createState() =>
      _NotificationsScreenState();
}

class _NotificationsScreenState extends ConsumerState<NotificationsScreen> {
  List<NotificationItem>? _items;
  ApiException? _error;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  Future<void> _load() async {
    try {
      final items = await ref.read(apiProvider).notifications();
      if (mounted) {
        setState(() {
          _items = items;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (e.isUnauthorized) {
        await ref.read(sessionProvider.notifier).markExpired();
      }
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _read(NotificationItem n) async {
    if (n.read) return;
    try {
      await ref.read(apiProvider).markNotificationRead(n.id);
      await _load();
    } on ApiException {
      // leave it unread; it will be marked on the next attempt
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    Widget body;
    if (_error != null && items == null) {
      body = StateMessage.forError(_error!, onRetry: _load);
    } else if (items == null) {
      body = const Center(child: CircularProgressIndicator());
    } else if (items.isEmpty) {
      body = const StateMessage(
          icon: Icons.notifications_none,
          title: 'No notifications',
          message: 'Assignments and changes to your jobs show up here.');
    } else {
      body = ListView(
        children: [
          for (final n in items)
            ListTile(
              leading: Icon(n.read
                  ? Icons.notifications_none
                  : Icons.notifications_active),
              title: Text(n.title,
                  style: TextStyle(
                      fontWeight:
                          n.read ? FontWeight.normal : FontWeight.bold)),
              subtitle: Text(
                  '${n.body}\n${DateFormat('d MMM HH:mm').format(n.createdAt)}'),
              isThreeLine: n.body.isNotEmpty,
              onTap: () => _read(n),
            ),
        ],
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications'), actions: [
        IconButton(
            tooltip: 'Refresh',
            onPressed: _load,
            icon: const Icon(Icons.refresh))
      ]),
      body: Column(children: [
        const StatusBanner(),
        Expanded(child: RefreshIndicator(onRefresh: _load, child: body))
      ]),
    );
  }
}
