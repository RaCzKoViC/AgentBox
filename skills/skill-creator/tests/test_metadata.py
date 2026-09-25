#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import (  # noqa: E402
    normalize_skill_name,
    parse_frontmatter,
    validate_skill_name,
    description_quality_warnings,
)
import yaml  # noqa: E402


class MetadataTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_skill_name("My Skill"), "my-skill")
        self.assertEqual(normalize_skill_name("My--Skill"), "my-skill")

    def test_validate_name(self):
        ok, _ = validate_skill_name("ssh-doctor")
        self.assertTrue(ok)
        ok, _ = validate_skill_name("-bad")
        self.assertFalse(ok)
        ok, _ = validate_skill_name("bad--name")
        self.assertFalse(ok)

    def test_parse_frontmatter(self):
        text = "---\nname: x\ndescription: hello world trigger skill create validate\n---\n\nBody\n"
        fm, body, err = parse_frontmatter(text)
        self.assertIsNone(err)
        self.assertEqual(fm["name"], "x")
        self.assertIn("Body", body)

    def test_generic_description_warn(self):
        warns = description_quality_warnings("Helps with development.")
        self.assertTrue(warns)

    def test_openai_yaml_loads(self):
        path = ROOT / "agents" / "openai.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertIn("interface", data)
        self.assertTrue(data["interface"].get("display_name"))


if __name__ == "__main__":
    unittest.main()
