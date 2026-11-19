"""The push step: a published tag never moves.

Runs the real `push` step from .github/workflows/build.yml with a stub `docker`
and `skopeo`. A rerun on an existing version tag used to push over the image.
"""

import unittest

from stubs import Registry, digest
from workflow import run_step

IMAGE = "ghcr.io/arachnedev/app"


class Push(unittest.TestCase):
    def setUp(self):
        self.reg = Registry()
        self.addCleanup(self.reg.close)
        self.fresh = digest("fresh")

    def push(self, version, **extra):
        env = self.reg.env() | {
            "IMAGE": f"{IMAGE}:{version}", "VERSION": version, "TOKEN": "unused", "ACTOR": "bot",
            "HOME": str(self.reg.dir), "STUB_PUSH_DIGEST": self.fresh, "GITHUB_OUTPUT": str(self.reg.dir / "out"),
        } | extra
        (self.reg.dir / "out").write_text("")
        result = run_step("push", env)
        pushed = any(c.startswith("push") for c in self.reg.calls())
        outputs = dict(l.split("=", 1) for l in (self.reg.dir / "out").read_text().splitlines())
        return result, result.stdout + result.stderr, pushed, outputs

    def test_a_new_version_is_pushed(self):
        result, out, pushed, outputs = self.push("v1.4.0")
        self.assertEqual(result.returncode, 0, out)
        self.assertTrue(pushed)
        self.assertEqual(outputs["digest"], self.fresh)

    def test_a_version_tag_that_exists_is_not_overwritten(self):
        old = self.reg.add("old", tags=["v1.4.0"])
        result, out, pushed, outputs = self.push("v1.4.0")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(pushed)
        self.assertEqual(self.reg.tag_of("v1.4.0"), old)
        self.assertIn("already published", out)
        self.assertIn(old, out)

    def test_a_staging_build_that_exists_is_kept(self):
        old = self.reg.add("old", tags=["sha-0123456789ab"])
        result, out, pushed, outputs = self.push("sha-0123456789ab")
        self.assertEqual(result.returncode, 0, out)
        self.assertFalse(pushed)
        self.assertEqual(outputs["digest"], old)

    def test_a_registry_error_pushes_nothing(self):
        result, out, pushed, outputs = self.push("v1.4.0", STUB_READ_ERROR="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(pushed)


if __name__ == "__main__":
    unittest.main()
