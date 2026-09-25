#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from create_skill import create_skill  # noqa: E402
from validate_skill import validate_skill  # noqa: E402


class CreatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sc-creator-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_scripted(self):
        report = create_skill(
            name="unit-demo-skill",
            description=(
                "Demonstrate skill-creator unit scaffolding for scripted skills. "
                "Use in automated tests; not for production."
            ),
            scope="user",
            mode="scripted",
            output=self.tmp,
        )
        self.assertEqual(report["status"], "CREATED", report)
        skill = self.tmp / "unit-demo-skill"
        self.assertTrue((skill / "SKILL.md").exists())
        v = validate_skill(skill, check_duplicates=False)
        self.assertNotEqual(v.status, "FAIL", v.to_dict())

    def test_collision_stop(self):
        create_skill(
            name="collide-me",
            description=(
                "Collision test skill for skill-creator. Use only in unit tests; "
                "do not use in production environments."
            ),
            output=self.tmp,
            mode="instruction-only",
        )
        report = create_skill(
            name="collide-me",
            description=(
                "Collision test skill for skill-creator. Use only in unit tests; "
                "do not use in production environments."
            ),
            output=self.tmp,
            mode="instruction-only",
        )
        self.assertEqual(report["status"], "STOPPED")
        self.assertEqual(report.get("reason"), "collision")

    def test_dry_run(self):
        report = create_skill(
            name="dry-run-skill",
            description=(
                "Dry-run demonstration skill for skill-creator tests. "
                "Use only in CI fixtures; not for end users."
            ),
            output=self.tmp,
            dry_run=True,
        )
        self.assertEqual(report["status"], "DRY_RUN")
        self.assertFalse((self.tmp / "dry-run-skill").exists())

    def test_update_backup(self):
        create_skill(
            name="update-me",
            description=(
                "Update path skill for skill-creator backup tests. "
                "Use in unit tests only; not for production."
            ),
            output=self.tmp,
            mode="instruction-only",
        )
        report = create_skill(
            name="update-me",
            description=(
                "Update path skill for skill-creator backup tests after change. "
                "Use in unit tests only; not for production."
            ),
            output=self.tmp,
            mode="instruction-only",
            update=True,
        )
        self.assertEqual(report["status"], "UPDATED", report)
        self.assertTrue(report.get("backup"))


if __name__ == "__main__":
    unittest.main()
