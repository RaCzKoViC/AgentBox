# Progressive disclosure

Skills load in stages to save context:

1. **Name + description** — always available for routing (`$skill` / implicit match).
2. **SKILL.md body** — loaded when the skill is selected.
3. **references/, scripts/, assets/** — read or executed only when needed.

## Practice

- Keep `SKILL.md` under a few thousand words when possible.
- Link references with clear "read when" cues.
- Put repeated logic in `scripts/` instead of prose.
- Do not duplicate large manuals already available upstream.
