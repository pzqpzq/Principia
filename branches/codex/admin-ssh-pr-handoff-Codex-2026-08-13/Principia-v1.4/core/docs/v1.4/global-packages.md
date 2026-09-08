# Downloadable Principle packages

“Global” describes a distribution channel. At runtime, every package is local data:
an immutable, verified, paper-free archive in the application-level
`principle-packages/` library. That library is shared across working directories;
private Principles, credentials, jobs, and raw papers remain isolated in the selected
working directory. It is not a separate remote database.

An adjacent `principle-packages/catalog.json` is discovered automatically in a source
checkout. Installed distributions can select it explicitly:

```bash
principia open \
  --working-directory /path/to/my-project \
  --package-library /path/to/principle-packages
```

Already-downloaded `.pcp` entries are verified and activated on startup. A later Cloud
install first writes beneath the same package library, then verifies and indexes the
archive. Switching working directories preserves this shared library and never copies
a package into private workspace state.

Packages declare one of two content classes:

- `reviewed_capsules`: human-reviewed Principle Capsules;
- `unassessed_candidates`: evidence-checked Candidate Principles whose human review
  is still pending.

Installation or cryptographic verification never upgrades scientific review status.

A v1.4 `.pcp` contains exactly `manifest.json`, `area.sqlite`, and `README.txt`. The database preserves immutable Principle revisions under `(principle_id, version)` and derives its current projection without deleting history.

Installation downloads to a `.partial`, enforces archive limits, verifies the catalog artifact SHA-256, rejects traversal/symlinks/unexpected entries, validates the manifest and framework range, verifies the internal database SHA-256, runs SQLite foreign-key and integrity checks, registers the package transactionally, and only then atomically updates the JSON active-version pointer.

Three hashes have distinct roles:

- `content_digest` covers canonical logical records across platforms.
- `area_sqlite_sha256` covers the exact internal database bytes.
- `artifact_sha256` covers the released archive and lives in the catalog/build receipt.

Commands:

```bash
principia cloud --working-directory ./my-project --package-library ./principle-packages install AREA --catalog ./catalog.json
principia cloud --working-directory ./my-project --package-library ./principle-packages list
principia cloud --working-directory ./my-project --package-library ./principle-packages verify AREA
principia cloud --working-directory ./my-project --package-library ./principle-packages pin AREA VERSION
principia cloud --working-directory ./my-project --package-library ./principle-packages update AREA --catalog ./catalog.json
principia cloud --working-directory ./my-project --package-library ./principle-packages rollback AREA
```

Pinning blocks activation of a different version. Failed updates leave the prior version active. Deleting `registry.sqlite` is recoverable through registry rebuild from immutable packages and active JSON pointers.
