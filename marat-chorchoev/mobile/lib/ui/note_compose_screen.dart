import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../core/models.dart';
import '../core/providers.dart';

/// Writes a note and (optionally) photos. Works offline: the note goes into the queue
/// with a stable command id and is delivered whenever a connection is available.
class NoteComposeScreen extends ConsumerStatefulWidget {
  const NoteComposeScreen({super.key, required this.job});

  final Job job;

  @override
  ConsumerState<NoteComposeScreen> createState() => _NoteComposeScreenState();
}

class _NoteComposeScreenState extends ConsumerState<NoteComposeScreen> {
  final _body = TextEditingController();
  final _photos = <String>[];
  bool _internal = false;
  bool _saving = false;
  String? _error;
  // Created once per draft: the same id is reused if the person taps Save twice.
  final String _commandId = newCommandId('note');

  @override
  void dispose() {
    _body.dispose();
    super.dispose();
  }

  Future<void> _pick(ImageSource source) async {
    try {
      final picked = await ImagePicker()
          .pickImage(source: source, maxWidth: 2048, imageQuality: 85);
      if (picked != null) setState(() => _photos.add(picked.path));
    } catch (_) {
      setState(() => _error =
          'Could not open the camera or gallery. Check the app permission in Android settings.');
    }
  }

  Future<void> _save() async {
    if (_saving) return;
    final text = _body.text.trim();
    if (text.isEmpty) {
      setState(() => _error = 'Write a note first.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    await ref.read(queueProvider.notifier).enqueue(
          job: widget.job,
          body: text,
          internal: _internal,
          photoPaths: _photos,
          commandId: _commandId,
        );
    if (!mounted) return;
    final online = ref.read(onlineProvider);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text(online
              ? 'Note saved — sending…'
              : 'Saved on this phone. Pending sync until you are online.')),
    );
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Note · ${widget.job.reference}')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _body,
            maxLines: 6,
            maxLength: 4000,
            decoration: InputDecoration(labelText: 'Note', errorText: _error),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Internal (hidden from the requester)'),
            value: _internal,
            onChanged: (v) => setState(() => _internal = v),
          ),
          const SizedBox(height: 8),
          Wrap(spacing: 8, children: [
            OutlinedButton.icon(
                onPressed: () => _pick(ImageSource.camera),
                icon: const Icon(Icons.photo_camera),
                label: const Text('Take photo')),
            OutlinedButton.icon(
                onPressed: () => _pick(ImageSource.gallery),
                icon: const Icon(Icons.photo_library_outlined),
                label: const Text('Choose photo')),
          ]),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final path in _photos)
              Chip(
                label: Text(path.split(RegExp(r'[\\/]')).last,
                    overflow: TextOverflow.ellipsis),
                onDeleted: () => setState(() => _photos.remove(path)),
              ),
          ]),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Save note'),
          ),
        ],
      ),
    );
  }
}
