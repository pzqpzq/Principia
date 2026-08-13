# v1.3 migration and recovery

Principia retains `.principia/principia.sqlite` as the authoritative physical database. On the first v1.4 open it acquires an exclusive migration lock, checkpoints WAL, creates and verifies a timestamped SQLite backup, and runs additive versioned migrations in one transaction.

Legacy tables, IDs, and raw payloads remain intact. Every legacy Idea becomes one unassessed Local Candidate with an append-only import event and SHA-256 input/output digests. It is never promoted directly to a Capsule.

If migration fails, the transaction rolls back and the verified backup remains beside the database. Stop Principia, preserve the failed database and receipts, and restore the latest verified `principia.sqlite.v1.4-backup-*` with SQLite backup tooling. Do not maintain a second writable workspace database.

A clean second reopen performs no migration DML. `principia doctor --json` reports the migration receipt without exposing absolute paths.
