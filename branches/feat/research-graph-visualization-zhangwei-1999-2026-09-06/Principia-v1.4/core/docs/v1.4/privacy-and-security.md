# Privacy and security

Principia binds only to `127.0.0.1`. It validates Host and Origin, uses a per-process mutation token, rejects ordinary JSON bodies larger than 1 MiB, and serves a restrictive Content Security Policy with local assets only.

Absolute private-source paths are stored only in the authoritative local SQLite database and are accepted only during the initial loopback registration request. Later API responses, job records, diagnostics, and exports use opaque `src:` IDs and portable `local-source://` URIs.

No-LLM jobs do not send content anywhere. Local-model jobs require a loopback host. Remote jobs send selected content only to the explicitly named provider after the user confirms egress for that job. Secrets are read from the process environment and are never placed in diagnostics, traces, package manifests, changesets, or release reports.

Ordinary `principia open` does not mount Admin API routes and returns 404 for `/admin`. `principia admin` launches a separate Admin-capable process. GitHub writes are disabled unless all explicit environment, authentication, validation, base-version, and typed-confirmation gates pass; the v1.4.0 fixture release does not configure a real publication target.
