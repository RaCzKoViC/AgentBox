#!/usr/bin/env python3
"""Fixture repo health checker."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--path", type=Path, default=Path.cwd())
    args = p.parse_args()
    root = args.path
    if not (root / ".git").exists():
        print("WARN: not a git repository")
        return 0
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True)
    print("DIRTY" if dirty.stdout.strip() else "CLEAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
