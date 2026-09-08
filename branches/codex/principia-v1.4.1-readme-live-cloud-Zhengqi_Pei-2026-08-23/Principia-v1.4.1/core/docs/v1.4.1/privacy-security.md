# Privacy and security

- Ordinary research never uploads local content to Global Cloud.
- Canonical validators reject PDF/full-text fields, quotations, credentials,
  private or non-HTTPS URLs, and absolute local paths.
- The public core contains only neutral Cloud contracts, validation, snapshot,
  search, and graph code. Privileged Admin routes, UI, extraction, publication,
  tests, prompts, and credentials live only in the sibling local package.
- Admin publication changesets are path-allowlisted to `global-cloud/**` and are
  rebuilt by CI from canonical records; client-generated indexes are never
  accepted as authoritative.
