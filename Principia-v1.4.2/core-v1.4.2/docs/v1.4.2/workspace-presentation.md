# Workspace presentation and user edits

The data-project workspace opens on Map. Results is the other top-level surface;
the old Graph URL is accepted as an alias for Map. The four record categories
remain available in the Study map and in Results. A Principle opens its detail
dialog without changing the surface. Selection can be restored from the URL.

## Canonical records and graph overlays

`GET /api/v1/research-sessions/{session_id}/workspace?run_id=...` is the common
projection for records, counts, graph membership, edges, and inspectors.
`GET /api/v1/research-sessions/{session_id}/graph?run_id=...` returns that same
graph. Both resolve session aliases and the selected run. Reading either endpoint
does not seed graph rows, migrate historical results, or update finding timestamps.

The selected run supplies immutable scientific records. Explicit graph edits
form an overlay with saved positions and visibility, plus context added by the
user. Generated membership from other runs is excluded. A removed scientific
record remains available in Results, while its graph visibility is stored as a
tombstone. Removing manually added context removes that context from the workspace
projection. Adding it again restores visibility and updates its saved payload.
Blank data projects can also hold manually added context before their first run.

Added context carries `origin: user_added` on the canonical record and
`workspace_origin: user_added` in its display payload. The graph retains its
original origin, including `virtual_principle`, for graph controls and styling.
Context does not count as a scientific finding or Rule, and no explanatory edge
is invented merely because the user added a node.

Graph writes use an immediate SQLite transaction around the expected-revision
check and the whole operation batch. A failed batch rolls back. Moves and removals
also work for canonical nodes that do not already have a saved graph row.
Coordinates must be finite. The browser serializes saves and queued replays;
a revision conflict refreshes the current revision and retries once. Only
recoverable failures enter the local retry queue, and the interface claims a
queued save only after IndexedDB confirms it was stored.

## Scientific labels and receipts

Generic short-horizon Rule titles are presented using the persisted executable
AST: response structure, observed history, and (when necessary) recording scope.
Normalization-scale powers are excluded from structural classification. Source
captions use explicit recording entities such as BIDS sessions or TESS targets.
`recorded_title`, `source_context`, and `source_paths` preserve the original title
and traceability. Scientific identities, equations, fitted values, and gates are
unchanged. Labels do not affect Rule selection or promotion.

Finding and Rule panels share structured receipt rendering. Scalars, vectors,
nested fields, and object tables retain their exact values. Long provenance lists
are collapsed, searchable, and progressively revealed. Computed estimates appear
before file-level provenance. Technical identifiers and diagnostics remain
available under disclosures. Preview clipping is applied after math rendering
so it cannot cut a LaTeX delimiter; executable symbol subscripts retain their
complete indices.

Record cards fill their containing column. Evidence panels are excluded from
the unrelated two-column search-result modal style. The Map sizes nodes for the
visible canvas and record count, uses a distinct color for evaluated Rules, and
provides zoom and fit controls. At narrow widths, the canvas and Study map list
stack vertically; hiding the list expands the canvas.

## Regression coverage

`tests/test_v142_workspace_edits.py` exercises overlay composition, selected-run
isolation, empty projects, atomic revisions, rollback, read-only timestamps,
removal of unsaved canonical nodes, and presentation-only Rule naming.
Frontend tests cover receipt structure, save conflicts and queue failures,
canonical edge endpoints, and scientific text rendering.
