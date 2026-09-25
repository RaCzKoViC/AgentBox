# Authoring guide

## Principles

1. Assume the model is capable — include only guidance that changes decisions.
2. Preserve user intent and scope.
3. Match specificity to risk.
4. Keep discovery cheap: precise `name` + `description`.
5. Disclose detail progressively.

## Description engine

Good:

> Create and validate Agent Skills for Codex. Use when scaffolding SKILL.md, packaging skills, or fixing skill metadata. Do not use for ordinary app coding.

Bad:

> Helps with development.

## Naming

Always `kebab-case`. Prefer concrete capability nouns: `ssh-doctor`, `repo-doctor`, `pdf-form-fill`.

## Choosing a mode

| Mode | When |
|------|------|
| instruction-only | Short procedural guidance, no scripts |
| scripted | Deterministic helpers needed |
| tool-aware | MCP/host tools required |
| plugin-ready | Intending ChatGPT/Codex plugin distribution |
| full | Scripts + references + agents + assets |

## Update pipeline

```text
DISCOVER → INSPECT → VALIDATE → IDENTIFY ISSUES
→ BACKUP → MODIFY → TEST → DIFF → APPROVE
```
