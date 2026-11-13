"""The build-args check in the shared workflow: secret-shaped input fails, plain input passes.

Runs the real step from .github/workflows/build.yml (see workflow.py).
"""

import tempfile
import unittest
from pathlib import Path

from workflow import fake_token, run_step, step

# A config an app could commit to switch every rule off.
ALLOW_ALL = "[extend]\nuseDefault = true\n\n[[allowlists]]\nregexes = ['.*']\n"


def run_check(build_args, cwd=None):
    return run_step("build-args", {"BUILD_ARGS": build_args}, cwd=cwd)


class BuildArgsCheck(unittest.TestCase):
    def assert_fails(self, build_args, secret=None, cwd=None):
        result = run_check(build_args, cwd=cwd)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        if secret:
            self.assertNotIn(secret, result.stdout + result.stderr, "the check printed the secret")

    def assert_passes(self, build_args):
        result = run_check(build_args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_step_reads_input_from_env_only(self):
        # An expression in the script would let a caller's input run as shell.
        self.assertNotIn("${{", step("build-args")["run"])

    def test_no_build_args_passes(self):
        self.assert_passes("")

    def test_plain_build_args_pass(self):
        self.assert_passes("NODE_ENV=production\nAPP_NAME=pipeline-sample\nAUTHOR=x\nKEYBOARD=us\n")

    def test_secret_shaped_names_fail(self):
        for name in ["NPM_TOKEN", "DB_PASSWORD", "api_key", "CLIENT_SECRET", "AWS_ACCESS_KEY_ID", "AUTH_HEADER"]:
            with self.subTest(name=name):
                self.assert_fails(f"{name}=x\n")

    def test_planted_token_value_fails_without_printing_it(self):
        token = fake_token()
        self.assert_fails(f"GREETING={token}\n", secret=token)

    def test_gitleaks_allow_comment_does_not_silence_a_value(self):
        token = fake_token()
        self.assert_fails(f"GREETING={token} gitleaks:allow\n", secret=token)

    def test_config_in_the_app_repo_does_not_silence_a_value(self):
        # The step runs in the caller's checkout, which the caller controls.
        token = fake_token()
        with tempfile.TemporaryDirectory() as repo:
            Path(repo, ".gitleaks.toml").write_text(ALLOW_ALL)
            self.assert_fails(f"GREETING={token}\n", secret=token, cwd=repo)

    def test_line_without_equals_fails(self):
        self.assert_fails("JUSTANAME\n")


if __name__ == "__main__":
    unittest.main()
