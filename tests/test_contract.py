"""The contract test in the shared workflow: the sample passes; each broken fixture fails with a message naming the contract line and the fix.

Runs the real `contract` step from .github/workflows/build.yml (see workflow.py)
against images built here. Needs a container engine, so `make check` (no engine)
skips it; `make contract-test` and CI's `contract-test` job run it.
"""

import os
import secrets
import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow import ROOT, run_step

ENGINE = os.environ.get("ENGINE", "")
FIXTURES = ROOT / "tests" / "fixtures" / "contract"
SAMPLE = ROOT / "sample"
VERSION = "v0.0.0-contract"


def build(context):
    tag = f"localhost/contract-test-{context.name}:{secrets.token_hex(4)}"
    subprocess.run(
        [ENGINE, "build", "-q", "--build-arg", f"VERSION={VERSION}", "-f", str(context / "Containerfile"), "-t", tag, str(context)],
        check=True, capture_output=True,
    )
    return tag


def run_contract(image, context=SAMPLE, app_json=""):
    env = {
        "ENGINE": ENGINE, "IMAGE": image, "VERSION": VERSION, "CONTEXT": str(context),
        "APP_JSON": app_json, "HEALTH_PATH": "/healthz", "MEMORY": "512m", "HEALTH_TIMEOUT": "20",
    }
    if ENGINE == "podman":
        # Rootless Podman needs its runtime dir; the step runs with a minimal env.
        env |= {k: os.environ[k] for k in ("HOME", "XDG_RUNTIME_DIR") if k in os.environ}
    return run_step("contract", env, cwd=ROOT)


@unittest.skipUnless(ENGINE, "needs ENGINE=docker or ENGINE=podman; run `make contract-test`")
class ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = {name: build(path) for name, path in
                      [("sample", SAMPLE)] + [(p.name, p) for p in sorted(FIXTURES.iterdir())]}

    @classmethod
    def tearDownClass(cls):
        subprocess.run([ENGINE, "rmi", "-f", *cls.images.values()], capture_output=True)

    def assert_fails_with(self, result, *needles):
        out = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, out)
        for needle in needles:
            self.assertIn(needle, out)
        return out

    def test_compliant_sample_passes(self):
        result = run_contract(self.images["sample"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("meets the container contract", result.stdout)

    def test_root_image_fails(self):
        self.assert_fails_with(run_contract(self.images["root"]),
                               "runs as root", "Contract: runs as a non-root user", "Fix: add a numeric USER")

    def test_filesystem_writing_image_fails(self):
        self.assert_fails_with(run_contract(self.images["writes-fs"]),
                               "wrote to the read-only root filesystem", "Contract: runs under hardened defaults",
                               "Fix: write temporary files under /tmp")

    def test_hardcoded_port_image_fails(self):
        self.assert_fails_with(run_contract(self.images["hardcoded-port"]),
                               "listens on port 3000, not on PORT=", "Contract: listens on the port given in PORT",
                               "Fix: read the port from the PORT environment variable")

    def test_missing_env_example_and_readme_sections_fail(self):
        with tempfile.TemporaryDirectory() as context:
            Path(context, "README.md").write_text("# app\n\n## Port\n\n3000\n")
            out = self.assert_fails_with(run_contract(self.images["sample"], context=Path(context)),
                                         ".env.example is missing", "Fix: add .env.example")
        for section in ("Volumes", "Dependencies", "Memory"):
            self.assertIn(section, out)
        self.assertNotIn("Port,", out)

    def test_named_secrets_sample_that_is_missing_fails(self):
        self.assert_fails_with(run_contract(self.images["sample"], app_json="nope.json"),
                               "app-json names nope.json", "Fix:")


if __name__ == "__main__":
    unittest.main()
