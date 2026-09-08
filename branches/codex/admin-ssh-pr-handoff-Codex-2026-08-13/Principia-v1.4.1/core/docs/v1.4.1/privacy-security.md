# Privacy and security

- Ordinary research never uploads local content to Global Cloud.
- Canonical validators reject PDF/full-text fields, quotations, credentials,
  private or non-HTTPS URLs, and absolute local paths.
- Admin download reuses HTTPS, DNS/redirect, MIME, size, encryption, and
  extractability defenses. Abstracts are metadata and never substitute for full
  text during extraction.
- GitHub publication credentials live in the macOS Keychain service
  `Principia Global Cloud GitHub`; tokens never enter SQLite, frontend state,
  logs, SSE payloads, changesets, or release assets.
- Admin endpoints retain the existing loopback Host/origin/session controls.
- Temporary deletion resolves and verifies the exact allowlisted job directory;
  no broad recursive deletion target is accepted.
