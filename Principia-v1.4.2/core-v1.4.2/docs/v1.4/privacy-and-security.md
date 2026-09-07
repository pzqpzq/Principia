# Privacy and security

Principia binds only to `127.0.0.1`. It validates Host and Origin, uses a per-process mutation token, rejects ordinary JSON bodies larger than 1 MiB, and serves a restrictive Content Security Policy with local assets only.

Absolute private-source paths are stored only in the authoritative local SQLite database and are accepted only during the initial loopback registration request. Later API responses, job records, diagnostics, and exports use opaque `src:` IDs and portable `local-source://` URIs.

No-LLM jobs do not send content anywhere. Local-model jobs require a loopback host. Remote jobs send selected content only to the explicitly named provider after the user confirms egress for that job. Secrets are read from the process environment and are never placed in diagnostics, traces, package manifests, changesets, or release reports.

The public runtime contains no privileged cloud-mutation routes. Cloud publication tooling is distributed separately from the public package.
