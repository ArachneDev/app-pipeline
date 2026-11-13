"""The gitleaks pin in build.yml equals the one in the check image, so the
tests run the same gitleaks the shared workflow runs."""

import re
import unittest

from workflow import ROOT, WORKFLOW

import yaml


class GitleaksPin(unittest.TestCase):
    def test_build_and_check_image_pin_the_same_gitleaks(self):
        env = yaml.safe_load(WORKFLOW.read_text())["jobs"]["build"]["env"]
        image = (ROOT / "tools" / "check-image" / "Containerfile").read_text()
        for name in ["GITLEAKS_VERSION", "GITLEAKS_SHA256"]:
            with self.subTest(name=name):
                found = re.search(rf"^ARG {name}=(\S+)$", image, re.MULTILINE)
                self.assertIsNotNone(found, f"no ARG {name} in the check image")
                self.assertEqual(str(env[name]), found.group(1))


if __name__ == "__main__":
    unittest.main()
