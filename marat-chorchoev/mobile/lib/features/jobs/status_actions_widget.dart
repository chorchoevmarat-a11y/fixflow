import 'package:flutter/material.dart';

class StatusActionsWidget extends StatelessWidget {
  final String currentStatus;
  final Function(String newStatus) onTransition;
  final VoidCallback onAddNote;
  final VoidCallback onLogMaterials;

  const StatusActionsWidget({
    super.key,
    required this.currentStatus,
    required this.onTransition,
    required this.onAddNote,
    required this.onLogMaterials,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Workflow Actions',
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: Theme.of(context).colorScheme.primary,
                  ),
            ),
            const SizedBox(height: 12),
            _buildActionButtons(context),
            const SizedBox(height: 12),
            const Divider(),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: onAddNote,
                    icon: const Icon(Icons.note_add_outlined, size: 18),
                    label: const Text('Add Note'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: onLogMaterials,
                    icon: const Icon(Icons.inventory_2_outlined, size: 18),
                    label: const Text('Materials'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActionButtons(BuildContext context) {
    switch (currentStatus.toLowerCase()) {
      case 'assigned':
      case 'pending':
        return Row(
          children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: () => onTransition('en_route'),
                icon: const Icon(Icons.directions_car),
                label: const Text('Start Travel (En Route)'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.blue.shade700,
                  foregroundColor: Colors.white,
                ),
              ),
            ),
          ],
        );

      case 'en_route':
        return Row(
          children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: () => onTransition('in_progress'),
                icon: const Icon(Icons.play_arrow),
                label: const Text('Arrived & Start Work'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.green.shade700,
                  foregroundColor: Colors.white,
                ),
              ),
            ),
          ],
        );

      case 'in_progress':
        return Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => onTransition('on_hold'),
                icon: const Icon(Icons.pause),
                label: const Text('Put on Hold'),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: ElevatedButton.icon(
                onPressed: () => onTransition('completed'),
                icon: const Icon(Icons.check_circle),
                label: const Text('Complete Job'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.teal.shade700,
                  foregroundColor: Colors.white,
                ),
              ),
            ),
          ],
        );

      case 'on_hold':
        return Row(
          children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: () => onTransition('in_progress'),
                icon: const Icon(Icons.play_arrow),
                label: const Text('Resume Work'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.blue.shade700,
                  foregroundColor: Colors.white,
                ),
              ),
            ),
          ],
        );

      case 'completed':
        return Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.green.shade50,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.green.shade200),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.check_circle, color: Colors.green.shade700),
              const SizedBox(width: 8),
              Text(
                'Job is marked as Completed',
                style: TextStyle(
                  color: Colors.green.shade800,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        );

      default:
        return Text('Status: $currentStatus');
    }
  }
}
