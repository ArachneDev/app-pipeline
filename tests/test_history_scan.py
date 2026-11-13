"""The history scan in the shared workflow: a secret in the built history fails,
and nothing the app repo commits can switch the scan off.

Runs the real step from .github/workflows/build.yml on a throwaway git repo.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow import PATH, fake_token, run_step

GIT_ENV = {
    "PATH": PATH,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
}


class HistoryScan(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        self.git("init", "-q", "-b", "main")
        self.commit("README", "hello\n")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", self.repo, *args], env=GIT_ENV, check=True, capture_output=True)

    def commit(self, name, text):
        Path(self.repo, name).write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"add {name}")

    def scan(self):
        return run_step("history", {"HOME": self.repo}, cwd=self.repo)

    def assert_fails(self, token):
        result = self.scan()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(token, result.stdout + result.stderr, "the scan printed the secret")

    def test_clean_history_passes(self):
        result = self.scan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_deleted_secret_in_history_fails(self):
        token = fake_token()
        self.commit("config.env", f"GH={token}\n")
        os.remove(Path(self.repo, "config.env"))
        self.commit("README", "removed it\n")
        self.assert_fails(token)

    def test_repo_config_and_ignore_file_do_not_silence_it(self):
        token = fake_token()
        self.commit("config.env", f"GH={token}\n")
        self.commit(".gitleaks.toml", "[extend]\nuseDefault = true\n\n[[allowlists]]\npaths = ['.*']\n")
        self.commit(".gitleaksignore", "config.env:github-pat:1\n")
        self.assert_fails(token)

    def test_allow_comment_does_not_silence_it(self):
        token = fake_token()
        self.commit("config.env", f"GH={token} # gitleaks:allow\n")
        self.assert_fails(token)

    def test_secret_only_on_another_branch_does_not_fail_this_build(self):
        # The build is of HEAD; an unmerged branch elsewhere is not in the image.
        self.git("checkout", "-q", "-b", "side")
        self.commit("config.env", f"GH={fake_token()}\n")
        self.git("checkout", "-q", "main")
        result = self.scan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
