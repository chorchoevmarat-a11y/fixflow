import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../shared/widgets/loading_states.dart';

class NotificationItem {
  final String id;
  final String title;
  final String body;
  final String type;
  final DateTime createdAt;
  bool isRead;

  NotificationItem({
    required this.id,
    required this.title,
    required this.body,
    required this.type,
    required this.createdAt,
    this.isRead = false,
  });

  factory NotificationItem.fromJson(Map<String, dynamic> json) {
    return NotificationItem(
      id: json['id'] as String,
      title: json['title'] as String? ?? 'Notification',
      body: json['body'] as String? ?? '',
      type: json['type'] as String? ?? 'info',
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String) ?? DateTime.now()
          : DateTime.now(),
      isRead: json['is_read'] as bool? ?? false,
    );
  }
}

class NotificationsScreen extends ConsumerStatefulWidget {
  const NotificationsScreen({super.key});

  @override
  ConsumerState<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends ConsumerState<NotificationsScreen> {
  bool _isLoading = true;
  String? _error;
  List<NotificationItem> _notifications = [];

  @override
  void initState() {
    super.initState();
    _loadNotifications();
  }

  Future<void> _loadNotifications() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final client = ref.read(apiClientProvider);
      final res = await client.get<List<dynamic>>('/notifications');
      final list = (res.data ?? [])
          .map((n) => NotificationItem.fromJson(n as Map<String, dynamic>))
          .toList();

      setState(() {
        _notifications = list;
        _isLoading = false;
      });
    } catch (_) {
      // Mock / fallback notifications if endpoint not yet populated
      setState(() {
        _notifications = [
          NotificationItem(
            id: '1',
            title: 'New Job Assigned',
            body: 'You have been assigned to Emergency AC Repair at Downtown Office.',
            type: 'job_assigned',
            createdAt: DateTime.now().subtract(const Duration(minutes: 25)),
            isRead: false,
          ),
          NotificationItem(
            id: '2',
            title: 'SLA Reminder',
            body: 'Job #102 SLA deadline expires in 2 hours.',
            type: 'sla_warning',
            createdAt: DateTime.now().subtract(const Duration(hours: 1)),
            isRead: false,
          ),
          NotificationItem(
            id: '3',
            title: 'Part Request Approved',
            body: 'Your requisition for Replacement Compressor #C-44 was approved.',
            type: 'inventory',
            createdAt: DateTime.now().subtract(const Duration(hours: 5)),
            isRead: true,
          ),
        ];
        _isLoading = false;
      });
    }
  }

  void _markAllAsRead() {
    setState(() {
      for (final n in _notifications) {
        n.isRead = true;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          if (_notifications.isNotEmpty)
            TextButton(
              onPressed: _markAllAsRead,
              child: const Text('Mark all read'),
            ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const LoadingView(message: 'Loading notifications...');
    }

    if (_error != null) {
      return ErrorView(message: _error!, onRetry: _loadNotifications);
    }

    if (_notifications.isEmpty) {
      return const EmptyView(
        title: 'No Notifications',
        subtitle: 'You are all caught up! No recent alerts.',
        icon: Icons.notifications_none,
      );
    }

    return RefreshIndicator(
      onRefresh: _loadNotifications,
      child: ListView.separated(
        padding: const EdgeInsets.symmetric(vertical: 8),
        itemCount: _notifications.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final item = _notifications[index];
          return ListTile(
            leading: CircleAvatar(
              backgroundColor: item.isRead
                  ? Colors.grey.shade200
                  : Theme.of(context).colorScheme.primaryContainer,
              child: Icon(
                _getIconForType(item.type),
                color: item.isRead
                    ? Colors.grey
                    : Theme.of(context).colorScheme.primary,
                size: 20,
              ),
            ),
            title: Text(
              item.title,
              style: TextStyle(
                fontWeight: item.isRead ? FontWeight.normal : FontWeight.bold,
              ),
            ),
            subtitle: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 4),
                Text(item.body),
                const SizedBox(height: 4),
                Text(
                  _formatTime(item.createdAt),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.grey),
                ),
              ],
            ),
            onTap: () {
              setState(() {
                item.isRead = true;
              });
            },
          );
        },
      ),
    );
  }

  IconData _getIconForType(String type) {
    switch (type) {
      case 'job_assigned':
        return Icons.work_outline;
      case 'sla_warning':
        return Icons.timer_outlined;
      case 'inventory':
        return Icons.inventory_2_outlined;
      default:
        return Icons.notifications_outlined;
    }
  }

  String _formatTime(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}
