# Security Policy

Self Ershov Memory handles staged writes and writeback safety. Treat anything that touches live roots, artifact validation, or proposal generation as security-sensitive.

## Supported versions

Security fixes are handled on the current `main` branch and the latest tagged release.

## Reporting a vulnerability

Do **not** open a public issue for:

- secrets or tokens in source, logs, or proposals
- path traversal or unsafe write behavior
- unexpected live mutation
- backup or discard failures
- any bug that could expose private data

Instead, open a **private GitHub security advisory**:

- https://github.com/ersh123/self-ershov-memory/security/advisories/new

Include:

- the affected version or commit
- exact steps to reproduce
- sanitized logs or screenshots
- the file or path involved, if relevant
- whether the problem touches live roots, artifact roots, or backups

## What we care about

- secret-like content rejection
- path safety
- approval gates for apply/discard
- backup integrity
- keeping staged artifacts reviewable instead of silently mutating live state

## Response expectations

If you report a valid issue privately, the maintainers will triage it promptly and keep the details out of public threads until the fix is ready.
