# Agent guide: app-pipeline

This repo is the reusable workflow every app calls, so a change here reaches every app at its next run. Usage and inputs are in [README.md](README.md).

| Path | What it is |
|---|---|
| `.github/workflows/build.yml` | The shared workflow apps call: build, scan, publish |
| `.github/workflows/pipeline-sample.yml` | The sample caller. It runs `build.yml` from this commit on every PR |
| `sample/` | `pipeline-sample`, a test image only. Never deployed |
| `tests/`, `tools/checks/` | What `make check` runs |

## Versioning

Apps call `@v1`, a moving major tag. Every release also gets an immutable `vX.Y.Z` tag.

1. Merge to `main`.
2. Tag the merge commit `vX.Y.Z` and push the tag. The sample caller publishes `ghcr.io/arachnedev/pipeline-sample:vX.Y.Z`. Check: that run is green.
3. Move the major tag: `git tag -f v1 <sha> && git push -f origin v1`. Check: `git ls-remote origin v1` shows `<sha>`.

## What is breaking

A breaking change needs a new major tag (`v2`) and a note to every app. Breaking means an app that passed before now fails or publishes somewhere else without changing its own repo:

- Removing or renaming an input or output, or changing a default.
- Changing the image name, the version tag format or the registry.
- Needing a new permission in the caller's `permissions:` block.
- A stricter check that turns existing apps red, unless it closes a security hole. Then ship it in `v1` and tell every app first.

Adding an optional input, fixing a bug, or bumping a pinned tool is not breaking.

## Test a change

1. Run `make check`. It runs the pin check, the tests and gitleaks in a pinned image. Check: it ends with `OK` and `no leaks found`.
2. Open a PR. The `pipeline-sample` job runs the changed `build.yml` end to end, without pushing.
3. A new rule gets a test in `tests/` that goes red on a planted violation.

Every `uses:` is pinned by full commit SHA; `tools/checks/pins.py` enforces it. Downloaded tools are pinned by version and sha256. Keep the gitleaks pin in `build.yml` and `tools/check-image/Containerfile` equal.

## Sources in infra

Point to these; don't copy them here.

- What an image must provide: [blueprint, Container contract](https://github.com/ArachneDev/infra/blob/main/docs/blueprint.md#container-contract).
- How a release flows: [blueprint, Release hand-off](https://github.com/ArachneDev/infra/blob/main/docs/blueprint.md#release-hand-off) and [ADR-006](https://github.com/ArachneDev/infra/blob/main/docs/adr/0006-deployment-model.md).
- The template apps start from: [blueprint, App starter repo](https://github.com/ArachneDev/infra/blob/main/docs/blueprint.md#app-starter-repo).
