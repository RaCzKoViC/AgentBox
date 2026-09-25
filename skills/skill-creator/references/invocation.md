# Invocation

## Codex

- Explicit: `$skill-creator`
- Picker: `/skills`
- Implicit: when `policy.allow_implicit_invocation` is true (default) and the prompt matches the description

Discovery scans USER, REPO (walk-up), ADMIN, and SYSTEM paths. Duplicate names may coexist; do not overwrite SYSTEM.

## ChatGPT

- Target UX: `@skill-creator` in the mention picker
- Host owns `@` parsing — skills do not implement a custom `@` parser
- Local USER install on AgentBox **does not guarantee** ChatGPT desktop picker registration
- Prefer plugin packaging + marketplace/install when `@` visibility is required

## Implicit trigger examples (this skill)

SHOULD: "create an agent skill", "validate this SKILL.md", "package my skill"

SHOULD NOT: "fix this Rust function", "what is SSH?", "create a PNG icon"
