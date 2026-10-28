# Changes

Each section corresponds to a completed specification (spec). Specs are
the unit of release — when a spec is finished and merged, it becomes
available in the next container image build.

From 0.23.0 on, each release has a versioned heading
(`## X.Y.Z — YYYY-MM-DD — …`); see RELEASING.md.

---

## 0.24.1 — 2026-10-28 — Playwright v1.64.0

### Changed

- Playwright 1.60.0 → 1.64.0: base image
  `mcr.microsoft.com/playwright:v1.64.0-noble` pinned by its index digest
  `sha256:06a9939e57531807f8d5fd76ce44b53165ffb7d7501d87ab10e285c20b1e971f`;
  `@playwright/test` 1.64.0 (lockfile regenerated; Playwright now requires
  Node ≥ 20 and drops its optional macOS `fsevents` dependency).
- Image tag alias becomes `0.24.1-pw1.64.0`; `0.24` and `latest` move to
  0.24.1, `0.24.0` is unchanged.
- `0.23.0` remains a tag only, without a GitHub Release (RELEASING.md).

### Verification

- `make test-all` on 1.64.0: 120 passed, 12 skipped, 1 xfailed, 0 failed —
  identical to the 1.60.0 baseline (same skipped/xfailed tests), including
  the Lightpanda/CDP lane and the spectate/slowMo/VNC tests.

---

## 0.24.0 — 2026-10-28 — Spec 024 — Professional Versioning and Image Publishing

**Branch**: `024-versioning-image-publishing`

### Summary

check_cep gets a release identity and a publish path. `VERSION` (SemVer,
canonical) is stamped into the plugin as `CEP_VERSION`; `check_cep
--version` prints `check_cep X.Y.Z`. Images carry OCI labels and report
their version; every run records plugin, image and Playwright version in
`test-meta.json`. `scripts/release.py` cuts a release locally (dated
CHANGES heading, release commit, annotated tag); pushing the tag publishes
the image to `ghcr.io/lausser/check_cep` and creates a GitHub Release.
Procedure and checklist: RELEASING.md.

### Added

- `VERSION` file and `CEP_VERSION` in `src/check_cep`; `--version`.
- Image labels `org.opencontainers.image.{version,revision,source,created,title}`
  and `io.consol.check_cep.playwright.version`; image ENV `CEP_IMAGE_VERSION`.
- `test-meta.json` key `versions` (`plugin`, `image`, `playwright`; each
  `"unknown"` when not determinable, e.g. with an older image).
- The plugin passes `CEP_PLUGIN_VERSION` into every container; with
  `--debug` a plugin/image difference is logged as
  `version mismatch: plugin X, image Y`. The check result never changes.
- `src/container/versions.env`: single source of the Playwright version
  and the base-image digest (`mcr.microsoft.com/playwright:v1.60.0-noble`
  pinned by its index digest). `package.json` pins `@playwright/test`
  exactly; `scripts/check-versions.py` fails every `make image*` target
  and CI when the sources disagree, and the build asserts the bundled
  Playwright version.
- `scripts/release.py prepare | notes | aliases`.
- `.github/workflows/image.yml`: PRs and `main` pushes run version checks,
  unit tests and an image build; release tags `X.Y.Z[-rc.N]` publish
  `X.Y.Z`, `X.Y.Z-pwP.Q.R` (immutable) and, for final releases, `X.Y` and
  `latest` (never moved backwards), linux/amd64.
- README "Installing from ghcr.io" (pinning recommendations), RELEASING.md.
- `make image` also tags `localhost/check_cep:<VERSION>`.

### Changed

- Lightpanda browser binary 0.3.4 → 1.0.2. The Lightpanda lane fixture
  `tc_lp_pass` now asserts the stable IANA link on example.com instead of
  the page's `h1`/paragraph text, which made it fail on the live site.

### Breaking

- `podman build` of `src/container` requires the build-args
  `PLAYWRIGHT_VERSION`, `PLAYWRIGHT_BASE_DIGEST`, `CEP_VERSION`, `VCS_REF`
  and `BUILD_DATE` (no defaults). Use `make image`, or see README §1.
- `PLAYWRIGHT_VERSION` (Makefile variable and image ENV) changes format
  from `v1.60.0` to `1.60.0`; it is no longer overridable on the `make`
  command line — edit `src/container/versions.env`. Local image tags keep
  the `v` (`localhost/check_cep:v1.60.0`).
- `CEP_PLUGIN_VERSION` is a new reserved name; `--environ
  CEP_PLUGIN_VERSION=…` is rejected with UNKNOWN.

---

## 0.23.0 — 2026-10-27 — Spec 023 — Layered Test Artifacts, Playwright Project Layout and Secret Injection

**Branch**: `023-layered-artifacts-secrets`

### Summary

Three capabilities and one policy fix. (1) **Secrets**: `--environ
NAME[=VALUE]` works in every mode; values reach the container without
appearing on any podman command line or in `--debug` output and are masked
as `***` in the Nagios output; plugin credentials get the same treatment.
(2) **Layers**: `--test-artifact` is repeatable; local directories and
`.tgz` archives are mounted read-only and merged in order into a writable
per-run test tree. (3) **Run modes**: a Playwright config at the top of the
merged tree runs the project as-is (project-root mode, incl. `*.spec.ts`,
setup projects, `tsconfig` aliases); otherwise the previous discovery
applies. (4) **Exit-status classification**: CRITICAL now means only "the
Playwright tests reported a failure"; infrastructure problems are UNKNOWN.

### Deliberately changed behavior

Review these before upgrading:

1. `--environ` is active in all modes (scheduled, `--shell`, `--headed`,
   `--vnc`, `--authoring`); the "only takes effect with --authoring" warning
   is gone.
2. `--environ` values and plugin credentials are masked as `***` in the
   status line and long output (every occurrence — use distinctive values).
3. Reserved names (`TEST_SOURCE`, `PWTIMEOUT`, `CEP_SLOW_MO`, `NAGIOS_*`,
   `AWS_*`, … — see README) are rejected with UNKNOWN.
4. **Breaking**: host proxy variables (`http_proxy`, `https_proxy`,
   `ftp_proxy`, `no_proxy`, either case) are no longer forwarded implicitly;
   every `podman run` gets `--http-proxy=false --env-host=false`. Migration:
   - application under test (browser, `request` fixture): `use.proxy` in
     `playwright.config.ts`, ideally in a shared or probe-specific layer;
   - S3 and own `fetch` calls: `--environ HTTPS_PROXY --environ NO_PROXY`.
   See README → *Container environment*.
5. `/home/pwuser/tests` is a writable per-run copy built inside the
   container; sources are mounted read-only under `/home/pwuser/layers/`.
   The `/home/pwuser/input-artifact.tgz` mount is gone.
6. Discovery picks the byte-wise first directory with test files and warns
   (stderr) about the others; previously the first one found by `os.walk`.
7. Project-root mode: a tree with a top-level Playwright config whose tests
   previously ran from a subdirectory now runs from the top with that config.
8. `--shell` (without `--authoring`) shows the merged tree, including
   extracted `.tgz` layers; a merge error exits 3 without a shell.
9. Acquisition (extraction, merge, S3 download) counts toward `--timeout`;
   Playwright gets the remainder.
10. Acquisition, merge and "no tests" failures are UNKNOWN (previously
    CRITICAL "failed"); a missing local test directory is UNKNOWN before the
    container starts (previously a podman mount error → CRITICAL).
11. **Exit-status classification**: OOM kills, podman failures (exit
    125/126/127, including registry authentication), container exit 3 and
    unexpected exit codes are UNKNOWN instead of CRITICAL. CRITICAL is
    reported only when Playwright reported a failure or timed out — check
    your notification routing for UNKNOWN.
12. A passed run whose report contains Playwright `errors` entries (report
    root or a test's first result) is CRITICAL.
13. A test can signal WARNING by writing visible text to stderr or by
    exiting 150; Playwright's empty stderr chunks no longer cause a false
    WARNING, and base64 `buffer` stdout/stderr chunks are decoded instead of
    dropped.

### Added

- `src/container/image/plugins/_layers.py`: safe archive extraction
  (`tarfile` "data" filter, member by member, deadline-aware, absolute
  member names rejected) and a two-phase merge (validate everything, then
  copy): type conflicts, special files and escaping symlinks are errors
  naming `layer #N (<host path>)`.
- `src/check_cep`: `Layer`, `resolve_layers()`/`select_layers()` (`%h`/`%s`
  expansion, validation before any container starts), `RESERVED_ENV_*`,
  `display_forwarding()`, masking (`set_mask_values`, `mask_secrets`,
  `MaskingFilter`), `ContainerOutcome` + `classify_result()`,
  `ensure_unique_labels()`.
- `src/container/image/run.py`: `prepare()` → `RunMode` (project-root /
  discovery), `--prepare-only`, the `CEPUNKNOWN [[[reason]]]` marker,
  `normalize_exit()`, crash boundary `run_guarded()`, spectate wrapper next
  to the active config, `layers` in `test-meta.json`.

### Migration notes

- Scripts that inspected `/home/pwuser/input-artifact.tgz` or expected
  `/home/pwuser/tests` to be the read-only source mount must use the merged
  tree instead.
- WRITING-TESTS renames "Pattern A/B" to "Nested layout"/"Flat layout"
  (discovery mode) and adds project-root mode.

### Verification status

- Unit tests: 289 passed (58 before this spec): every `classify_result()`
  branch plus a property test over all exit codes, the merge/extract helper,
  reserved names, bare-argv invariant, masking, run modes, label rules.
- `make test-all` (local + S3/MinIO + Loki): 119 passed, 12 skipped,
  1 xfailed, 1 failed. The failure, `test_local_lightpanda[tc_lp_pass]`
  (Lightpanda finds no `h1` on https://example.com), fails identically on
  the pre-spec baseline and is unrelated.
- Verified end to end: secrets reach the test in every form and never appear
  in the podman argv (also sampled with `ps` during a run), `--debug` or the
  Nagios output; the container environment equals image `ENV` + podman's own
  variables + check_cep's + `--environ` names (no proxies, no unnamed host
  variables); single-layer parity with the pre-spec release (status line,
  exit code, perfdata labels); layered nested and project-root checks equal
  their hand-merged single directory; setup projects with `storageState`;
  slowMo takes effect headless and via VNC in both run modes; `--shell`
  builds the merged tree.
- SC-008: 50 MB single layer, median of 5 runs: 2.97 s before, 3.01 s after
  (+0.04 s).
- Code review with a second agent (OpenCode/GPT-5.6): fixed duplicate-label
  suffix collisions, a missing deadline check while planning the merge, and
  validation of the layer handoff; kept `extractall()`-compatible reverse
  directory order and the integer acquisition-time deduction.
- Verified by hand on the desktop (Wayland and VNC): spectate with visible
  slowMo and vision highlights, and an interactive `--shell` on a merged
  directory + `.tgz` tree.
- Walkthrough fixes: an UNKNOWN that ends the run before Playwright no longer
  reports the previous run's perfdata and output (a `steps.json` older than
  the run is ignored) or the raw `CEPUNKNOWN` marker as long output.

---

## Spec 022 — OpenCode CLI as Default AI Authoring Backend

**Branch**: `022-opencode-authoring`

### Summary

Replaces `@google/gemini-cli` with the opencode CLI (`opencode-ai` npm
package) as the AI backend driving the spec-020 authoring workflow
(PREFLIGHT → AUTHOR → RUN → CRITIC → GATE → PACKAGE), defaulting to the free
Zen model `opencode/big-pickle`. Gemini stays available as an *opencode
provider connection* (`google/…` model + `GEMINI_API_KEY`) instead of a
second CLI — the gemini CLI is removed from the image entirely. The default
path is **keyless**: free Zen models need no credential and no billing. The
generic `--environ NAME[=VALUE]` replaces the removed `--gemini-api-key`.
Because a keyless default can't be gated on credential presence, the live
eval is now gated by the explicit `CEP_AI_EVAL=1` opt-in; the "no AI
credential on scheduled runs" guarantee is preserved and extended to both
`OPENCODE_API_KEY` and `GEMINI_API_KEY`.

### Verification status

**This is the first time spec 021's 12-case eval has ever completed live, on
any backend.** Full result: **12/12 pass** — all 9 positive cases (SC-001,
SC-003) and all 3 adversarial cases (SC-002), the latter never previously
executed live at all. SC-004 (clean GATE within `CEP_MAX_ITERATIONS`, not the
900 s harness timeout), SC-005 (metrics record `model` and plausible
turn/wall values), SC-006 (fast suite green with `CEP_AI_EVAL` unset, all 12
cases skip), SC-007 (scheduled runs carry neither `OPENCODE_API_KEY` nor
`GEMINI_API_KEY`, verified against a real container), and SC-008 (the Gemini
connection works end-to-end and records the google model id) are all
confirmed by real runs, not just unit tests.

### Changed

- `Makefile`: `OPENCODE_VERSION ?= 1.18.4` replaces `GEMINI_CLI_VERSION`.
- `src/container/Dockerfile` (`ai` stage): installs `opencode-ai` instead of
  `@google/gemini-cli`; bakes `/home/pwuser/.config/opencode/opencode.json`
  (default model, workspace-scoped permissions, the `chrome-devtools` MCP
  server, a read-only `critic` agent) instead of `.gemini/settings.json`;
  third-party + local skills now live under `/home/pwuser/.agents/skills/`
  only — opencode discovers them natively, so the `.gemini/skills` symlink
  wiring is gone entirely.
- `src/container/image/cep_authoring`: `AUTHOR` and `CRITIC` now invoke
  `opencode run` (with a read-only `--agent critic`) instead of `gemini -p`;
  `MODEL` defaults to `OPENCODE_MODEL:-opencode/big-pickle`; PREFLIGHT no
  longer requires a credential unconditionally — it fails fast only when the
  selected model is `google/…` and `GEMINI_API_KEY` is unset.
- `src/check_cep`: `--gemini-api-key` removed; replaced by repeatable
  `--environ NAME[=VALUE]` (bare `NAME` forwards the host env var's current
  value so it never appears on the podman command line). `--environ` is
  inert outside `--authoring` (warns, injects nothing). `--opencode-config
  FILE` bind-mounts a providers/models overlay at
  `/home/pwuser/.config/opencode/providers.json` and sets `OPENCODE_CONFIG`
  so opencode merges it over the baked image config (MCP/critic/permissions
  stay); authoring-only, missing file is exit 3.
- `tests/integration/conftest.py`, `authoring_eval_support.py`,
  `test_authoring_eval.py`: eval gate re-keyed from `requires_gemini_key`
  (credential presence) to `requires_ai_eval` (`CEP_AI_EVAL=1`); a detected
  quota/rate-limit event now **fails** the run immediately (no retry, no
  skip/spread across days) — `CEP_EVAL_RETRIES` removed as dead code.
- `.agents/skills/cep-test-authoring/SKILL.md`, `WRITING-TESTS.md`,
  `tests/authoring-eval/README.md`: tool-name/CLI/env-var references updated
  (opencode, keyless default, `--environ`, `CEP_AI_EVAL`); no semantic
  guidance change (021 freeze).

### Fixed

Six real bugs surfaced by this feature's live runs — the first time any of
this code path had ever executed to completion:

- **AUTHOR never returned.** After finishing its work, opencode's agent tried
  to invoke `cep_package` itself (correct guidance for a *supervised* session,
  per the skill) and — denied by workspace containment — kept probing
  alternate approaches instead of stopping, burning the full 900 s harness
  timeout with nothing to show for it. Fixed with an explicit instruction in
  the `AUTHOR` prompt (`cep_authoring`) to stop once `VERIFICATION.md` is
  written and never touch anything outside the workspace.
- **`cep_package` silent failure on intents with no `@`-references**
  (pre-existing, predates spec 022 — confirmed via `git log`/`git show HEAD`,
  never previously exercised by a live run on any backend): `grep -oE` exits 1 on
  no matches, and under `pipefail`+`set -e` that silently killed the
  packaging script before the archive was ever built, even after GATE had
  passed. Fixed with `|| true` on the affected pipeline.
- **Hardcoded credential fallback.** The AUTHOR wrote `?? 'Passw0rd!'` as a
  fallback default (reasoning the sample app's own visible demo credentials
  made it "safe"), and the critic non-deterministically approved it twice
  running. Fixed with an explicit anti-hardcoded-fallback instruction in the
  `AUTHOR` prompt, even for values that also appear as public demo defaults.
- **`no_secret_leak()` false positive** in the eval harness: the check
  flagged the intent file (`*.ai` — our own golden fixture, packaged verbatim
  by `cep_package`'s contract) and `VERIFICATION.md`/`KNOWLEDGE.md`
  (documentation) for prose-mentioning the known demo credential. Fixed in
  `authoring_eval_support.py` to scan only real source/config files.
- **`run_packaged_test` didn't mirror the authoring workspace layout.**
  `cep_package`'s contract never bundles sibling fixture folders (real
  deployments target live URLs, not local `file://` pages), so any
  `file://`-based golden case lost its `journey`/`probes` folders when the
  extracted package was re-run standalone. Fixed `extract_and_run` to copy
  those siblings alongside the extracted package before running it.
- **opencode's google provider reads `GOOGLE_GENERATIVE_AI_API_KEY`, not
  `GEMINI_API_KEY`** — a wrong assumption in the original contract/plan,
  never live-tested before this feature (US4). Fixed by bridging the
  documented `--environ GEMINI_API_KEY` interface internally in
  `cep_authoring`'s PREFLIGHT (`export
  GOOGLE_GENERATIVE_AI_API_KEY="$GEMINI_API_KEY"`) — no external contract
  change.

Also fixed in passing: `tests/unit/conftest.py`'s shared `make_config()` test
factory was missing the `authoring`/(now `environ`) `RunConfig` fields
entirely — a pre-existing, unrelated bug (predates spec 022) that broke
`test_run_context.py`/`test_cleanup.py` outright whenever anyone tried to use
it; fixed alongside the field rename since it blocked verifying this spec's
own fast-suite baseline.

### Risk / rollback

The AI image is the only thing that changes (base/scheduled image is
untouched). Rollback: retag the previous `ai` image build, or `git revert`
this branch's commits to restore the gemini-CLI path — no data migration, no
schema changes, nothing to undo on already-deployed scheduled checks.

---

## Spec 021 — AI Test-Authoring Hardening

**Branch**: `021-ai-test-hardening`

### Summary

Proves — and keeps proving — that the spec-020 authoring workflow reliably
produces *good*, deterministic tests for *hard*, realistic pages. Purely
additive: no host-plugin execution path, container I/O contract, or
deployed-check behaviour changes.

### Verification status (read before relying on SC-002)

**The full gated eval has NOT been run to completion — there is no sufficient
model-token budget available.** What is and is not verified:

- **Verified (offline, no AI, reproducible):** the sample app (10/10 smoke
  tests), all 9 golden ideal tests, the `GEMINI_API_KEY` gating in both
  directions (12/12 cases skip with the key unset; suite green), intent
  PREFLIGHT for all 12 intents, and the `cep_authoring` orchestrator tests.
- **Verified (live, with AI):** the workflow explored the journey site and
  authored a good deterministic test into the correct workspace on iteration 1 —
  business-named steps, role-based locators for the non-obvious navigation,
  stable values asserted, the requested balance emitted as perfdata, the dynamic
  "Last login" deliberately *not* asserted — plus `KNOWLEDGE.md` and
  `VERIFICATION.md`. The shipped skill exemplars were demonstrably read and used.
- **NOT verified:** the complete positive-path property set (SC-002) and the
  adversarial cases (SC-003). No package was produced end-to-end, because a run
  exhausts the free-tier cap (`generate_content_free_tier_input_token_count`,
  250 000/day) during exploration — even a clean, single-iteration run. This is a
  **budget** limit, not a known defect: the two bugs that previously caused
  runaway iteration were found and fixed (see *Fixed*).

To complete verification, supply a paid key (or a cheaper provider) and run
`pytest -m authoring_eval tests/integration/test_authoring_eval.py -v`. The
harness classifies quota exhaustion as a `skip`, so it never reports a false
regression when the budget runs out.

### Added

- **Deterministic sample app** under `tests/authoring-eval/sample-app/`: a
  realistic, distraction-rich multi-page fake-bank **journey site**
  (landing → non-obvious "Online Banking" entry → interstitial → login →
  dashboard, no login form on the landing page) plus eight isolated
  single-difficulty **probe routes** (consent-first-visit, ambiguous-elements,
  no-stable-locator, stable-vs-dynamic, async-loading, responsive-breakpoint,
  iframe, moving-element). Served via `file://` (relative links); the iframe
  probe is the one HTTP-served exception. A hard-case catalogue maps each
  difficulty → route → 020 FR guarded → golden pair.
- **Golden intent→test pairs** in `tests/authoring-eval/golden/<Capability>/`
  (flagship `MultiPageJourney` + one per probe): a human-written `intent.ai`,
  the *ideal* deterministic Playwright test, config, functions, and
  `VERIFICATION.md`. Every ideal test passes deterministically offline. The
  best two (flagship + `StableVsDynamic`) ship as skill few-shot **exemplars**
  under `.agents/skills/cep-test-authoring/examples/`, referenced from
  `SKILL.md`.
- **Gated behavioural eval** (`tests/integration/test_authoring_eval.py` +
  `authoring_eval_support.py`): runs the real `cep_authoring` against the
  sample app and asserts capability *outcomes* — package produced, ≥2
  deterministic passes, critic pass, requested values emitted as perfdata, no
  secret outside `.env`, `VERIFICATION.md` complete, and a per-capability
  behavioural signal — **never** the generated source text (SC-008). Gated
  **solely on the presence of `GEMINI_API_KEY`** (plus an AI-image skipif); the
  `authoring_eval` marker is for selection only.
- **Adversarial cases** (incoherent / unsatisfiable / nondeterministic intents):
  assert the workflow refuses or flags the conflict and never fabricates a
  passing test (SC-003).

### Changed

- `src/container/image/cep_authoring`: additive per-run **metrics** record
  (`<TestName>-metrics.json`: iterations, model turns, wall seconds, outcome,
  pinned model) written at STOP/PACKAGE; an optional **slow-motion** verification
  RUN wrapper (`CEP_SLOW_MO` + `HEADED=1`, mirrors `run.py`) that never touches
  the packaged test's config; model pin recorded (`gemini-3.1-flash-lite`).
- `tests/integration/conftest.py`: registers the `authoring_eval` marker and the
  reusable `requires_gemini_key` / `requires_ai_image` skips.

### Fixed

- **`cep_authoring` authored into the wrong directory** (found by this spec's eval
  on its first real run). The AUTHOR prompt passed a *relative* folder
  (`$TESTNAME/`), but the model inherits the orchestrator's cwd — `/home/pwuser`
  when launched as `podman run … cep_authoring`, not the workspace mount
  `/home/pwuser/tests`. The AI therefore wrote a complete, good test to the
  ephemeral container filesystem while `$TESTDIR` stayed empty, so the RUN phase
  found no tests, never reached a clean-run streak, and burned every iteration
  without producing a package. Fixed by running gemini from `$WORKSPACE` and
  passing **absolute** paths (plus naming the workspace root in the prompt); the
  `cd` also makes gemini's own sandbox reject stray writes instead of silently
  accepting them.
- **`cep_authoring` failed silently on an unwritable workspace.** `mkdir -p
  "$TESTDIR"` was unchecked, so a mount the container user cannot write (the
  usual rootless-podman uid mismatch) surfaced as "no clean runs" after burning
  the whole iteration budget. It now fails fast with an actionable message and
  aborts the loop instead of retrying an unfixable condition.
- Eval harness: mounts the workspace with
  `--userns=keep-id:uid=1001,gid=1001` + `--security-opt label=disable`,
  mirroring `check_cep`'s own `--authoring` flags, so the in-container user can
  actually write to it.
- Eval harness: a hung `cep_authoring` now reports as a classified `timeout`
  failure instead of an opaque harness error (and as `quota_error` — a skip —
  when the stall is model-quota backoff), and the named container is
  force-removed (killing the `podman` CLI otherwise leaves it running).

---

## Spec 020 — AI-Assisted Test Authoring

**Branch**: `020-ai-test-authoring`

### Summary

Added an AI-assisted **authoring** workflow that turns a non-technical user's
plain-language intent file (`*.ai`) into a deterministic, deployable
`check_cep` Playwright test — with **no AI at run time**. An admin enters a
new `check_cep --authoring` mode (a bash shell in the `ai` image with the
site-level workspace mounted read-write and `GEMINI_API_KEY` injected); the
new `cep-test-authoring` skill guides Gemini to explore the site, author the
test reusing the sanctioned robustness patterns, and record findings in a
per-site `KNOWLEDGE.md`. A quality gate (immutable success criteria by
marker-line convention, an independent critic pass in a fresh Gemini process,
a scorable checklist, ≥2 consecutive clean runs) guards against
assertion-weakening. Packaging is a shared `cep_package` tool; an optional
`cep_authoring` orchestrator runs the whole loop unattended with a hard
iteration cap. **The scheduled execution path is byte-identical to before** —
every change is additive and gated behind `--authoring`.

### Host plugin (`src/check_cep`)

Two additive CLI arguments and conditional mount/env logic:

- `--authoring` (default off) — implies shell semantics; mounts the
  **site-level** tests dir (`.../tests/%h`) **read-write** (vs the read-only
  service-level mount) and injects `GEMINI_API_KEY`. Refuses (exit 3,
  actionable message) when combined with `--test-source s3` or when the
  workspace directory does not exist. With no resolvable key it still starts,
  printing a visible "AI assistant will not be functional" warning.
- `--gemini-api-key <key>` — follows the existing credential-argument pattern
  (`--aws-access-key-id`, `--loki-password`); resolution order arg → host
  `GEMINI_API_KEY` → absent. Injected into the container **only** in
  authoring mode (FR-020) — never on scheduled runs or plain `--shell`.

### Container / AI image (`ai` stage only)

- `chrome-devtools-mcp` (pinned `1.5.0`) added to `AI_NODE_PACKAGES` and
  registered as a Gemini MCP server (Option A: spawns the Playwright Chrome
  headless/isolated with `--no-sandbox`/`--disable-dev-shm-usage` for rootless
  Podman). Exploration is two-tool: chrome-devtools-mcp **discovers**
  candidates, `@playwright/cli` **confirms** the Playwright locator. All
  existing AI tooling (`@playwright/cli`, playwright-cli skills, `@playwright/test`)
  is kept.
- New operator tools COPY'd to `/home/pwuser/.local/bin` (siblings of
  `cep_codegen`): `cep_authoring` (unattended orchestrator), `cep_package`
  (shared packaging tool), and `cep-cdp-mcp` (the chrome-devtools-mcp
  launcher). The base/scheduled image never ships them.
- `--headed`/`--vnc` now reach the authoring workflow, for **both** browsers:
  the `cep-cdp-mcp` launcher runs the AI's exploration browser visible when
  `HEADED=1`, and `cep_authoring`'s RUN phase adds `--headed` so the
  verification run is visible too — so `check_cep --authoring --headed` lets an
  operator watch the agent inspect the live site *and* watch the generated test
  execute (verified on Wayland). Both are pinned to the standard **1280×720**
  viewport (exploration via the MCP `--viewport` arg, the test via the authored
  config) so the agent inspects the same geometry the deployed check runs at.

### Skill, references, docs

- New skill `.agents/skills/cep-test-authoring/` (staged via the existing
  Makefile skill copy): `SKILL.md` (explore→assess→author→run→compare
  workflow, reuse conventions, quality gate, knowledge rules) plus
  `references/` — `intent-template.ai`, `critic-prompt.md`,
  `quality-checklist.md`.
- Package format fixed in `contracts/package-layout.md`: a
  `<TestName>-<YYYYMMDD>.tar.gz` deployable unchanged via
  `--test-artifact`/S3; `cep_package` refuses to build on a secret found
  outside `.env`.
- `WRITING-TESTS.md` gained a two-audience "AI-Assisted Test Authoring"
  chapter; `README.md` a pointer; `etc/check_cep/tests/onvista/KNOWLEDGE.md`
  seeded as a demo of the per-site knowledge convention.

### Verification

Integration tests (`tests/integration/test_modes.py`,
`tests/integration/test_authoring_orchestrator.py`): authoring env-injection
+ site-level rw mount matrix, the exit-3 refusals, the no-key warning, and
the orchestrator PREFLIGHT failures + cap-termination. Scheduled-path
regression covered by the existing suite (`test_collision.py` unchanged and
green).

End-to-end proven live against `example.com` with `gemini-3.1-flash-lite`:
plain-language intent → AI-authored deterministic test → 2/2 clean runs →
independent critic **pass** → gate → packaged `.tar.gz`; the package then ran
through the real `check_cep --test-artifact` path on the **base** image with
`GEMINI_API_KEY` unset → `OK` with perfdata (confirms FR-020/SC-003 — no AI at
run time). Two defects were found and fixed during this run:

- The `ai`-stage `npm install` pruned the base image's `node_modules`
  (`@playwright/test` / the `playwright` runner), which broke `npx playwright
  test` in the authoring image. Root cause: the base stage deleted its
  `package.json`, orphaning `node_modules`, so npm 7+ reified the tree to only
  the AI packages. Fixed by keeping the base manifest, which makes the
  ai-stage install additive (one npm prefix, more packages).
- The orchestrator's critic phase logged its progress line to stdout while the
  caller captured that stdout as the verdict — fixed so the captured function
  emits only the verdict.

---

## Spec 019 — Pin Gemini CLI to Latest Stable Release

**Branch**: `019-update-gemini-cli`

### Summary

`@google/gemini-cli` was the only build dependency in `src/container/Dockerfile`
installed without a version pin (`npm install @google/gemini-cli @playwright/cli`),
so every AI image build (`image-ai`, `test-image-ai`) silently resolved to
whatever npm's `latest` dist-tag happened to be that day. Pinned it to the
current stable release, `0.49.0`, following the same `ARG`/Makefile-variable
pattern already used for `PLAYWRIGHT_VERSION`.

### Version pin

`GEMINI_CLI_VERSION` (default `0.49.0`) in `Makefile`, passed via `--build-arg`
to the `image-ai` and `test-image-ai` targets; `ARG GEMINI_CLI_VERSION=0.49.0`
in `src/container/Dockerfile`'s `ai` stage builds `AI_NODE_PACKAGES` as
`@google/gemini-cli@${GEMINI_CLI_VERSION}`. Override with
`make image-ai GEMINI_CLI_VERSION=x.y.z`. An invalid version fails the build
loudly via npm's own `ETARGET` error — no silent fallback.

### Scope

Only the AI image variants are affected; `make image`/`test-image` (the
non-AI base images) remain unchanged and gemini-free.

---

## Spec 018 — Lightpanda 0.3.4 Upgrade & Broader Test Coverage

**Branch**: `018-lightpanda-034-upgrade`

### Summary

Bumped the pinned native Lightpanda browser binary from `v0.2.6` to `0.3.4`
(`ARG LIGHTPANDA_BROWSER_VERSION` in `src/container/Dockerfile`) and expanded
the Lightpanda integration lane to cover the check kinds the newer engine can
now run reliably.

### Playwright bumped v1.58.2 → v1.60.0

Aligned the container's Playwright with the version the official
`lightpanda-io/demo` runs (`~1.60.0`): base image `mcr.microsoft.com/playwright:
v1.60.0-noble` (Makefile `PLAYWRIGHT_VERSION` + Dockerfile ARG) and
`@playwright/test` in `src/container/package.json`/`package-lock.json`. No
breaking 1.59/1.60 change affects this project (the removed `connectOverCDP`
`logger` option isn't used; no `videosPath`/`videoSize`/`ariaRef`/`exposeBinding`
/`junit` usage). Full integration suite unchanged (22 passed). Note: the bump
does **not** unlock Lightpanda interaction on heavy pages — the click hang below
persists on 1.60, confirming it is a Lightpanda actionability limit, not a
Playwright-client version issue.

### Version pin — mind the tag scheme

The `0.3.x` releases dropped the `v` prefix used by the `0.2.x` line. The pin
is `0.3.4` (**not** `v0.3.4`, which 404s); the download-URL template is
unchanged. The build hard-fails via `curl -f` if the asset is missing, so the
pin stays reproducible.

### Expanded Lightpanda lane

`FIXTURES_LIGHTPANDA` in `tests/integration/test_modes.py` grew from 2 to 4
fixtures. Promoted (same Nagios verdict as Chromium, verified empirically):

- `tc_fail` — failing-assertion path → `CRITICAL -`
- `tc_timeout` — timeout guardrail → `CRITICAL - ... timed out` within its limit

### Upgrade canary (`tc_pass_canary`)

`tc_pass` additionally runs in the Lightpanda lane as a **strict xfail canary**
with Chromium-lane expectations (`OK -`, exit 0). It is a *broad* interaction
canary: `tc_pass` trips on the first unsupported interaction — a number-input
`fill()` that raises `InvalidStateError` (~20s → `CRITICAL` → XFAIL, suite stays
green) — and never reaches its click. An XPASS therefore requires the engine to
broadly support interaction (number/date `fill()` **and** click actionability
**and** value read-back), not a single fix. When a future Lightpanda pin bump
makes it pass, `strict=True` turns the XPASS into a loud suite failure — the
automatic signal to re-review which fixtures can be promoted, replacing manual
per-upgrade probing. The interaction limits are architectural (no CSS layout
engine, so Playwright's click actionability hit test cannot converge on
CSS-framework pages); analysis and rejected alternatives (e.g. `force: true` —
would weaken the user-fidelity guarantee) are documented in the spec folder
(`dual-engine-assessment.md`, research item R6).

### Capability boundary (verified on 0.3.4, cross-checked vs. changelog + demo)

Genuinely improved: text/password `fill()` now writes the DOM value, and
`locator.click()` works on **simple/static pages** (an `example.com` link-click
navigates, matching the official `lightpanda-io/demo`). Still limited: click
**hangs on complex / JS-heavy app pages** — on `practice.expandtesting.com` the
element is found but Playwright's click actionability never completes → timeout,
so multi-field forms (`tc_pass`) and multi-page flows (`tc_register_pass`), which
target that heavy site, remain Chromium-only. Also: `fill()` on
`<input type=number|date>` throws `InvalidStateError`; `getByText()`/`toHaveValue()`
matchers are unreliable on some pages. Vision fixtures stay permanently
Chromium-only (no rendering engine). No check was weakened to pass on Lightpanda;
unsupported interactions return a clear `CRITICAL` within their time limit (no
hang).

---

## Spec 017 — S3 Source: Explicit TGZ Artifact Input

**Branch**: `017-s3-tgz-source`

### Summary

Replaced the implicit `{test_name}/scripts.tgz` S3 key derivation with an
explicit `--test-artifact` parameter. The artifact value encodes both bucket
and key for S3 sources (`/bucket/path/to/tests.tgz`) and accepts a local
directory or `.tgz`/`.tar.gz` file for local sources.

### Breaking change — `--s3-bucket` removed

The `--s3-bucket` CLI argument and the `S3_BUCKET` container environment
variable are **removed**. The bucket name is now the first path segment of
`--test-artifact`. Update existing S3 check commands:

```
# Before
--test-source s3 --s3-bucket mybucket

# After
--test-source s3 --test-artifact /mybucket/path/to/tests.tgz
```

### New parameter — `--test-artifact`

| `--test-source` | `--test-artifact` value | Behaviour |
|-----------------|------------------------|-----------|
| `s3` | `/bucket/key/tests.tgz` | Downloaded from S3, cached in `testscripts-cache/`, extracted to container |
| `local` | `/path/to/tests.tgz` | Mounted at fixed container path, extracted inside container |
| `local` | `/path/to/tests/` | Directory mounted directly at `/home/pwuser/tests` |

### New container environment variable — `TEST_ARTIFACT`

The value of `--test-artifact` is forwarded into the container as
`TEST_ARTIFACT`. Source plugins use it to locate and acquire test scripts.

### Deprecation — `--test-dir`

`--test-dir` continues to work for `--test-source=local` directory mounts
but now emits a deprecation warning to stderr. Use `--test-artifact` instead.
Supplying both `--test-dir` and `--test-artifact` is an error.

### S3 cache layout

Cache entries now mirror the full artifact path under `testscripts-cache/`:

```
testscripts-cache/
└── mybucket/
    └── path/
        └── tests.tgz
```

Freshness is checked via S3 `HeadObject` (mtime + size comparison).

---

## Spec 014 — AI Agent Skill Files

**Branch**: `014-ai-agent-skills`

### Summary

Added three AI agent skill folders under `.agents/skills/` that give any
AI coding agent instant senior-level knowledge for check-cep-vision image
matching, Sakuli-to-Playwright migration, and general Playwright test
authoring. Skills are also deployed into the container at
`/home/pwuser/.agents/skills/`.

### Added

- `check-cep-vision` skill — SKILL.md with quick start, decision tree,
  region presets, click offsets, hybrid fallback, anti-patterns, and
  environment reference. Supporting docs: api-reference.md (complete
  function signatures and types), template-guide.md (capture workflow and
  crop rules), vision-explainer.md (two-stage matching pipeline internals),
  troubleshooting.md (diagnosing not-found/ambiguous failures)
- `sakuli-migration` skill — SKILL.md with 5-rule migration framework
  ("migrate locator intent, not just test outcome"), translation table,
  migration definition of done, and Rule 3a pragmatic fallback doctrine.
  Supporting docs: migration-rules.md, translation-table.md,
  project-structure.md, cookie-consent.md
- `playwright-skill` symlink — links to the existing `playwright-skill/`
  submodule for general Playwright test authoring guidance
- Makefile `_copy-skills` target — copies `.agents/skills/` (with `cp -rL`
  to dereference symlinks) into the Docker build context before image
  builds, cleans up afterward
- `.gitignore` entry for `src/container/.agents-skills/` (temporary build
  artifact)

### Changed

- `src/container/Dockerfile`: added COPY for `.agents-skills/` into
  `/home/pwuser/.agents/skills/` with Gemini-compatible symlink at
  `/home/pwuser/.gemini/`
- `Makefile`: `image` and `test-image` targets now depend on `_copy-skills`

---

## Spec 013 — More Realistic Test Coverage for check_cep

**Branch**: `013-more-tests`

### Summary

Expanded the regression suite with a new wave of realistic, visually busy local fixtures and documented the hard-but-fair authoring patterns needed for reliable Playwright + vision tests. The branch also clarified and stabilized the Lightpanda path used by the integration suite.

### Added

- New realistic local fixtures under `tests/fixtures/`:
  - `tc_shop_catalog_grid`
  - `tc_news_homepage_busy`
  - `tc_marketplace_preview_tile`
  - `tc_marketplace_anchor_then_target`
  - `tc_marketplace_real_photo_pair`
- New lessons-learned documents:
  - `docs/lessons-learned/013-more-tests.md`
  - `docs/lessons-learned/013-lightpanda-versioning-and-install.md`

### Changed

- `tests/integration/test_modes.py`: registered the new realistic fixtures in the local/S3 matrix and made the Lightpanda lane explicitly ignore spectate mode so `CEP_SPECTATE=1` can still be used for Chromium demo runs.
- `tests/integration/conftest.py`: added an explicit `spectate` override to `run_check_cep()` so individual integration lanes can disable headed mode intentionally.
- `WRITING-TESTS.md`: expanded with advanced guidance for realistic clutter fixtures, ambiguity-first assertions, anchor-then-target matching, repeated region tightening, and similar-photo handling, plus direct links to the marketplace examples.
- `src/container/Dockerfile`: documented the Lightpanda package/binary version split, pinned the standalone browser binary to `v0.2.6`, and made the binary install deterministic at `/usr/local/bin/lightpanda`.
- `src/container/package.json` / `src/container/package-lock.json`: removed the unused `@lightpanda/browser` npm dependency after confirming the runtime path uses the standalone Lightpanda binary only.

### Fixed

- Lightpanda integration tests now pass on the standalone-binary path without depending on the npm wrapper package.
- Lightpanda tests no longer fail when the outer pytest run uses `CEP_SPECTATE=1` for Chromium observation.
- The repository now records the actual Lightpanda integration model clearly: Playwright connects over CDP to `/usr/local/bin/lightpanda serve`, not through the npm package runtime.

---

## Spec 012 — Failure Screenshot in Playwright Report

**Branch**: `012-failure-screenshot`

### Summary

Changed the demo `playwright.config.ts` template so that failed tests show a full-page screenshot in the HTML report instead of a long, unreadable HTML page dump.

### Changes

- Added `screenshot: { mode: 'only-on-failure', fullPage: true }` to the `use` section — Playwright now captures a full-page screenshot at the moment of failure.
- Existing user configs are not modified automatically; see `specs/012-failure-screenshot/quickstart.md` for manual migration.

---

## Spec 011 — Externalize Demo Configurations

**Branch**: `011-externalize-demo-configs`

### Summary

Moved inline demo file content out of `setup-omd-site.sh` into a new `omd-demo/` directory that mirrors the OMD site root. The setup script now does a recursive copy instead of generating files via heredocs.

### Changes

- New `omd-demo/etc/` tree containing the demo Playwright test (`consol.test.ts`, `playwright.config.ts`) and a Naemon monitoring config (`cep-demo.cfg`) with portable `$USER2$`/`$USER4$` macros.
- `setup-omd-site.sh`: replaced heredoc section with `cp -r omd-demo/etc/ $OMD_ROOT/etc/`, added validation for missing/empty `omd-demo/`, extended `chown` scope for the Naemon config path, added web symlink (`var/www/check_cep` → `var/tmp/check_cep`).
- make the demo test case fail from time to time (1 out of 10 on a random basis)

---

## Spec 010 — RunContext: Shared Execution Context

**Branch**: `010-run-context`

### Summary

Introduced two frozen dataclasses to eliminate function signature churn across the plugin:

- **`RunConfig`** (33 typed fields): immutable wrapper for all CLI arguments, replacing raw `argparse.Namespace` access after argument parsing.
- **`RunContext`** (12 fields): immutable per-run state combining identity (`hostname`, `servicedescription`, `testname`, `testident`, `container_name`), timing (`start_time`, `started_str`, `timeout_deadline`), paths (`result_dir`, `pid_file`, `omd_root`), and the nested `RunConfig`.

### Migrated Functions

Four functions now accept `RunContext` instead of individual shared-state parameters. `resolve_path_template` remains a standalone string utility (no RunContext dependency).

| Function | Before | After |
|---|---|---|
| `resolve_report_url` | 7 args | 2 args (`ctx`, `timestamp`) |
| `build_podman_command` | 5 args | 3 args |
| `run_cleanup` | 5 args | 2 args |
| `build_env_vars` | 2 args | 1 arg |
| `resolve_path_template` | 4 args | 4 args (unchanged, pure string utility) |

Total positional parameters reduced from 23 to 12.

### Other Changes

- All `args.*` access is now confined to the `RunConfig` constructor; the rest of `main()` reads from `config.*` or `ctx.*`.
- `RunContext` is logged at `DEBUG` level immediately after construction.
- `main()` is structured in four clearly separated phases: parse + `RunConfig`, validate, `RunContext` construction, run + format.
- New test helper module `tests/unit/test_run_context.py` with `make_config(**overrides)` and `make_ctx(**overrides)` factories for single-override unit test setup.
- Deleted `docs/CONTEXT.md` (superseded by `specs/010-run-context/`).

---

## Spec 009 — Local Report Housekeeping

**Branch**: `009-report-management`

### Added
- `%t` placeholder in `--result-dir` and `--report-url` — resolves to the process start time (Unix epoch), giving each run its own isolated timestamped directory
- `--report-retention Xh` — auto-deletes old per-run directories after each check, oldest-first, with a 10 s safety margin before the plugin timeout deadline
- `CleanupResult` dataclass, `ReportCleanupPlugin` Protocol, and `LocalCleanup` implementation — storage-agnostic cleanup with S3 extensibility in mind
- `CEP_STARTED` env var — host process start time passed into the container so `test-meta.json` records the same timestamp used for `%t`
- `docs/CONTEXT.md` — design document for a future `RunContext` refactor

### Changed
- `test-meta.json` schema v2: `timestamp` field renamed to `finished`; new `started` field added (Unix epoch of host process start)
- PID file relocated from `result_dir/` to `$OMD_ROOT/var/tmp/check_cep.{testident}.pid` so the duplicate-run guard works when `%t` creates unique per-run directories
- Dockerfile: direct nightly binary fallback for Lightpanda when the npm postinstall fails due to GitHub API rate-limiting during the build
- `patch-lightpanda.js`: infrastructure log lines moved from `console.error` to `console.log` with `[CEPDBG]` prefix — prevents false WARNING triggers from stderr detection
- `run.py`: `OSError` added alongside `RuntimeError` when catching Lightpanda startup failures — missing binary now produces `UNKNOWN` instead of an unhandled exception crash

### Fixed
- Playwright report URL in plugin output now resolves `%t` to the correct run timestamp when `test-meta.json` contains `started`

---

## Spec 008 — Unified Debug Logging

**Branch**: `008-debug-logging`

### Added
- `cepDebug(message)` function in `check-cep-helpers` — test authors can emit debug-only messages with the `[CEPDBG]` prefix, visible only with `--debug`
- TypeScript declaration for `cepDebug` in `check-cep-helpers/index.d.ts`

### Changed
- Vision traces (`check-cep-vision`) moved from `console.error('[cep] ...')` on stderr to `console.log('[CEPDBG] ...')` on stdout — eliminates false WARNING triggers from stderr pollution and makes vision diagnostics visible with `--debug`
- `extract_output_from_steps()` now accepts a `debug` parameter; stdout lines starting with `[CEPDBG]` are filtered out unless `--debug` is active — single filtering point on the host side
- `extract_output_from_steps()` no longer filters `[cep] ` from stderr — all stderr entries pass through unconditionally (no `[cep]` lines will be produced anymore)
- `run.py` dispatcher now forwards Playwright stdout and stderr unchanged — removed `[cep]` prefix filter loop

### Fixed
- False WARNING status when running vision-using tests (caused by `[cep]` lines on stderr being detected as `has_stderr`)

---

## Spec 007 — Vision Autoscroll (Best-Effort Interaction Functions)

**Branch**: `007-vision-autoscroll`

### Added
- `vision.clickBestEffort(locator, options?)` — scroll into view + click with progressive fallback (standard → forced → DOM-level)
- `vision.typeBestEffort(locator, text, options?)` — scroll into view + type with progressive fallback
- `vision.fillBestEffort(locator, value, options?)` — scroll into view + fill with progressive fallback
- `scrollIntoView` option (default: `true`) to opt out of automatic scrolling when needed
- Transparent Lightpanda compatibility: scroll step silently skipped on DOM-only browsers
- Debug logging for individual fallback steps when `--debug` is active (`process.env.DEBUG`)
- TypeScript declarations for all three new functions and the `scrollIntoView` option
- `check-cep-helpers` npm package bundled in the container — shared test utilities (`cepLog`, `cepLogLocated`, `cepLogFound`, `cepLogType`, `cepLogPress`, `cepLogWait`, `cepLogUrl`) for timestamped Playwright test logging

### Changed
- Existing migrated testcases refactored to use centralized bestEffort functions, replacing duplicated local `clickWithFallback` helpers and ad-hoc `scrollIntoView` evaluate calls
- Logging helpers extracted from 7 testcase-local `functions/index.ts` files into `check-cep-helpers`, eliminating identical copies of `cepLog` and its derivatives

---

## Spec 006 — README Visual Teaser

**Branch**: `006-readme-teaser`

### Added
- 4-scene animated GIF teaser at the top of README.md: passing test, Playwright report, failing test with "Invalid credentials", error details
- Title cards (1-second, dark background, white text) between each scene for context
- `scripts/teaser/teaser-pass.test.ts` — passing login with `highlightLocator()` on the "Signed in as operator" result
- `scripts/teaser/teaser-fail.test.ts` — login with "operator " (trailing space) triggers "Invalid credentials" rejection with red styling
- `scripts/teaser/record-report.js` — records Playwright HTML report navigation inside the container
- `scripts/generate-teaser.sh` — orchestrates 4 test/report recordings, title cards, video concatenation, and GIF conversion
- `make teaser` target to regenerate the GIF reproducibly

### Changed
- Login fixture (`login.html`) `handleSignIn()` now validates the username — non-"operator" usernames show "Invalid credentials" in red with light-red input backgrounds
- Pass/fail scenes are visually distinct: green "Signed in as operator" vs. red "Invalid credentials" with red-tinted input fields

### How it works
- Runs two teaser-specific tests via check_cep with Playwright video recording (`CEP_SLOW_MO=600`, `CEP_VISION_HIGHLIGHT_MS=800`)
- Passing test enters "operator" → success. Failing test enters "operator " (trailing space) → web app rejection with red error styling
- Records Playwright HTML report navigation via `podman run` with `record-report.js`
- ffmpeg generates title cards, normalizes all video segments, concatenates, and converts to GIF via two-pass palette method
- GIF parameters: 640px wide, 10 fps, 128 colors, bayer dithering — stays under 5 MB

---

## Spec 005 — Lightpanda Browser Integration

**Branch**: `005-lightpanda-browser`

### Added
- `--browser lightpanda` CLI flag for using Lightpanda as an alternative headless browser engine
- CJS monkey-patch (`patch-lightpanda.js`) that transparently redirects Playwright's `chromium.launch()` to Lightpanda's CDP endpoint — no test file changes needed
- `canScreenshot()` guard in check-cep-vision so vision functions degrade gracefully on browsers without a rendering engine
- Lightpanda integration tests (`tc_lp_pass` fixture)
- Lightpanda section in WRITING-TESTS.md

### Fixed
- `[cep]` infrastructure messages (from monkey-patch `console.error()`) no longer leak into Nagios output — filtered in both `run_playwright()` and `extract_output_from_steps()`
- Container-side `print("[cep] ...")` calls replaced with `logger.debug()` to avoid bypassing the output filter
- Lightpanda lifecycle extracted into `start_lightpanda_cdp()` / `stop_lightpanda_cdp()` helpers
- `BROWSER` env var now always set in container environment (was conditional, causing inconsistency)

### Limitations
- Lightpanda is experimental: single navigation + DOM reads only
- `fill()`, `click()` with navigation, second `goto()`, and complex sites crash the CDP server
- Vision matching not available (no rendering engine)

---

## Spec 004 — Advanced Vision Tests and Documentation

**Branch**: `004-vision-advanced-tests`

### Added
- Three worked example fixtures: `tc_vision_example_form`, `tc_vision_example_console`, `tc_vision_example_login`
- Spectate mode (`CEP_SPECTATE=1`) for headed test demos with configurable slow-motion and highlight overlays
- `WRITING-TESTS.md` — comprehensive test authoring handbook covering folder structure, vision API, templates, regions, click offsets, selector strategy, and worked examples
- Chrome binary wrapper that injects GPU-disable and Wayland flags at the binary level — `playwright codegen` now works in containers
- `cep_codegen` convenience alias for `npx playwright codegen`
- `test.step()` performance data extraction — each step's duration becomes a separate Nagios metric
- DOM selector strategy guide (recommended default over vision)

### Changed
- Tutorial moved from standalone file to `README.md`

---

## Spec 003 — check-cep-vision Library

**Branch**: `003-check-cep-vision`

### Added
- `check-cep-vision` npm package bundled in the container at `/home/pwuser/node_modules/check-cep-vision`
- Vision-only functions: `locateByImage`, `waitForImage`, `existsByImage`, `clickByImage`, `typeByImage`
- DOM helper functions: `clickFirstVisible`, `fillFirstVisible`
- Hybrid functions with automatic DOM fallback: `clickByImageOr`, `typeByImageOr`
- Debug functions: `highlightByImage`, `highlightLocator`, `highlightFirstVisible`
- Region presets (`header`, `main`, `footer`, `left`, `right`, `topLeft`, `topRight`) and custom `RectRegion` support
- Multi-scale template matching (default scales: 0.97, 1.0, 1.03)
- Ambiguity detection with configurable gap threshold
- Debug artifact output (`*-region.png`, `*-annotated.png`, `*-meta.json`)
- `--headed` flag for running tests with a visible browser on the host desktop
- TypeScript declarations (`index.d.ts`) for full IDE support

### Dependencies
- `opencv-wasm` 4.3.0-10 (WASM-compiled OpenCV for template matching)
- `pngjs` 7.0.0 (PNG decode/encode)

---

## Spec 002 — Test Environment and Bug Fixes

**Branch**: `002-test-env-setup`

### Added
- Pytest integration test suite (`tests/integration/test_modes.py`) with parametrized fixtures for local and S3 modes
- `conftest.py` test helpers: `run_check_cep()`, `local_test_dir()`, `run_check_cep_s3()`
- OMD install script for development environments
- Test fixtures: `tc_pass`, `tc_fail`, `tc_timeout`, `tc_syntax`, `tc_register_pass`

### Fixed
- `result_dest == "local"` guards that prevented result artefacts from being written in local mode
- Test directory discovery (`chdir` to first `test.ts` location)
- Container build setup reorganized for reproducibility

---

## Spec 001 — CEP Framework Overview

**Branch**: `001-cep-framework-overview`

### Added
- `check_cep` host-side Nagios/Naemon plugin (Python) — CLI params, Podman container orchestration, result parsing, Nagios-formatted output
- `run.py` container-side dispatcher — plugin architecture with source/dest/logging modules
- Plugin modules: `source_local.py`, `source_s3.py`, `dest_local.py`, `dest_s3.py`, `logging_loki.py`
- Container image based on Microsoft Playwright (`mcr.microsoft.com/playwright`)
- `steps.json` and `test-meta.json` result format
- CLI flags: `--test-source`, `--result-dest`, `--logging`, `--timeout`, `--host-name`, `--service-description`, `--image`, `--test-dir`, `--result-dir`
- Template variables `%h` / `%s` for host-name/service-description in paths
- SELinux-compatible volume mounts (`:z` suffix)
- CPU limit hardcoded at 2 cores
- PID file concurrency control
