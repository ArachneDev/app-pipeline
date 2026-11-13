# app-pipeline

The shared CI workflow every ArachneDev app calls. A version tag builds the app's `Containerfile`, runs it under production hardening, scans it and pushes `ghcr.io/arachnedev/<app>:<tag>`.

## Use it

Put this in the app repo as `.github/workflows/release.yml`:

```yaml
name: release
on:
  pull_request:
  push: {branches: [main], tags: ["v*.*.*"]}
jobs:
  build:
    permissions: {contents: read, packages: write}
    uses: ArachneDev/app-pipeline/.github/workflows/build.yml@v1
```

1. Push a branch or open a pull request. The workflow builds and scans, and pushes nothing.
2. Push a tag such as `v1.4.0`. Check: `ghcr.io/arachnedev/<repo-name>:v1.4.0` exists.

## What it does

| Step | Fails when |
|---|---|
| Build-args check | A `build-args` name looks secret (`TOKEN`, `PASSWORD`, `KEY`...) or gitleaks finds a secret-shaped value |
| gitleaks on every commit reachable from the build | A secret was ever committed there. A `.gitleaks.toml`, `.gitleaksignore` or `gitleaks:allow` in the app repo is ignored |
| `docker build` of the `Containerfile` | The build fails. `VERSION` is passed as a build argument, set to the tag |
| Contract test: runs the image read-only, with no capabilities, `no-new-privileges`, a memory limit, exec tmpfs on `/tmp`, `/var/tmp` and `/run`, `PORT=18080`, `.env.example` as env and a sample `/run/secrets/app.json` | The image runs as root, `.env.example` or a README section (Port, Volumes, Dependencies, Memory) is missing, or `health-path` doesn't answer 2xx with the version within 60 s. Each error names the contract line and the fix |
| Trivy image scan | A critical CVE with a fix available is not listed in `.trivyignore` |
| Push to ghcr.io with `GITHUB_TOKEN` | Only on a version tag `vX.Y.Z` (or `vX.Y.Z-pre`); any other tag fails. Outputs `image` and `digest` |

## Inputs

All optional. Most apps pass none.

| Input | Default | Use |
|---|---|---|
| `app` | Repo name, lowercased | Image name under `ghcr.io/<owner>/` |
| `context` | `.` | Build context |
| `containerfile` | `Containerfile` | Path inside the context |
| `build-args` | Empty | One `KEY=VALUE` per line. Never secrets: the app reads those at run time |
| `trivy-ignore` | `.trivyignore` | One CVE ID per line, each with a comment saying why it is accepted |
| `app-json` | Empty: `{}` | Sample `/run/secrets/app.json` for the contract test, inside the context. Fake values only |
| `health-path` | `/healthz` | Path that must answer 2xx with the build version |
| `memory` | `512m` | Memory limit for the contract test: the measured peak plus 25 to 50 percent |

What an image must provide is the container contract in the infra blueprint: <https://github.com/ArachneDev/infra/blob/main/docs/blueprint.md#container-contract>.
