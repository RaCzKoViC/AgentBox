#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_skill import validate_skill  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


class ValidatorTests(unittest.TestCase):
    def test_hello_pass(self):
        r = validate_skill(FIX / "hello-skill", check_duplicates=False)
        self.assertIn(r.status, ("PASS", "WARN"), r.to_dict())

    def test_repo_doctor_pass(self):
        r = validate_skill(FIX / "repo-doctor", check_duplicates=False)
        self.assertNotEqual(r.status, "FAIL", r.to_dict())

    def test_missing_description_fail(self):
        r = validate_skill(FIX / "invalid-no-description", check_duplicates=False)
        self.assertEqual(r.status, "FAIL")
        codes = {f.code for f in r.findings}
        self.assertIn("description.missing", codes)

    def test_bad_name_fail(self):
        r = validate_skill(FIX / "invalid-bad-name", check_duplicates=False)
        self.assertEqual(r.status, "FAIL")
        codes = {f.code for f in r.findings}
        self.assertTrue("name.invalid" in codes or "name.mismatch" in codes)

    def test_secret_detected_without_value(self):
        r = validate_skill(FIX / "invalid-secret", check_duplicates=False)
        secret_findings = [f for f in r.findings if f.code == "security.secret"]
        self.assertTrue(secret_findings)
        for f in secret_findings:
            self.assertNotIn("sk-AAAA", f.message)
            self.assertIn("redacted", f.message.lower())


if __name__ == "__main__":
    unittest.main()
