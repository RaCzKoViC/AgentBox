---
name: repo-doctor
description: Analyze Git repository health including remotes, dirty worktrees, hooks, and oversized files. Use for repository diagnostics and repair planning; do not use for general Git tutorials.
---

# Repo Doctor

## Workflow
1. Detect git root.
2. Run `scripts/check_repo.py`.
3. Summarize findings with severity.
4. Suggest safe fixes (no force-push).

## References
See [references/checks.md](references/checks.md).
