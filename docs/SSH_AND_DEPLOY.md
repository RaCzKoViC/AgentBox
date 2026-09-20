# SSH, Tailscale & Termius — AgentBox Control Plane

## Reference host (production Control Plane)

| Field | Value |
|-------|--------|
| Hostname | `cursor` |
| Tailscale IP | `100.123.66.15` |
| SSH port | `22` |
| User | `box` |
| Project root | `/workspace/agentbox-v5` (or clone of this repo) |
| Dashboard | `http://100.123.66.15:8787` |

> Put **SSH keys** or store the password in Termius / 1Password — **never** in git.

## Termius

1. Host: `100.123.66.15`, port `22`, user `box`, OS Linux/Debian.  
2. After login:

```bash
agent5 version
agent5 status
agentbox-live          # shared tmux with live status + progress log
```

3. Dashboard in a browser on the same Tailscale network; token via `agent5 web token`.

## Deploy guard

Installers call `agentbox-deploy-guard` so upgrades only run on the designated host (`cursor` / expected Tailscale IP / user `box` / expected root).

```bash
agentbox-deploy-guard
cd /workspace/agentbox-v5   # or this repo path
./install.sh
```

## Connecting a remote worker

On another machine with Tailscale reachability to the Control Plane:

```bash
agent5 worker token create          # on Control Plane
agent5-worker enroll --url http://100.123.66.15:8787 --token <one-time>
agent5-worker start
```

## What not to commit

- `~/.config/agentbox-v5/secrets/admin.token`
- SSH passwords / private keys  
- Provider API keys  
- Live SQLite DB / backups with secrets
