# Distribution

## Local scopes

1. USER: `~/.agents/skills/<name>/` — private, all repos
2. REPO: `<repo>/.agents/skills/<name>/` — team/repo specific

## Package

```bash
python scripts/package_skill.py /path/to/skill -o dist
python scripts/package_skill.py /path/to/skill -o dist --plugin
```

Produces:

- `<name>-<timestamp>.skill.zip` — portable skill bundle
- `<name>-plugin/` — `.codex-plugin/plugin.json` + embedded skill (plugin-ready)

## ChatGPT / Codex plugins

Skills are the authoring format; **plugins** are the installable unit for broader distribution.

Steps:

1. Validate skill
2. Package with `--plugin`
3. Register via marketplace / plugin install UI
4. Verify `@` picker in ChatGPT only after host confirms install

If SYSTEM `plugin-creator` is available, prefer it for full plugin scaffolds.

## Honest status labels

- `FILES CREATED`
- `LOCAL VALIDATION PASSED`
- `CODEX DISCOVERY VERIFIED`
- `PLUGIN READY`
- `CHATGPT INSTALLATION REQUIRED`
- `CHATGPT DISCOVERY VERIFIED`
