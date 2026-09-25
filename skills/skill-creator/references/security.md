# Security

## Never embed

- Passwords, API keys, tokens, cookies, session secrets
- SSH / TLS private keys
- Raw `.env` contents

Validator scans for common patterns and reports **labels only** (values redacted).

## Dangerous automation

Generated scripts must not auto-run without policy/approval:

- `sudo`
- `rm -rf /...`
- `git push --force`
- `curl | sh`

## Scopes

- Never modify SYSTEM/bundled skills
- ADMIN only when writable and explicitly requested
- Backup before update; rollback on failed install

## Audit

Audit log (no secrets): `~/.local/share/agentbox/skill-creator-audit.jsonl`
