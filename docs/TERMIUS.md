# AgentBox + Termius

## Host
- Label: AgentBox
- Host/IP: `100.123.66.15` (Tailscale)
- Port: `22`
- User: `box`
- OS: Debian (hostname `cursor`)

## After login
```bash
agent5 version
agent5 status
cd /workspace/agentbox-v5
```

## Dashboard (rc1)
Open in browser on the same Tailscale network:
`http://100.123.66.15:8787`

## Live build / tests
```bash
tail -f /workspace/agentbox-runs/live/rc1.log
# or
bash /workspace/agentbox-runs/live/watch.sh /workspace/agentbox-runs/live/rc1.log
```

Everything we build lands on this machine — Termius SSH is the same filesystem as the AgentBox desktop/Computer view.

## rc1 Dashboard
```bash
agent5 web status
agent5 web token    # copy Bearer token — do not commit/share publicly
```
Browser (same Tailscale network as AgentBox):
`http://100.123.66.15:8787`

Paste token in the login form, or call API:
```bash
TOKEN=$(agent5 web token)
curl -H "Authorization: Bearer $TOKEN" http://100.123.66.15:8787/api/v1/status
```

## Shared live terminal (Grok Bot + Termius)

Same `tmux` session on AgentBox — both sides see the same panes.

```bash
# From Termius after SSH login:
agentbox-live
# or:
tmux attach -t agentbox-live
```

Windows in the session:
- `live` — status + progress log (auto-refresh)
- `shell` — interactive shell (Ctrl+B then N to switch)

Append progress from either side:
```bash
agentbox-progress "deployed X"
```

Log file: `/workspace/agentbox-runs/live/progress.log`
