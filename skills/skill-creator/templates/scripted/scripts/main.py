#!/usr/bin/env python3
"""Primary helper for {{NAME}}."""
from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="{{TITLE}} helper")
    parser.add_argument("--check", action="store_true", help="Run a health check")
    args = parser.parse_args()
    if args.check:
        print("OK: {{NAME}} helper ready")
        return 0
    print("{{TITLE}}: replace this stub with real logic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
