# AgentBox v5 Event Taxonomy (beta2)

Events are stored in SQLite `events` via `emit_event(kind, message, task_id, run_id, payload)`.
Kinds use dotted namespaces. Existing alpha/beta1 kinds remain valid.

## task.*
| Kind | When |
|------|------|
| `task.created` | Task inserted |
| `task.queued` | Status → queued |
| `task.scheduled` | Claimed by daemon |
| `task.started` / `task.running` | Runner begins |
| `task.completed` | Success |
| `task.failed` | Failure |
| `task.blocked` | Blocked (e.g. required handoff failed) |
| `task.cancelled` | Cancelled |
| `task.status_changed` | Generic status transition |

## agent.*
| Kind | When |
|------|------|
| `agent.registered` | Registry register/update |
| `agent.status` | Status change |
| `agent.run.started` | Agent run begins |
| `agent.run.finished` | Agent run ends |

## handoff.*
| Kind | When |
|------|------|
| `handoff.created` | Handoff requested |
| `handoff.accepted` | Target accepted |
| `handoff.started` | Work began |
| `handoff.completed` | Success |
| `handoff.failed` | Failed (may retry) |
| `handoff.rejected` | Explicit reject |
| `handoff.retried` | Retry scheduled |

## provider.*
| Kind | When |
|------|------|
| `provider.request` | Provider call started |
| `provider.response` | Provider returned |
| `provider.error` | Provider error |

## sandbox.*
| Kind | When |
|------|------|
| `sandbox.created` | Sandbox provisioned |
| `sandbox.destroyed` | Sandbox torn down |
| `sandbox.error` | Sandbox failure |

## approval.*
| Kind | When |
|------|------|
| `approval.created` | Gate created |
| `approval.approved` | Approved |
| `approval.rejected` | Rejected |

## Legacy (kept)
`budget.exceeded`, `plan.stub`, `run.*`, and other pre-beta2 kinds remain supported.
