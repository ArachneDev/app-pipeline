"""Image name and version: only a vX.Y.Z tag publishes; any other tag fails loudly.

Runs the real `vars` step from .github/workflows/build.yml.
"""

import tempfile
import unittest
from pathlib import Path

from workflow import run_step

SHA = "0123456789abcdef0123456789abcdef01234567"


def run_vars(ref_type, ref_name, app=""):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp, "out")
        out.write_text("")
        result = run_step("vars", {
            "APP": app, "REPO_NAME": "My-App", "OWNER": "ArachneDev",
            "REF_TYPE": ref_type, "REF_NAME": ref_name, "SHA": SHA,
            "GITHUB_OUTPUT": str(out),
        })
        outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    return result, outputs


class Version(unittest.TestCase):
    def test_branch_builds_sha_tag_and_does_not_publish(self):
        result, out = run_vars("branch", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(out["image"], "ghcr.io/arachnedev/my-app:sha-0123456789ab")
        self.assertEqual(out["publish"], "false")

    def test_version_tags_publish(self):
        for tag in ["v1.4.0", "v10.0.12", "v2.0.0-rc.1"]:
            with self.subTest(tag=tag):
                result, out = run_vars("tag", tag, app="pipeline-sample")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(out["image"], f"ghcr.io/arachnedev/pipeline-sample:{tag}")
                self.assertEqual(out["publish"], "true")

    def test_other_tags_fail_and_publish_nothing(self):
        # prod and staging are moved by the release flow; + is not a valid image tag.
        for tag in ["prod", "staging", "latest", "v1", "1.4.0", "v1.4.0+build.5", "v1.4"]:
            with self.subTest(tag=tag):
                result, out = run_vars("tag", tag)
                self.assertNotEqual(result.returncode, 0, f"tag {tag} was accepted")
                self.assertNotEqual(out.get("publish"), "true")


if __name__ == "__main__":
    unittest.main()
