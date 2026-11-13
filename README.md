# app-pipeline

The shared CI workflow every ArachneDev app calls. A version tag builds the app's `Containerfile`, scans it and pushes `ghcr.io/arachnedev/<app>:<tag>`.

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
| gitleaks on the full git history | A secret was ever committed |
| `docker build` of the `Containerfile` | The build fails. `VERSION` is passed as a build argument, set to the tag |
| Trivy image scan | A critical CVE with a fix available is not listed in `.trivyignore` |
| Push to ghcr.io with `GITHUB_TOKEN` | Only on a tag. Outputs `image` and `digest` |

## Inputs

All optional. Most apps pass none.

| Input | Default | Use |
|---|---|---|
| `app` | Repo name, lowercased | Image name under `ghcr.io/<owner>/` |
| `context` | `.` | Build context |
| `containerfile` | `Containerfile` | Path inside the context |
| `build-args` | Empty | One `KEY=VALUE` per line. Never secrets: the app reads those at run time |
| `trivy-ignore` | `.trivyignore` | One CVE ID per line, each with a comment saying why it is accepted |

What an image must provide is the container contract in the infra blueprint: <https://github.com/ArachneDev/infra/blob/main/docs/blueprint.md#container-contract>.
