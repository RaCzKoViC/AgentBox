#!/usr/bin/env python3
"""Probe whether expected tools exist on PATH."""
from __future__ import annotations

import argparse
import shutil


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tools", nargs="*", default=[])
    args = parser.parse_args()
    missing = [t for t in args.tools if shutil.which(t) is None]
    if missing:
        print("MISSING:", ", ".join(missing))
        return 1
    print("OK: all tools present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
