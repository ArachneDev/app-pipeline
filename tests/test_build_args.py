"""The build-args check in the shared workflow: secret-shaped input fails, plain input passes.

Runs the real step from .github/workflows/build.yml, so the test and the
workflow can't drift. Needs bash and gitleaks on PATH (the check image has both).
"""

import secrets
import subprocess
import unittest
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "build.yml"


def build_args_step():
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    for job in jobs.values():
        for step in job.get("steps", []):
            if step.get("id") == "build-args":
                return step
    raise AssertionError("no step with id build-args in build.yml")


def run_check(build_args):
    step = build_args_step()
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "BUILD_ARGS": build_args},
        capture_output=True,
        text=True,
    )


def fake_token():
    # Built at run time so the repo's own gitleaks scan never sees one.
    return "ghp_" + secrets.token_hex(18)


class BuildArgsCheck(unittest.TestCase):
    def assert_fails(self, build_args, secret=None):
        result = run_check(build_args)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        if secret:
            self.assertNotIn(secret, result.stdout + result.stderr, "the check printed the secret")

    def assert_passes(self, build_args):
        result = run_check(build_args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_step_reads_input_from_env_only(self):
        # An expression in the script would let a caller's input run as shell.
        self.assertNotIn("${{", build_args_step()["run"])

    def test_no_build_args_passes(self):
        self.assert_passes("")

    def test_plain_build_args_pass(self):
        self.assert_passes("NODE_ENV=production\nAPP_NAME=pipeline-sample\nAUTHOR=x\nKEYBOARD=us\n")

    def test_secret_shaped_names_fail(self):
        for name in ["NPM_TOKEN", "DB_PASSWORD", "api_key", "CLIENT_SECRET", "AWS_ACCESS_KEY_ID", "AUTH_HEADER"]:
            with self.subTest(name=name):
                self.assert_fails(f"{name}=x\n", secret=None)

    def test_planted_token_value_fails_without_printing_it(self):
        token = fake_token()
        self.assert_fails(f"GREETING={token}\n", secret=token)

    def test_line_without_equals_fails(self):
        self.assert_fails("JUSTANAME\n")


if __name__ == "__main__":
    unittest.main()
