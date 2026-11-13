"""The pin check: an action not pinned by commit goes red, a pinned one stays green."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "checks"))

import pins  # noqa: E402

SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


class PinCheck(unittest.TestCase):
    def test_commit_pin_and_local_call_pass(self):
        text = f"steps:\n  - uses: actions/checkout@{SHA} # v7.0.1\n  - uses: ./.github/workflows/build.yml\n"
        self.assertEqual(pins.violations(text), [])

    def test_tag_or_branch_pin_fails(self):
        for ref in ["v7", "v7.0.1", "main"]:
            with self.subTest(ref=ref):
                self.assertEqual(len(pins.violations(f"  - uses: actions/checkout@{ref}\n")), 1)

    def test_short_sha_fails(self):
        self.assertEqual(len(pins.violations(f"  - uses: actions/checkout@{SHA[:7]}\n")), 1)

    def test_docker_action_needs_digest(self):
        self.assertEqual(len(pins.violations("  - uses: docker://alpine:3.22\n")), 1)
        digest = "sha256:" + "a" * 64
        self.assertEqual(pins.violations(f"  - uses: docker://alpine@{digest}\n"), [])

    def test_this_repo_passes(self):
        self.assertEqual(pins.repo_violations(ROOT), [])


if __name__ == "__main__":
    unittest.main()
