"""Fails when a workflow uses an action not pinned by full commit SHA.

A tag can be moved to new code; a commit cannot. Local calls (./...) are
allowed, and Docker actions must be pinned by digest. Usage: python pins.py [repo]
"""

import re
import sys
from pathlib import Path

USES = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^'\"\s#]+)", re.MULTILINE)
COMMIT = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
DIGEST = re.compile(r"^docker://[^@]+@sha256:[0-9a-f]{64}$")


def violations(text):
    found = []
    for ref in USES.findall(text):
        if ref.startswith("./") or COMMIT.match(ref) or DIGEST.match(ref):
            continue
        found.append(ref)
    return found


def repo_violations(root):
    found = []
    for path in sorted((Path(root) / ".github" / "workflows").glob("*.y*ml")):
        found += [f"{path.relative_to(root)}: {ref}" for ref in violations(path.read_text())]
    return found


if __name__ == "__main__":
    bad = repo_violations(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    for line in bad:
        print(f"not pinned by commit or digest: {line}")
    sys.exit(1 if bad else 0)
