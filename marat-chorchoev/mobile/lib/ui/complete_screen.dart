import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../core/models.dart';
import '../core/providers.dart';

/// Completion is an online-only action: photo upload and the final transition both
/// need the server, and neither is simulated locally.
class CompleteScreen extends ConsumerStatefulWidget {
  const CompleteScreen({super.key, required this.job});

  final Job job;

  @override
  ConsumerState<CompleteScreen> createState() => _CompleteScreenState();
}

class _CompleteScreenState extends ConsumerState<CompleteScreen> {
  final _note = TextEditingController();
  final _uploaded = <String>[];
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _photo(ImageSource source) async {
    final picked = await ImagePicker()
        .pickImage(source: source, maxWidth: 2048, imageQuality: 85);
    if (picked == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(apiProvider).uploadImage(
            requestId: widget.job.id,
            kind: 'COMPLETION',
            path: picked.path,
            commandId: newCommandId('done'),
            assignmentId: widget.job.assignmentId,
          );
      setState(() => _uploaded.add(picked.name));
    } on ApiException catch (e) {
      setState(() => _error = e.isNetwork
          ? 'No connection — the photo was not uploaded.'
          : e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _complete() async {
    final note = _note.text.trim();
    if (note.length < 20) {
      return setState(
          () => _error = 'The completion note must be at least 20 characters.');
    }
    if (_uploaded.isEmpty) {
      return setState(() => _error = 'Add at least one completion photo.');
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(apiProvider).transition(widget.job.id, 'complete',
          body: {'completion_note': note});
      try {
        final fresh = await ref.read(apiProvider).jobDetail(widget.job.id);
        await ref.read(jobsProvider.notifier).replace(fresh);
      } on ApiException {
        // Completion itself succeeded; only the local refresh failed. Do not claim otherwise.
      }
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Job completed')));
        Navigator.of(context).pop();
      }
    } on ApiException catch (e) {
      setState(() => _error = e.isNetwork
          ? 'No connection — the job was not completed.'
          : e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final online = ref.watch(onlineProvider);
    return Scaffold(
      appBar: AppBar(title: Text('Complete · ${widget.job.reference}')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (!online) const Text('Offline: completing needs a connection.'),
          TextField(
            controller: _note,
            maxLines: 5,
            decoration: const InputDecoration(
                labelText: 'Completion note (20+ characters)'),
          ),
          const SizedBox(height: 12),
          Wrap(spacing: 8, children: [
            OutlinedButton.icon(
              onPressed:
                  online && !_busy ? () => _photo(ImageSource.camera) : null,
              icon: const Icon(Icons.photo_camera),
              label: const Text('Take photo'),
            ),
            OutlinedButton.icon(
              onPressed:
                  online && !_busy ? () => _photo(ImageSource.gallery) : null,
              icon: const Icon(Icons.photo_library_outlined),
              label: const Text('Choose photo'),
            ),
          ]),
          for (final name in _uploaded)
            ListTile(
                dense: true,
                leading: const Icon(Icons.check_circle_outline),
                title: Text('Uploaded $name')),
          if (_error != null)
            Text(_error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          const SizedBox(height: 16),
          FilledButton(
              onPressed: online && !_busy ? _complete : null,
              child: const Text('Complete job')),
        ],
      ),
    );
  }
}
