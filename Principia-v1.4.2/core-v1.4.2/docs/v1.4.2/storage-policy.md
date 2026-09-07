# Local storage and clean releases

Principia stores imported source references and derived evidence in a workspace;
it does not need a new copy of the scientific Python environment for each release.
Raw source corpora remain outside version folders and read-only. Bundled public
Global/Meta-Principles are product knowledge and remain available in an empty release.

## New versions

Build the frontend, then run from the core tree:

```sh
python ../scripts/build_clean_release.py /path/to/old-version /path/to/empty-new-version
```

The builder uses a product allowlist, prunes runtime/evaluation/dependency/cache
trees and credentials without reading them, refuses symlink traversal and a
nonempty destination, and enforces a 192 MiB source payload ceiling. A per-file
SHA-256 manifest is written to CLEAN_RELEASE.json. Do not increase the ceiling
without investigating the added files. Do not create releases with a recursive
copy of the development folder.

Start the new version with `python3 scripts/start_local.py --port 8142`. The launcher
requires Python 3.11+ (or Python 3.10 with tomli), selects that version's source
explicitly, and uses its own `runtime/user-workspace`. Dependencies can live in a
shared runtime keyed by the dependency contract and machine architecture, under
the user's application-support directory. A local core `.venv` is also supported.
Built UI assets are included; Node dependencies are needed only for development.
Keep shared Node packages inside a directory actually named `node_modules` (for
example, `runtimes/node-<contract>/node_modules`), then link the frontend to that
directory. Node and TypeScript rely on that directory name when resolving peers.
When sharing an editable Python environment, run backend checks from the core
with `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python` so imports select
the intended release. The launcher already sets both variables.
API credentials and previous projects are not copied. Configure API & models in
the new interface, or explicitly pass `--credential-env` to the launcher.

## Database growth and deletion

New databases enable SQLite incremental auto-vacuum. Permanent project deletion
removes its scientific records and derived artifact folders, then reclaims up to
4096 free pages. Concurrent maintenance failure does not invalidate a committed
delete. Larger free regions remain reusable for new records and can be compacted
explicitly. Raw source files are never removed by project deletion.

Existing databases are not rebuilt by startup or GET requests. Inspect one with:

```sh
python -m principia storage inspect --working-directory /path/to/user-workspace
```

To reclaim all free space and enable incremental reclamation in a legacy database,
stop its server and finish/cancel outstanding work, then run:

```sh
python -m principia storage compact --working-directory /path/to/user-workspace
```

Compaction preserves records, rejects live runtime leases and active jobs, and
checks SQLite integrity. It needs temporary free disk space. Normal growth from
new scientific work is expected; compression must not discard negative evidence,
counterexamples, locked-test receipts, or user projects.

## Test workspaces and history

Use one disposable workspace per campaign. Do not fork the full runtime for every
small UI check. At the end of a campaign retain its report and compress the stopped
test workspace before starting another copy. The helper only accepts a selected
subdirectory of runtime; frozen evaluation directories are never accepted:

```sh
python scripts/archive_runtime.py /path/to/version/runtime/finished-test \
  /path/to/version/runtime/archives/finished-test.tar.gz --remove-verified
```

The helper refuses credential files and live server leases, never follows source
symlinks, verifies every archived file's size and SHA-256, and checks that the input
did not change before removing the expanded copy. A verification failure preserves
the original. Without `--remove-verified`, it retains the expanded copy as well.
The archive and adjacent manifest preserve the complete selected history; extract
only into a new, empty directory when needed. Do not overwrite a live workspace.
If a legacy test workspace has a credential subtree, `--preserve-credentials`
leaves that subtree in its original location without reading or archiving it;
only verified noncredential entries are removed.

Count source folders, runtime evidence, compressed history, and shared dependencies
separately in storage reports. Moving dependencies into shared storage avoids
future duplication but is not itself disk-space reclamation. APFS clone files may
share physical extents even when folder-size tools count both copies.
