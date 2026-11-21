# app-pipeline

The shared CI workflow every ArachneDev app calls. A version tag builds the app's `Containerfile`, runs it under production hardening, scans it and pushes `ghcr.io/arachnedev/<app>:<tag>`. With `promote: true` it then moves `:prod` after the owner approves, and moves it back if the release does not come up.

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

## Release channels

Add `promote: true` to move the channel tags `:prod` and `:staging`. The app's repo needs a `production` Environment with the owner as required reviewer first: GitHub creates a missing Environment with no reviewer, and `:prod` would then move unapproved.

```yaml
name: release
on:
  pull_request:
  push: {branches: [main, staging], tags: ["v*.*.*"]}
  workflow_dispatch:
    inputs:
      version: {description: "Earlier version to put back on :prod, such as v1.3.0", required: true}
jobs:
  release:
    permissions: {contents: read, packages: write}
    uses: ArachneDev/app-pipeline/.github/workflows/build.yml@v1
    with:
      promote: true
      production-url: https://app.doublew.nu/healthz
      staging-url: https://staging1.doublew.nu/healthz
    secrets: inherit   # only for a URL behind Cloudflare Access; see below
```

| Trigger | What moves | Approval |
|---|---|---|
| Push of `v1.4.0` | After the build, `:prod` moves to that image's digest with `skopeo copy`, with no rebuild | The `production` Environment's reviewer. Until they approve, nothing moves |
| Run the workflow with a `version` | `:prod` moves to the digest of that earlier version, with no build | The same approval |
| Push to `staging` | The build is pushed as `:sha-<12 chars>`, and `:staging` moves to it | None |

The deployment history of the `production` or `staging` Environment lists each run with a link that names the version.

**Verify and revert.** After the move the job polls the health URL, which must answer 2xx with the version (ADR-006, Phase B):

1. It records the digest the tag pointed at, exactly as the registry serves it, for an image or an index. Check: the log says `Recorded :prod at sha256:...`.
2. It polls every 15 s for `verify-window` seconds. Failures count only after the first half of the window, the start-up allowance (one timer cycle plus start-up), or once the new version has shown.
3. `verify-failures` failed polls in a row move the tag back to the recorded digest, without a new approval, and fail the job with the reason. A shorter blip is ignored.
4. A release that never shows the new version in the window is moved back too. A registry error before the move fails the job and moves nothing.
5. A first release has no earlier digest: the job fails and the tag stays.

An empty URL skips the check, for an app with no port. Change the window together with the host's timer interval and delay in infra, or a good release may be moved back.

**Behind Cloudflare Access.** Set the organization Actions secrets `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` to a read-only service token, and add `secrets: inherit`. The job sends them as headers and never prints them.

One promote job runs per app and channel at a time, and a run waiting for approval counts as running. A newer run waits behind it, so the owner approves or rejects the older one first. A newer run replaces an older one that is only queued, which GitHub shows as cancelled [Local test, newapp-test run 44346932502].

## What it does

| Step | Fails when |
|---|---|
| Build-args check | A `build-args` name looks secret (`TOKEN`, `PASSWORD`, `KEY`...) or gitleaks finds a secret-shaped value |
| gitleaks on every commit reachable from the build | A secret was ever committed there. A `.gitleaks.toml`, `.gitleaksignore` or `gitleaks:allow` in the app repo is ignored |
| `docker build` of the `Containerfile` | The build fails. `VERSION` is passed as a build argument, set to the tag |
| Contract test: runs the image read-only, with no capabilities, `no-new-privileges`, a memory limit, exec tmpfs on `/tmp`, `/var/tmp` and `/run`, `PORT=18080`, `.env.example` as env and a sample `/run/secrets/app.json` | The image's `USER` is not a numeric UID above 0 (a name can map to root), `.env.example` or a README section (Port, Volumes, Dependencies, Memory) is missing, or `health-path` doesn't answer 2xx with the exact version within 60 s. Each error names the contract line and the fix |
| Trivy image scan | A critical CVE with a fix available is not listed in `.trivyignore` |
| Push to ghcr.io with `GITHUB_TOKEN` | Only on a version tag `vX.Y.Z` (or `vX.Y.Z-pre`), or on a `staging` push with `promote: true`. Any other tag fails. A version tag that already exists fails and is never overwritten. Outputs `image` and `digest` |

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
| `memory` | `512m` | Memory limit for the contract test: the measured peak plus 25 to 50 percent. A number above 0 with a unit: `k`, `m` or `g` |
| `promote` | `false` | Move `:prod` and `:staging` as in Release channels |
| `production-url`, `staging-url` | Empty: no check | Health URL polled after `:prod` or `:staging` moves |
| `verify-window` | `900` | Seconds to poll: 2 timer intervals (300 s plus up to 30 s delay) plus start-up, rounded up. The first half is one interval plus delay plus 120 s of start-up |
| `verify-failures` | `3` | Failed polls in a row that move the tag back |

The secrets `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` are optional.

What an image must provide is the container contract, copied in app-starter's `AGENTS.md`: <https://github.com/ArachneDev/app-starter/blob/main/AGENTS.md>.
