import 'dart:io';
import 'package:drift/drift.dart' as drift;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:uuid/uuid.dart';
import '../../core/api_client.dart';
import '../../core/database.dart';
import '../sync/offline_queue_manager.dart';

class NoteComposeScreen extends ConsumerStatefulWidget {
  final String jobId;

  const NoteComposeScreen({super.key, required this.jobId});

  @override
  ConsumerState<NoteComposeScreen> createState() => _NoteComposeScreenState();
}

class _NoteComposeScreenState extends ConsumerState<NoteComposeScreen> {
  final _textController = TextEditingController();
  final ImagePicker _picker = ImagePicker();
  final List<XFile> _selectedImages = [];
  bool _isPrivate = false;
  bool _isSaving = false;

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  Future<void> _pickImage(ImageSource source) async {
    try {
      final photo = await _picker.pickImage(
        source: source,
        imageQuality: 80,
        maxWidth: 1920,
      );
      if (photo != null) {
        setState(() {
          _selectedImages.add(photo);
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to pick photo: $e')),
        );
      }
    }
  }

  Future<void> _saveNote() async {
    final content = _textController.text.trim();
    if (content.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter note content')),
      );
      return;
    }

    setState(() => _isSaving = true);
    final noteId = const Uuid().v4();
    final db = ref.read(databaseProvider);
    final queue = ref.read(offlineQueueManagerProvider);
    final client = ref.read(apiClientProvider);

    try {
      // 1. Save note to local database
      await db.saveLocalNote(
        LocalNotesCompanion.insert(
          id: noteId,
          jobId: widget.jobId,
          content: content,
          isPrivate: drift.Value(_isPrivate ? 1 : 0),
          createdAt: drift.Value(DateTime.now()),
          synced: const drift.Value(0),
        ),
      );

      // Save local evidence records for images
      for (final img in _selectedImages) {
        final evidenceId = const Uuid().v4();
        await db.saveEvidenceFile(
          LocalEvidenceFilesCompanion.insert(
            id: evidenceId,
            jobId: widget.jobId,
            noteId: drift.Value(noteId),
            localPath: img.path,
            mimeType: 'image/jpeg',
            createdAt: drift.Value(DateTime.now()),
            synced: const drift.Value(0),
          ),
        );
      }

      // 2. Try online sync or enqueue
      try {
        await client.post(
          '/jobs/${widget.jobId}/notes',
          data: {
            'content': content,
            'is_private': _isPrivate,
            'local_id': noteId,
          },
        );
        await db.markNoteSynced(noteId, noteId);
      } catch (_) {
        // Enqueue command for offline replay
        await queue.enqueueCommand(
          commandId: noteId,
          commandType: 'add_note',
          jobId: widget.jobId,
          payload: {
            'content': content,
            'is_private': _isPrivate,
            'local_id': noteId,
          },
        );
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Note recorded successfully')),
        );
        context.pop();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to save note: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSaving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Add Field Note'),
        actions: [
          TextButton(
            onPressed: _isSaving ? null : _saveNote,
            child: _isSaving
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Save', style: TextStyle(fontWeight: FontWeight.bold)),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _textController,
              maxLines: 6,
              decoration: const InputDecoration(
                hintText: 'Enter field observations, customer remarks, or repair steps...',
                labelText: 'Note Content',
                alignLabelWithHint: true,
              ),
            ),
            const SizedBox(height: 16),
            SwitchListTile(
              title: const Text('Internal Note Only'),
              subtitle: const Text('Customer will not see this remark'),
              value: _isPrivate,
              onChanged: (val) => setState(() => _isPrivate = val),
              contentPadding: EdgeInsets.zero,
            ),
            const SizedBox(height: 16),
            Text(
              'Attach Photo Evidence',
              style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                OutlinedButton.icon(
                  onPressed: () => _pickImage(ImageSource.camera),
                  icon: const Icon(Icons.camera_alt),
                  label: const Text('Camera'),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: () => _pickImage(ImageSource.gallery),
                  icon: const Icon(Icons.photo_library),
                  label: const Text('Gallery'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            if (_selectedImages.isNotEmpty)
              SizedBox(
                height: 100,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: _selectedImages.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 8),
                  itemBuilder: (context, index) {
                    final img = _selectedImages[index];
                    return Stack(
                      children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: Image.file(
                            File(img.path),
                            width: 100,
                            height: 100,
                            fit: BoxFit.cover,
                          ),
                        ),
                        Positioned(
                          top: 2,
                          right: 2,
                          child: GestureDetector(
                            onTap: () {
                              setState(() {
                                _selectedImages.removeAt(index);
                              });
                            },
                            child: Container(
                              decoration: const BoxDecoration(
                                shape: BoxShape.circle,
                                color: Colors.black54,
                              ),
                              child: const Icon(Icons.close, size: 18, color: Colors.white),
                            ),
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}
