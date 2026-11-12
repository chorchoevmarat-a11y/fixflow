import 'dart:io';
import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;

final databaseProvider = Provider<AppDatabase>((ref) => AppDatabase());

part 'database.g.dart';

// ─── Tables ──────────────────────────────────────────────────────────────────

class CachedJobs extends Table {
  TextColumn get id => text()();
  TextColumn get title => text()();
  TextColumn get description => text()();
  TextColumn get status => text()();
  TextColumn get priority => text()();
  TextColumn get customerId => text()();
  TextColumn get customerName => text()();
  TextColumn get locationAddress => text()();
  TextColumn get assignedTechnicianId => text()();
  DateTimeColumn get scheduledStart => dateTime().nullable()();
  DateTimeColumn get scheduledEnd => dateTime().nullable()();
  DateTimeColumn get slaDeadline => dateTime().nullable()();
  TextColumn get rawJson => text()(); // full JSON blob for extra fields
  DateTimeColumn get cachedAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {id};
}

class PendingCommands extends Table {
  IntColumn get localId => integer().autoIncrement()();
  TextColumn get commandId => text().unique()(); // idempotency key (UUID)
  TextColumn get commandType => text()(); // e.g. 'update_status', 'add_note'
  TextColumn get jobId => text()();
  TextColumn get payload => text()(); // JSON
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  IntColumn get retryCount => integer().withDefault(const Constant(0))();
  TextColumn get lastError => text().nullable()();
}

class LocalNotes extends Table {
  TextColumn get id => text()(); // local UUID
  TextColumn get jobId => text()();
  TextColumn get content => text()();
  IntColumn get isPrivate => integer().withDefault(const Constant(0))();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  IntColumn get synced => integer().withDefault(const Constant(0))();
  TextColumn get remoteId => text().nullable()(); // set after sync

  @override
  Set<Column> get primaryKey => {id};
}

class LocalEvidenceFiles extends Table {
  TextColumn get id => text()();
  TextColumn get jobId => text()();
  TextColumn get noteId => text().nullable()();
  TextColumn get localPath => text()();
  TextColumn get mimeType => text()();
  TextColumn get caption => text().nullable()();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  IntColumn get synced => integer().withDefault(const Constant(0))();
  TextColumn get remoteUrl => text().nullable()();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Database ────────────────────────────────────────────────────────────────

@DriftDatabase(
  tables: [CachedJobs, PendingCommands, LocalNotes, LocalEvidenceFiles],
)
class AppDatabase extends _$AppDatabase {
  AppDatabase() : super(_openConnection());

  @override
  int get schemaVersion => 1;

  // ── CachedJobs ──────────────────────────────────────────────────────────

  Future<void> upsertJob(CachedJobsCompanion entry) =>
      into(cachedJobs).insertOnConflictUpdate(entry);

  Future<List<CachedJob>> getAllJobs() => select(cachedJobs).get();

  Future<CachedJob?> getJobById(String id) =>
      (select(cachedJobs)..where((t) => t.id.equals(id))).getSingleOrNull();

  Future<int> clearJobs() => delete(cachedJobs).go();

  // ── PendingCommands ──────────────────────────────────────────────────────

  Future<int> enqueuePendingCommand(PendingCommandsCompanion entry) =>
      into(pendingCommands).insert(entry);

  Future<List<PendingCommand>> getAllPendingCommands() =>
      (select(pendingCommands)
            ..orderBy([(t) => OrderingTerm.asc(t.createdAt)]))
          .get();

  Future<int> deletePendingCommand(int localId) =>
      (delete(pendingCommands)..where((t) => t.localId.equals(localId))).go();

  Future<void> incrementRetry(int localId, String error) =>
      (update(pendingCommands)..where((t) => t.localId.equals(localId))).write(
        PendingCommandsCompanion(
          retryCount: const Value(1), // incremented in service layer
          lastError: Value(error),
        ),
      );

  // ── LocalNotes ───────────────────────────────────────────────────────────

  Future<void> saveLocalNote(LocalNotesCompanion entry) =>
      into(localNotes).insertOnConflictUpdate(entry);

  Future<List<LocalNote>> getNotesForJob(String jobId) =>
      (select(localNotes)..where((t) => t.jobId.equals(jobId))).get();

  Future<List<LocalNote>> getUnsyncedNotes() =>
      (select(localNotes)..where((t) => t.synced.equals(0))).get();

  Future<void> markNoteSynced(String id, String remoteId) =>
      (update(localNotes)..where((t) => t.id.equals(id))).write(
        LocalNotesCompanion(synced: const Value(1), remoteId: Value(remoteId)),
      );

  // ── LocalEvidenceFiles ───────────────────────────────────────────────────

  Future<void> saveEvidenceFile(LocalEvidenceFilesCompanion entry) =>
      into(localEvidenceFiles).insertOnConflictUpdate(entry);

  Future<List<LocalEvidenceFile>> getEvidenceForJob(String jobId) =>
      (select(localEvidenceFiles)..where((t) => t.jobId.equals(jobId))).get();

  Future<List<LocalEvidenceFile>> getUnsyncedEvidence() =>
      (select(localEvidenceFiles)..where((t) => t.synced.equals(0))).get();

  Future<void> markEvidenceSynced(String id, String remoteUrl) =>
      (update(localEvidenceFiles)..where((t) => t.id.equals(id))).write(
        LocalEvidenceFilesCompanion(
          synced: const Value(1),
          remoteUrl: Value(remoteUrl),
        ),
      );
}

LazyDatabase _openConnection() {
  return LazyDatabase(() async {
    final dbFolder = await getApplicationDocumentsDirectory();
    final file = File(p.join(dbFolder.path, 'fixflow.db'));
    return NativeDatabase.createInBackground(file);
  });
}
