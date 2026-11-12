import 'package:flutter/material.dart';

class ConflictResolutionDialog extends StatelessWidget {
  final String title;
  final String entityName;
  final String localValue;
  final String serverValue;
  final VoidCallback onKeepLocal;
  final VoidCallback onAcceptServer;

  const ConflictResolutionDialog({
    super.key,
    required this.title,
    required this.entityName,
    required this.localValue,
    required this.serverValue,
    required this.onKeepLocal,
    required this.onAcceptServer,
  });

  static Future<bool?> show(
    BuildContext context, {
    required String title,
    required String entityName,
    required String localValue,
    required String serverValue,
  }) {
    return showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => ConflictResolutionDialog(
        title: title,
        entityName: entityName,
        localValue: localValue,
        serverValue: serverValue,
        onKeepLocal: () => Navigator.of(ctx).pop(true),
        onAcceptServer: () => Navigator.of(ctx).pop(false),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(
        children: [
          Icon(Icons.warning_amber_rounded, color: Colors.orange.shade800),
          const SizedBox(width: 8),
          Expanded(child: Text(title)),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'A conflict occurred while syncing updates for $entityName. The server has a newer or conflicting version.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            _buildSection(
              context,
              title: 'Your Local Change (Queued offline)',
              content: localValue,
              color: Colors.amber.shade50,
              borderColor: Colors.amber.shade400,
            ),
            const SizedBox(height: 12),
            _buildSection(
              context,
              title: 'Server Version',
              content: serverValue,
              color: Colors.blue.shade50,
              borderColor: Colors.blue.shade300,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: onAcceptServer,
          child: const Text('Accept Server'),
        ),
        ElevatedButton(
          onPressed: onKeepLocal,
          child: const Text('Keep My Changes (Overwrite)'),
        ),
      ],
    );
  }

  Widget _buildSection(
    BuildContext context, {
    required String title,
    required String content,
    required Color color,
    required Color borderColor,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
          ),
          const SizedBox(height: 4),
          Text(content, style: const TextStyle(fontSize: 14)),
        ],
      ),
    );
  }
}
