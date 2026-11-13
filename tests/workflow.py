"""Runs one step of .github/workflows/build.yml by its `id`, so tests and workflow can't drift.

Needs bash, git and gitleaks on PATH (the check image has all three).
"""

import secrets
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
PATH = "/usr/local/bin:/usr/bin:/bin"


def step(step_id):
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    for job in jobs.values():
        for s in job.get("steps", []):
            if s.get("id") == step_id:
                return s
    raise AssertionError(f"no step with id {step_id} in build.yml")


def run_step(step_id, env, cwd=None):
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step(step_id)["run"]],
        env={"PATH": PATH, **env},
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def fake_token():
    # Built at run time so the repo's own gitleaks scan never sees one.
    return "ghp_" + secrets.token_hex(18)
