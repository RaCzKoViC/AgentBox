# Skill format

An Agent Skill is a **directory** containing a required `SKILL.md` plus optional resources.

```text
my-skill/
├── SKILL.md              # required
├── agents/openai.yaml    # optional Codex UI / policy
├── scripts/              # optional executables
├── references/           # optional docs loaded on demand
└── assets/               # optional output templates/binaries
```

## SKILL.md

YAML frontmatter + Markdown body.

### Required frontmatter

| Field | Rules |
|-------|--------|
| `name` | 1–64 chars; `a-z`, `0-9`, hyphens; no leading/trailing/consecutive hyphens; must match directory name |
| `description` | 1–1024 chars; what + when; front-load trigger words; no `<`/`>` |

### Optional frontmatter

`license`, `compatibility`, `metadata` (string map), `allowed-tools` (experimental).

## Official sources

- OpenAI Codex skills docs: https://developers.openai.com/codex/skills
- Agent Skills specification (agentskills): name/description constraints above

## Differences noted (2026)

- Codex adds `agents/openai.yaml` for UI and `policy.allow_implicit_invocation`.
- Discovery paths for Codex: `~/.agents/skills`, `<repo>/.agents/skills` (walk-up), admin `/etc/codex/skills`, plus bundled SYSTEM skills.
- Plugins are the installable distribution unit; skills are the authoring format.
