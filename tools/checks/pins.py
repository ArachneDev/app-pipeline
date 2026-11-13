"""Fails when a workflow uses an action not pinned by full commit SHA.

A tag can be moved to new code; a commit cannot. Local calls (./...) are
allowed, and Docker actions must be pinned by digest. The file is parsed as
YAML, so flow style ({uses: ...}) is checked too. Usage: python pins.py [repo]
"""

import re
import sys
from pathlib import Path

import yaml

COMMIT = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
DIGEST = re.compile(r"^docker://[^@]+@sha256:[0-9a-f]{64}$")


def uses_refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "uses" and isinstance(value, str):
                yield value.strip()
            else:
                yield from uses_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from uses_refs(item)


def violations(text):
    return [
        ref for ref in uses_refs(yaml.safe_load(text))
        if not (ref.startswith("./") or COMMIT.match(ref) or DIGEST.match(ref))
    ]


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
