import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/models.dart';
import '../core/providers.dart';
import 'widgets.dart';

/// Consume stock on an in-progress job. Online only: stock is shared and must never be
/// decremented locally. The command id is fixed per attempt so a retry after a timeout
/// cannot take stock twice.
class MaterialsScreen extends ConsumerStatefulWidget {
  const MaterialsScreen({super.key, required this.job});

  final Job job;

  @override
  ConsumerState<MaterialsScreen> createState() => _MaterialsScreenState();
}

class _MaterialsScreenState extends ConsumerState<MaterialsScreen> {
  List<InventoryItem>? _items;
  ApiException? _loadError;
  InventoryItem? _selected;
  final _qty = TextEditingController(text: '1');
  String _commandId = newCommandId('mat');
  bool _busy = false;
  String? _message;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  @override
  void dispose() {
    _qty.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final items = await ref.read(apiProvider).inventory();
      if (mounted) setState(() => _items = items);
    } on ApiException catch (e) {
      if (mounted) setState(() => _loadError = e);
    }
  }

  Future<void> _use() async {
    final item = _selected;
    final quantity = int.tryParse(_qty.text.trim());
    if (item == null) return setState(() => _message = 'Choose an item.');
    if (quantity == null || quantity < 1) {
      return setState(() => _message = 'Enter a whole quantity of 1 or more.');
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await ref.read(apiProvider).consumeMaterial(
            requestId: widget.job.id,
            itemId: item.id,
            quantity: quantity,
            commandId: _commandId,
          );
      _commandId = newCommandId('mat'); // the next use is a new command
      await _load();
      setState(
          () => _message = 'Recorded $quantity ${item.unit} of ${item.name}.');
    } on ApiException catch (e) {
      // Same command id is kept on network errors so tapping again is safe.
      setState(() => _message = e.isNetwork
          ? 'No connection. Nothing was recorded — tap again to retry.'
          : e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return Scaffold(
      appBar: AppBar(title: Text('Materials · ${widget.job.reference}')),
      body: _loadError != null
          ? StateMessage.forError(_loadError!, onRetry: _load)
          : items == null
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    DropdownButtonFormField<InventoryItem>(
                      initialValue: _selected,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'Item'),
                      items: [
                        for (final i in items)
                          DropdownMenuItem(
                              value: i,
                              child: Text(
                                  '${i.code} — ${i.name} (${i.stock} ${i.unit})',
                                  overflow: TextOverflow.ellipsis)),
                      ],
                      onChanged: (v) => setState(() => _selected = v),
                    ),
                    TextField(
                      controller: _qty,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: 'Quantity'),
                    ),
                    if (_message != null)
                      Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Text(_message!)),
                    const SizedBox(height: 16),
                    FilledButton(
                        onPressed: _busy ? null : _use,
                        child: const Text('Use materials')),
                  ],
                ),
    );
  }
}
