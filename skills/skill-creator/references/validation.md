# Validation

```bash
python scripts/validate_skill.py /path/to/skill
python scripts/validate_skill.py /path/to/skill --json
python scripts/validate_skill.py /path/to/skill --strict
```

## Checks

- Directory + `SKILL.md` present
- Frontmatter parse + allowed keys
- Name kebab-case + matches directory
- Description present, length, quality warnings
- Broken markdown references
- `agents/openai.yaml` parse + icon paths
- Dangerous command patterns in scripts (WARN)
- Embedded secret patterns (WARN/FAIL, values never printed)
- Duplicate name awareness across scopes (WARN)

## Exit codes

| Status | Exit |
|--------|------|
| PASS | 0 |
| WARN | 0 (1 with `--strict`) |
| FAIL | 1 |
