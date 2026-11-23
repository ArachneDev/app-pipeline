"""The contract test in the shared workflow: the sample passes; each broken fixture fails with a message naming the contract line and the fix.

Runs the real `contract` step from .github/workflows/build.yml (see workflow.py)
against images built here. Needs a container engine, so `make check` (no engine)
skips it; `make contract-test` and CI's `contract-test` job run it.
"""

import os
import secrets
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow import ROOT, run_step, step

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


def run_contract(image, context=SAMPLE, app_json="", version=VERSION, exec_modes=""):
    env = {
        "ENGINE": ENGINE, "IMAGE": image, "VERSION": version, "CONTEXT": str(context),
        "APP_JSON": app_json, "HEALTH_PATH": "/healthz", "MEMORY": "512m", "HEALTH_TIMEOUT": "20",
        "CONTRACT_EXEC": exec_modes,
    }
    if ENGINE == "podman":
        # Rootless Podman needs its runtime dir; the step runs with a minimal env.
        env |= {k: os.environ[k] for k in ("HOME", "XDG_RUNTIME_DIR") if k in os.environ}
    return run_step("contract", env, cwd=ROOT)


class RunFlags(unittest.TestCase):
    # Runs in `make check`. Each flag is a contract line; dropping one needs an infra change first.
    def test_production_hardening_flags_are_all_there(self):
        flags = step("contract")["env"]["RUN_FLAGS"].split()
        for flag in ["--read-only", "--cap-drop=all", "--security-opt=no-new-privileges", "--pids-limit=2048"]:
            self.assertIn(flag, flags)
        for path in ["/tmp", "/var/tmp", "/run"]:
            # Podman's read-only tmpfs is exec; Docker's default is noexec.
            self.assertIn(f"--tmpfs={path}:rw,exec,nosuid,nodev", flags)


class Inputs(unittest.TestCase):
    # Runs in `make check`: bad inputs are refused before any engine call.
    def check(self, **inputs):
        env = {"IMAGE": "unused", "VERSION": VERSION, "CONTEXT": str(SAMPLE), "APP_JSON": "",
               "HEALTH_PATH": "/healthz", "MEMORY": "512m", "ENGINE": "false"} | inputs
        result = run_step("contract", env, cwd=ROOT)
        return result.returncode, result.stdout + result.stderr

    def test_memory_without_a_limit_is_refused(self):
        # 0 means no limit to Docker and Podman; a bare number means bytes.
        for memory in ("0", "00", "0m", "512"):
            code, out = self.check(MEMORY=memory)
            self.assertNotEqual(code, 0, memory)
            self.assertIn("memory must be a size such as 512m", out)

    def test_app_json_value_is_never_printed(self):
        # A caller who pastes the secrets themselves instead of a path must not see them in the log.
        code, out = self.check(APP_JSON='{"TOKEN": "canary-4f2e"}')
        self.assertNotEqual(code, 0)
        self.assertIn("app-json does not name a file", out)
        self.assertNotIn("canary-4f2e", out)

    def test_named_secrets_sample_that_is_missing_fails(self):
        code, out = self.check(APP_JSON="nope.json")
        self.assertNotEqual(code, 0)
        self.assertIn("app-json does not name a file", out)
        self.assertIn("Fix:", out)

    def test_malformed_contract_exec_is_refused(self):
        for value in ("sleep 300", "sleep 300 | ", " | cat /www/healthz", "ok | fine\nno pipe here"):
            code, out = self.check(CONTRACT_EXEC=value)
            self.assertNotEqual(code, 0, value)
            self.assertIn("contract-exec needs one '<exec> | <health>' per line", out)

    def test_empty_hardening_flags_are_refused(self):
        code, out = self.check(RUN_FLAGS="\n")
        self.assertNotEqual(code, 0)
        self.assertIn("RUN_FLAGS is empty", out)


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

    def test_empty_contract_exec_tests_only_the_default_mode(self):
        for value in ("", "\n  \n"):
            result = run_contract(self.images["sample"], exec_modes=value)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("mode '", result.stdout + result.stderr)

    # The sample is busybox: `sleep` keeps a mode up, and /www/healthz holds the build version.
    def test_exec_mode_that_is_healthy_with_the_version_passes(self):
        result = run_contract(self.images["sample"], exec_modes="sleep 300 | cat /www/healthz")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Running mode 'sleep 300'", result.stdout)
        self.assertIn("meets the container contract", result.stdout)

    def test_each_exec_mode_is_tested_and_one_failure_fails_the_run(self):
        out = self.assert_fails_with(
            run_contract(self.images["sample"], exec_modes="sleep 300 | cat /www/healthz\ntrue | cat /www/healthz"),
            "mode 'true': the container exited with code 0")
        self.assertNotIn("mode 'sleep 300'", out.split("::error")[-1])

    def test_exec_mode_that_exits_early_fails(self):
        self.assert_fails_with(run_contract(self.images["sample"], exec_modes="true | cat /www/healthz"),
                               "mode 'true': the container exited with code 0 before its health command passed",
                               "Fix: make the mode start and keep running")

    def test_exec_mode_whose_health_never_passes_fails(self):
        self.assert_fails_with(run_contract(self.images["sample"], exec_modes="sleep 300 | false"),
                               "mode 'sleep 300': the health command 'false' did not exit 0 within 20s",
                               "Fix: make the health command succeed")

    def test_exec_mode_healthy_without_the_version_fails(self):
        self.assert_fails_with(run_contract(self.images["sample"], exec_modes="sleep 300 | echo ok"),
                               "mode 'sleep 300': the health command 'echo ok' passed but its output did not include the build version",
                               "Fix: make the health command print the VERSION")

    def test_exec_mode_with_a_missing_command_fails(self):
        self.assert_fails_with(run_contract(self.images["sample"], exec_modes="no-such-bin | cat /www/healthz"),
                               "mode 'no-such-bin'")

    def test_app_reads_its_sample_secrets_file(self):
        fixture = FIXTURES / "reads-secrets"
        with tempfile.TemporaryDirectory() as context:
            for name in ("README.md", ".env.example"):
                shutil.copy(SAMPLE / name, context)
            shutil.copy(fixture / "app.json.example", context)
            result = run_contract(self.images["reads-secrets"], context=Path(context), app_json="app.json.example")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # Without it the app gets {} and refuses to start.
            self.assert_fails_with(run_contract(self.images["reads-secrets"], context=Path(context)),
                                   "exited with code 3", "GREETING missing")

    def test_health_body_with_a_longer_version_fails(self):
        # The sample answers v0.0.0-contract: that is not the build version v0.0.0.
        self.assert_fails_with(run_contract(self.images["sample"], version="v0.0.0"),
                               "did not include the build version v0.0.0")

    def test_root_image_fails(self):
        self.assert_fails_with(run_contract(self.images["root"]),
                               "may run as root", "Contract: runs as a non-root user", "Fix: add a numeric USER")

    def test_root_by_another_spelling_fails(self):
        # USER 00 is UID 0; so is a name that the image's /etc/passwd maps to 0.
        for image in ("root-padded", "root-by-name"):
            self.assert_fails_with(run_contract(self.images[image]),
                                   "Contract: runs as a non-root user", "Fix: add a numeric USER")

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

    def test_readme_section_names_match_whole_words(self):
        # "report-bot", "Support" and "Independent" contain port and depend but aren't those sections.
        with tempfile.TemporaryDirectory() as context:
            shutil.copy(SAMPLE / ".env.example", context)
            Path(context, "README.md").write_text(
                "# report-bot\n\n## Support\n\n## Volumes\n\n## Independent of others\n\n## Memory\n")
            self.assert_fails_with(run_contract(self.images["sample"], context=Path(context)),
                                   "README.md has no section for: Port, Dependencies.")



if __name__ == "__main__":
    unittest.main()
