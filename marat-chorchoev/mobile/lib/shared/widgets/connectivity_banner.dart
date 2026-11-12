import 'package:flutter/material.dart';

class ConnectivityBanner extends StatelessWidget {
  final bool isOffline;
  final int pendingSyncCount;
  final VoidCallback? onSyncNow;

  const ConnectivityBanner({
    super.key,
    required this.isOffline,
    this.pendingSyncCount = 0,
    this.onSyncNow,
  });

  @override
  Widget build(BuildContext context) {
    if (!isOffline && pendingSyncCount == 0) {
      return const SizedBox.shrink();
    }

    final theme = Theme.of(context);
    final color = isOffline ? Colors.orange.shade800 : Colors.blue.shade700;
    final bgColor = isOffline ? Colors.orange.shade50 : Colors.blue.shade50;

    return Container(
      width: double.infinity,
      color: bgColor,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          Icon(
            isOffline ? Icons.wifi_off : Icons.sync,
            size: 18,
            color: color,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              isOffline
                  ? (pendingSyncCount > 0
                      ? 'Offline Mode • $pendingSyncCount change${pendingSyncCount == 1 ? '' : 's'} queued'
                      : 'Offline Mode • Changes will sync later')
                  : '$pendingSyncCount change${pendingSyncCount == 1 ? '' : 's'} waiting to sync',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: color,
              ),
            ),
          ),
          if (!isOffline && pendingSyncCount > 0 && onSyncNow != null)
            TextButton(
              onPressed: onSyncNow,
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: Text(
                'Sync Now',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
