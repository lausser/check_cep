# Releasing check_cep

## Versioning policy

check_cep uses [Semantic Versioning](https://semver.org/) `MAJOR.MINOR.PATCH`,
optionally with a release-candidate suffix `-rc.N`. Tags carry no prefix:
`0.24.0`, not `v0.24.0`. The old tags `0.6 0.7 0.8 0.10 0.12` predate this
scheme and stay as they are.

| Change | Version | Example |
|---|---|---|
| A finished spec (convention: minor = spec number while in 0.x) | minor | spec 024 → `0.24.0` |
| Fixes, dependency bumps such as a Playwright upgrade | patch | `0.24.1` |
| Pre-release for testing a publish | rc | `0.25.0-rc.1` (sorts before `0.25.0`) |

`1.0.0` is cut when the plugin CLI, the container I/O contract and the
image tags are declared stable; until then a minor release may contain
breaking changes, which CHANGES.md lists under **Breaking**.

## Where versions live

| File | Content | Maintained by |
|---|---|---|
| `VERSION` | the release version, canonical | `scripts/release.py` |
| `src/check_cep` | `CEP_VERSION = "X.Y.Z"` (the plugin is installed as a standalone file) | stamped by `scripts/release.py` — do not edit |
| `src/container/versions.env` | `PLAYWRIGHT_VERSION`, `PLAYWRIGHT_BASE_DIGEST` | by hand (Playwright upgrade) |
| `src/container/package.json` / `package-lock.json` | exact `@playwright/test` pin / derived lock | by hand / `make package-lock` |
| `CHANGES.md` | one chapter per release, `## X.Y.Z — YYYY-MM-DD — …` | by hand, dated by `scripts/release.py` |

`python3 scripts/check-versions.py` (run before every `make image*` and in CI)
fails when these disagree.

Builds of `main` between releases keep the last `VERSION`; they are told
apart only by the `org.opencontainers.image.revision` label (`-dirty` for a
local build from an unclean tree). There is no `-dev` suffix, and such builds
are never published under a release tag.

## What is automated

| Step | Who / what |
|---|---|
| Date the CHANGES heading, write `VERSION`, stamp `CEP_VERSION`, commit `chore(release): X.Y.Z`, annotated tag | `scripts/release.py prepare` (local, never pushes) |
| Push `main` and the tag | maintainer |
| Version checks, unit tests, image build on every PR and `main` push | `.github/workflows/image.yml`, job `test` (read-only) |
| Image push to `ghcr.io/lausser/check_cep`, floating tags, GitHub Release | workflow jobs `gate` + `publish`, only for tags matching `^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-rc\.(0|[1-9][0-9]*))?$` |
| Make the package public (first publish only), acceptance checks | maintainer |

## Release procedure

```bash
git checkout main                                   # clean tree, everything merged
python3 scripts/release.py prepare --dry-run        # proposes 0.<spec>.0 from CHANGES.md, checks everything
python3 scripts/release.py prepare 0.24.0           # commit + annotated tag, prints the push command
python3 scripts/release.py notes 0.24.0             # the release notes the workflow will publish
```

`prepare` aborts without changing anything when the tree is dirty, the branch
is not `main`, the tag exists, the version is invalid or not greater than
`VERSION`, or CHANGES.md has no matching chapter:

- spec release `X.Y.0`: a chapter `## Spec 0YY — Title` (becomes
  `## X.Y.0 — <date> — Spec 0YY — Title`)
- any other release: a chapter `## X.Y.Z — Unreleased — Title` (date filled in)
- a final `X.Y.0` after `X.Y.0-rc.N`: the rc heading is re-dated to `X.Y.0`

`python3 scripts/release.py aliases X.Y.Z` prints the image tags a publish
may set (used by the workflow). `X.Y.Z` and `X.Y.Z-pwP.Q.R` are immutable;
`X.Y` and `latest` are set only for a final release that is the highest
final release of its minor line / overall — they never move backwards, so
publishing `0.23.2` after `0.24.0` moves `0.23` but not `latest`.

## Release checklist (maintainer)

1. `main` is clean and contains everything for the release.
2. `make test-all` passes; any failure must already be in the recorded
   baseline of the previous release (currently none).
3. `python3 scripts/release.py prepare X.Y.Z`.
4. `git push origin main`
5. Wait for the `main` workflow run of the release commit to succeed:
   `gh run list --branch main --limit 5 --json headSha,conclusion,status`
   — its `headSha` must equal `git rev-parse X.Y.Z^{commit}`.
6. `git push origin X.Y.Z` — note the time.
7. The tag workflow run is green (`gh run watch`).
8. First publish only: GitHub → Packages → `check_cep` → Package settings →
   change visibility to **Public**.
9. Anonymous pull by tag and by digest:
   ```bash
   podman logout ghcr.io 2>/dev/null
   podman pull ghcr.io/lausser/check_cep:X.Y.Z
   podman pull ghcr.io/lausser/check_cep@$(podman image inspect ghcr.io/lausser/check_cep:X.Y.Z --format '{{.Digest}}')
   ```
10. All tags of the release resolve to one digest — for a final release
    `X.Y.Z X.Y.Z-pwP.Q.R` plus whatever `release.py aliases X.Y.Z` printed
    (`X.Y`, `latest`); for an rc only `X.Y.Z-rc.N X.Y.Z-rc.N-pwP.Q.R`:
    `for t in <tags>; do podman pull -q ghcr.io/lausser/check_cep:$t >/dev/null; podman image inspect ghcr.io/lausser/check_cep:$t --format "$t {{.Digest}}"; done`
11. `gh release view X.Y.Z` shows the same text as `python3 scripts/release.py notes X.Y.Z`.
12. The time from the tag push (step 6) to the successful anonymous pull
    (step 9) is below 30 minutes (SC-003); note it in the release.

A failed publish can be re-run from the Actions UI: an existing `X.Y.Z` with
the expected labels is not rebuilt; a missing `X.Y.Z-pwP.Q.R` is created
(an existing one is verified, never rewritten), eligible floating tags
(`X.Y`, `latest`; never for an rc) are moved, and the release is created if
absent. An existing tag with a different revision or
digest fails the run and changes nothing. Make the immutability of `X.Y.Z`
explicit in the package settings as well; the workflow check is the
guarantee, the registry settings are an additional control.

## Upgrading Playwright

A Playwright upgrade is a patch release.

1. Resolve the multi-arch index digest of the new base image (the
   `Docker-Content-Digest` of the manifest list):
   ```bash
   curl -sSI \
     -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
     https://mcr.microsoft.com/v2/playwright/manifests/v1.64.0-noble | grep -i docker-content-digest
   ```
   (`podman manifest inspect` prints a re-serialized manifest; its sha256 is
   not the digest.)
2. Set `PLAYWRIGHT_VERSION` and `PLAYWRIGHT_BASE_DIGEST` in
   `src/container/versions.env`.
3. Set `"@playwright/test": "<version>"` (exact) in `src/container/package.json`,
   then `make package-lock`.
4. `python3 scripts/check-versions.py` → exit 0.
5. `make test-all` and compare with the baseline of the previous version.
6. Add `## X.Y.Z — Unreleased — Playwright vP.Q.R` to CHANGES.md, merge,
   release as above.

## Bootstrap: 0.23.0

`0.23.0` marks spec 023 (`a6080c8`) retroactively. It is an annotated tag
only: no GitHub Release and no image (that commit has no workflow). The
first published release is `0.24.0`. Pushing the tag is optional
(`git push origin 0.23.0`); it does not trigger a build.

## Validating the workflow locally

```bash
podman run --rm -v "$PWD:/repo:ro,z" -w /repo docker.io/rhysd/actionlint:1.7.12 -color
pytest tests/unit/test_workflow.py -q
```

## Optional: spex `after_finish` hook

`.specify/extensions.yml` is local (git-excluded). spex hooks can only name
speckit commands and there is no release command, so the reminder is an
*optional* hook: spex displays its prompt after `/speckit-spex-finish` and
runs nothing by itself (the named command is the harmless quick reference).
Append to the existing `after_finish:` list:

```yaml
  - extension: local
    command: speckit.spex.help
    enabled: true
    optional: true
    priority: 20
    prompt: "Spec merged to main. Cut the release: python3 scripts/release.py prepare --dry-run (RELEASING.md)"
    description: Release reminder (RELEASING.md)
    condition: null
```
