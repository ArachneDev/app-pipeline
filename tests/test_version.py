"""Image name and version: only a vX.Y.Z tag publishes; any other tag fails loudly.

Runs the real `vars` step from .github/workflows/build.yml.
"""

import tempfile
import unittest
from pathlib import Path

from workflow import run_step

SHA = "0123456789abcdef0123456789abcdef01234567"


def run_vars(ref_type, ref_name, app="", event="push", promote="false", dispatch_version=""):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp, "out")
        out.write_text("")
        result = run_step("vars", {
            "APP": app, "REPO_NAME": "My-App", "OWNER": "ArachneDev",
            "REF_TYPE": ref_type, "REF_NAME": ref_name, "SHA": SHA,
            "EVENT_NAME": event, "PROMOTE": promote, "DISPATCH_VERSION": dispatch_version,
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
        self.assertEqual(out["channel"], "")

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


class Channels(unittest.TestCase):
    def test_promote_is_off_unless_the_caller_asks(self):
        for ref in (("tag", "v1.4.0"), ("branch", "staging")):
            result, out = run_vars(*ref)
            self.assertEqual(out["channel"], "", ref)

    def test_a_version_tag_goes_to_production(self):
        result, out = run_vars("tag", "v1.4.0", promote="true")
        self.assertEqual((out["channel"], out["publish"], out["build"]), ("production", "true", "true"))

    def test_a_push_to_staging_publishes_a_sha_tag_for_staging(self):
        result, out = run_vars("branch", "staging", promote="true")
        self.assertEqual(out["channel"], "staging")
        self.assertEqual(out["publish"], "true")
        self.assertEqual(out["image"], "ghcr.io/arachnedev/my-app:sha-0123456789ab")

    def test_other_branches_and_pull_requests_do_not_promote(self):
        for ref, event in (("main", "push"), ("7/merge", "pull_request"), ("staging", "pull_request")):
            with self.subTest(ref=ref, event=event):
                result, out = run_vars("branch", ref, event=event, promote="true")
                self.assertEqual((out["channel"], out["publish"]), ("", "false"))

    def test_dispatch_repromotes_a_version_without_building(self):
        result, out = run_vars("branch", "main", event="workflow_dispatch", promote="true", dispatch_version="v1.2.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((out["channel"], out["build"], out["publish"], out["version"]), ("production", "false", "false", "v1.2.0"))

    def test_dispatch_refuses_a_version_that_is_not_a_version_tag(self):
        for v in ("", "prod", "staging", "v1", "main", "v1.2.0 && echo"):
            with self.subTest(version=v):
                result, out = run_vars("branch", "main", event="workflow_dispatch", promote="true", dispatch_version=v)
                self.assertNotEqual(result.returncode, 0)

    def test_dispatch_needs_promote(self):
        result, out = run_vars("branch", "main", event="workflow_dispatch", dispatch_version="v1.2.0")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
