import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/models.dart';
import '../core/providers.dart';
import 'widgets.dart';

const _days = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday'
];

/// Read-only view of the technician's weekly hours, time off, and upcoming appointments.
class AvailabilityScreen extends ConsumerStatefulWidget {
  const AvailabilityScreen({super.key});

  @override
  ConsumerState<AvailabilityScreen> createState() => _AvailabilityScreenState();
}

class _AvailabilityScreenState extends ConsumerState<AvailabilityScreen> {
  TechnicianProfile? _profile;
  ApiException? _error;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  Future<void> _load() async {
    try {
      final profile = await ref.read(apiProvider).myProfile();
      if (mounted) setState(() => _profile = profile);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final jobs = [
      for (final j in ref.watch(jobsProvider).jobs)
        if (j.startAt != null && j.assignment?['is_active'] == true) j
    ]..sort((a, b) => a.startAt!.compareTo(b.startAt!));
    final profile = _profile;
    return Scaffold(
      appBar: AppBar(title: const Text('Availability')),
      body: Column(
        children: [
          const StatusBanner(),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text('Upcoming appointments',
                    style: Theme.of(context).textTheme.titleMedium),
                if (jobs.isEmpty)
                  const Padding(
                      padding: EdgeInsets.all(8),
                      child: Text('No scheduled appointments.')),
                for (final j in jobs)
                  ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(j.appointmentText),
                      subtitle: Text('${j.reference} · ${j.title}')),
                const Divider(),
                Text('Weekly hours',
                    style: Theme.of(context).textTheme.titleMedium),
                if (_error != null && profile == null)
                  StateMessage.forError(_error!, onRetry: _load),
                if (profile == null && _error == null)
                  const Padding(
                      padding: EdgeInsets.all(16),
                      child: Center(child: CircularProgressIndicator())),
                if (profile != null) ...[
                  for (final slot in profile.availability)
                    Text(
                        '${_days[slot.weekday]}: ${slot.startsAt}–${slot.endsAt}'),
                  if (profile.availability.isEmpty)
                    const Text('No weekly hours set. Ask an administrator.'),
                  const SizedBox(height: 12),
                  Text('Time off',
                      style: Theme.of(context).textTheme.titleMedium),
                  if (profile.timeOff.isEmpty) const Text('None scheduled.'),
                  for (final t in profile.timeOff) Text(t),
                  const SizedBox(height: 12),
                  Text('Skills',
                      style: Theme.of(context).textTheme.titleMedium),
                  Wrap(
                      spacing: 6,
                      children: [for (final s in profile.skills) Chip2(s)]),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
