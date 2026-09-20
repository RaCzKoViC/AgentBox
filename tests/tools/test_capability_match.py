#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
from tools import registry
from tools.capability import find_tools
from tools.sandbox import shell_risk

def test_builtins_and_git_match():
    registry.ensure_builtins()
    ids = {t["id"] for t in registry.list_tools()}
    assert "git.status" in ids
    matches = find_tools("git")
    assert any(m["id"].startswith("git.") for m in matches)

def test_shell_denylist():
    info = shell_risk("rm -rf /tmp/x")
    assert info["denied"] is True

if __name__ == "__main__":
    test_builtins_and_git_match()
    test_shell_denylist()
    print("OK")
