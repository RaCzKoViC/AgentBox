# Policy package (beta3)

Modules:
- `risk.py` — risk scoring + levels + persistence
- `policies.py` — INI (`~/.config/agentbox-v5/policies.ini`) + TOML + evaluate_policy
- `budgets.py` — budget scopes + usage table + check/record
- `permissions.py` — agent permission profiles
- `approvals.py` — approval queue (alpha3-compatible + beta3 columns)
- `enforcement.py` — `enforce_action()` pipeline

## Autonomy

`AGENTBOX_AUTO_APPROVE=1` (default): auto-approve non-CRITICAL approvals.
CRITICAL actions (`force_push`, privileged docker, `/etc` writes) still **DENY**.
