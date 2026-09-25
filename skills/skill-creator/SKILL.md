---
name: skill-creator
description: Create, design, update, validate, test, package, and improve Agent Skills for Codex and ChatGPT. Use when the user wants a new skill, to fix or improve SKILL.md, validate skill structure, package for distribution, or build reusable agent workflows. Do not use for ordinary application coding unrelated to Agent Skills.
metadata:
  short-description: Create, validate, test, and package Agent Skills
---

# Skill Creator

Build and maintain Agent Skills with progressive disclosure: lean `SKILL.md`, details in `references/`, deterministic logic in `scripts/`.

## Workflow

```text
INTENT → REQUIREMENTS → SCOPE → TRIGGERS → STRUCTURE
→ GENERATION → VALIDATION → TEST → INSTALL/DISTRIBUTION → REPORT
```

Recognize operations: **CREATE | UPDATE | VALIDATE | INSPECT | PACKAGE | TEST**.

## Scopes

| Scope | Path | Notes |
|-------|------|-------|
| REPO | `$REPO_ROOT/.agents/skills/<name>` | Repo-specific |
| USER | `$HOME/.agents/skills/<name>` | Preferred for private universal skills |
| ADMIN | `$CODEX_ADMIN_SKILLS` (typically host admin skills dir) | Only if writable and safe |
| SYSTEM | bundled under Codex | **Never modify** |

## Quick commands

```bash
python scripts/create_skill.py --name my-skill --description "..." --scope user --mode scripted
python scripts/validate_skill.py /path/to/skill
python scripts/inspect_skill.py /path/to/skill
python scripts/test_skill.py /path/to/skill
python scripts/package_skill.py /path/to/skill -o dist --plugin
python scripts/doctor.py
```

## Modes

`instruction-only` · `instruction+references` · `scripted` · `tool-aware` · `full` · `plugin-ready`

## Safety

- Atomic create (temp → validate → install); backup before update; support rollback.
- No passwords, API keys, tokens, or private keys in skill files.
- Do not overwrite SYSTEM/bundled skills. Collision without `--update`/`--force` → STOP.
- ChatGPT `@skill-creator` may require plugin install — do not claim picker success from Linux files alone.
- Codex: `$skill-creator` / `/skills` when installed on a discovered path.

## Read when needed

- Format: [references/skill-format.md](references/skill-format.md)
- Authoring: [references/authoring-guide.md](references/authoring-guide.md)
- Progressive disclosure: [references/progressive-disclosure.md](references/progressive-disclosure.md)
- Invocation: [references/invocation.md](references/invocation.md)
- Metadata: [references/metadata.md](references/metadata.md)
- Validation: [references/validation.md](references/validation.md)
- Testing: [references/testing.md](references/testing.md)
- Distribution: [references/distribution.md](references/distribution.md)
- Security: [references/security.md](references/security.md)
- Examples: [references/examples.md](references/examples.md)
