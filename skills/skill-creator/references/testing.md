# Testing

```bash
python scripts/test_skill.py /path/to/skill
python scripts/doctor.py
```

## What `test_skill.py` covers

- Structure validation
- Metadata presence
- Script syntax compile
- Reference linkage heuristic
- SHOULD TRIGGER / SHOULD NOT TRIGGER prompts (routing heuristic — host still owns real matching)

## Self-test sequence

```text
create fixture → validate → inspect → test → modify → backup → package → cleanup
```

## Quality gates

`structure` · `metadata` · `references` · `scripts` · `security` · `trigger tests`

Statuses: `DRAFT` → `VALID` → `READY_LOCAL` → `PLUGIN_READY` → `INSTALLED` → `DISCOVERY_VERIFIED`
