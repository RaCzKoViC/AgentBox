# Metadata (`agents/openai.yaml`)

Optional Codex sidecar for UI and policy.

```yaml
interface:
  display_name: "Skill Creator"
  short_description: "Create, validate, test, improve, and package Agent Skills."
  brand_color: "#3B82F6"
  default_prompt: "Use $skill-creator to create a new reusable Agent Skill from my requirements."

policy:
  allow_implicit_invocation: true
```

## Rules

- Quote string values.
- `default_prompt` should mention `$skill-name`.
- `short_description` ~25–64 characters for UI scanning when possible.
- Declare only real MCP dependencies under `dependencies.tools`.
- Icon paths are relative to the skill root; missing icons → validator WARN.
