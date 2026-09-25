# skill-creator

Professional Agent Skill for creating, validating, testing, packaging, and improving Agent Skills on AgentBox / Codex.

## Install locations

- **USER (preferred):** `~/.agents/skills/skill-creator/`
- **Repo copy:** `/workspace/agentbox-v5/skills/skill-creator/`

A SYSTEM/bundled `skill-creator` may also exist under `~/.codex/skills/.system/`. This package does **not** overwrite it.

## Invocation

| Surface | How | Status notes |
|---------|-----|--------------|
| Codex | `$skill-creator` or `/skills` | Works when skill is on a scanned path (USER/REPO) |
| ChatGPT | `@skill-creator` | Often needs plugin packaging + host install — verify in product UI |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/create_skill.py` | Atomic skill scaffold + install |
| `scripts/validate_skill.py` | PASS/WARN/FAIL validation |
| `scripts/inspect_skill.py` | Structure & invocation report |
| `scripts/test_skill.py` | Structure + trigger heuristics |
| `scripts/package_skill.py` | Zip + optional plugin scaffold |
| `scripts/doctor.py` | Environment & self-check |

## Example

```bash
python3 scripts/create_skill.py \
  --name ssh-doctor \
  --description "Diagnose SSH connectivity, auth, and agent forwarding issues. Use when troubleshooting SSH failures; not for general networking theory." \
  --scope user \
  --mode scripted
```

## Backups / rollback

Backups: `~/.local/share/agentbox/skill-backups/`

Restore by copying a backup directory back over the skill path (see implementation report).

## License

Provided for AgentBox use. No secrets embedded.
