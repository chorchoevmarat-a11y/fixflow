import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api_client.dart';
import '../../shared/widgets/loading_states.dart';

class MaterialItem {
  final String id;
  final String sku;
  final String name;
  final int availableStock;
  final String unit;

  MaterialItem({
    required this.id,
    required this.sku,
    required this.name,
    required this.availableStock,
    required this.unit,
  });

  factory MaterialItem.fromJson(Map<String, dynamic> json) {
    return MaterialItem(
      id: json['id'] as String,
      sku: json['sku'] as String? ?? '',
      name: json['name'] as String? ?? 'Unnamed item',
      availableStock: (json['available_stock'] as num?)?.toInt() ?? 0,
      unit: json['unit'] as String? ?? 'pcs',
    );
  }
}

class MaterialUsageScreen extends ConsumerStatefulWidget {
  final String jobId;

  const MaterialUsageScreen({super.key, required this.jobId});

  @override
  ConsumerState<MaterialUsageScreen> createState() => _MaterialUsageScreenState();
}

class _MaterialUsageScreenState extends ConsumerState<MaterialUsageScreen> {
  bool _isLoading = true;
  bool _isOffline = false;
  String? _error;
  List<MaterialItem> _catalog = [];
  MaterialItem? _selectedItem;
  final _quantityController = TextEditingController(text: '1');
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _checkAndLoad();
  }

  @override
  void dispose() {
    _quantityController.dispose();
    super.dispose();
  }

  Future<void> _checkAndLoad() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final connectivity = await Connectivity().checkConnectivity();
    if (connectivity.contains(ConnectivityResult.none)) {
      setState(() {
        _isOffline = true;
        _isLoading = false;
      });
      return;
    }

    try {
      final client = ref.read(apiClientProvider);
      final res = await client.get<List<dynamic>>('/inventory/items');
      final items = (res.data ?? [])
          .map((i) => MaterialItem.fromJson(i as Map<String, dynamic>))
          .toList();

      setState(() {
        _catalog = items;
        _isLoading = false;
        _isOffline = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _submitUsage() async {
    if (_selectedItem == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select a material')),
      );
      return;
    }

    final qty = int.tryParse(_quantityController.text);
    if (qty == null || qty <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter a valid positive quantity')),
      );
      return;
    }

    if (qty > _selectedItem!.availableStock) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Quantity exceeds available stock (${_selectedItem!.availableStock})')),
      );
      return;
    }

    setState(() => _isSubmitting = true);
    final client = ref.read(apiClientProvider);

    try {
      await client.post(
        '/jobs/${widget.jobId}/materials',
        data: {
          'material_id': _selectedItem!.id,
          'quantity': qty,
        },
      );

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Material usage logged successfully')),
        );
        context.pop();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to log material: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Log Material Usage'),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isOffline) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.cloud_off, size: 56, color: Colors.orange.shade700),
              const SizedBox(height: 16),
              Text(
                'Online Connection Required',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text(
                'Material inventory tracking requires an active network connection to prevent real-time stock allocation conflicts.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: _checkAndLoad,
                icon: const Icon(Icons.refresh),
                label: const Text('Check Connection'),
              ),
            ],
          ),
        ),
      );
    }

    if (_isLoading) {
      return const LoadingView(message: 'Loading inventory catalog...');
    }

    if (_error != null) {
      return ErrorView(
        message: _error!,
        onRetry: _checkAndLoad,
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Select Material & Part',
            style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<MaterialItem>(
            value: _selectedItem,
            isExpanded: true,
            hint: const Text('Select an item from inventory'),
            items: _catalog.map((item) {
              return DropdownMenuItem<MaterialItem>(
                value: item,
                child: Text('${item.name} (${item.availableStock} ${item.unit} available)'),
              );
            }).toList(),
            onChanged: (val) {
              setState(() {
                _selectedItem = val;
              });
            },
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _quantityController,
            keyboardType: TextInputType.number,
            decoration: InputDecoration(
              labelText: 'Quantity Used',
              suffixText: _selectedItem?.unit ?? 'units',
            ),
          ),
          const SizedBox(height: 32),
          ElevatedButton(
            onPressed: _isSubmitting ? null : _submitUsage,
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16),
            ),
            child: _isSubmitting
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : const Text('Confirm Usage & Deduct Stock'),
          ),
        ],
      ),
    );
  }
}
