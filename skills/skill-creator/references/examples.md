# Examples

## Create scripted skill

```bash
python scripts/create_skill.py \
  --name repo-doctor \
  --description "Analyze Git repository health: remotes, dirty state, hooks, and large files. Use for repo diagnostics; not for general Git tutorials." \
  --scope user \
  --mode scripted
```

## Validate

```bash
python scripts/validate_skill.py ~/.agents/skills/repo-doctor
```

## Update with backup

```bash
python scripts/create_skill.py \
  --name repo-doctor \
  --description "..." \
  --scope user \
  --mode scripted \
  --update
```

## Package plugin-ready

```bash
python scripts/package_skill.py ~/.agents/skills/repo-doctor -o /tmp/skill-dist --plugin
```

## UX sketch

```text
$skill-creator
Create skill AgentBox Backup that backs up SQLite DB and config.
```

Expected behavior: propose `agentbox-backup`, choose USER scope + scripted mode, generate, validate, test, report path.
