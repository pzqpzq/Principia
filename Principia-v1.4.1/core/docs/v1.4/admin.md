# Admin review and dry-run publication

Launch the isolated runtime with:

```bash
principia admin --workspace ./admin-workspace
```

Harvest produces a Candidate, never a publishable Capsule. A human reviewer must approve, edit, merge, or reject it. Approval requires a reviewed grade, all five quality dimensions, falsifier, scope, at least one public source/proof reference, and complete generation trace.

Changesets pin their base content digest, base/proposed package versions, operations, approval requirement, validation results, trace, and human-readable goal. The default publication action is a dry run that returns a digest and size preview and optionally writes a local JSON export. It performs no external write.

Real GitHub publication is deliberately unconfigured for this release. Do not enable it during acceptance.
