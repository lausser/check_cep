# AI Test-Authoring Hardening (spec 021/022)

This tree proves — and keeps proving — that the spec-020 AI authoring workflow
reliably produces *good*, deterministic Playwright tests for *hard*, realistic
pages. It contains three things:

- **`sample-app/`** — a self-contained, deterministic target: a realistic,
  distraction-rich multi-page fake-bank **journey site** plus isolated
  single-difficulty **probe routes**. See `sample-app/README.md` for the
  hard-case catalogue.
- **`golden/<Capability>/`** — hand-written (intent, ideal test) pairs. The
  ideal tests are *proven*, not aspirational: each passes deterministically
  against its sample-app page offline.
- The **gated behavioural eval** (`tests/integration/test_authoring_eval.py`)
  that runs the real `cep_authoring` orchestrator against the sample app and
  asserts capability *outcomes* — never the generated source text.

## A. Serve the sample app (offline, no AI, free)

The app is static HTML with **relative links**, served by `file://`. Nothing to
install, no server to start — just open a page:

```bash
# open in a browser to eyeball the journey
xdg-open tests/authoring-eval/sample-app/journey/index.html
```

**One exception:** the `probes/iframe/` case needs a real HTTP origin (so parent
and frame share an origin — `file://` documents have an opaque/null origin). It
ships a `playwright.config.ts` with a `webServer` (`python3 -m http.server`) that
starts automatically when its test runs. Every other page works under `file://`.

## B. Run the golden ideal tests (offline, no AI, free)

The golden tests resolve `@playwright/test` and `check-cep-vision` from the
container's bundled `node_modules`. On a host that has them (this repo ships them
under `src/container/node_modules/`), run a golden pair offline like this:

```bash
NM="$PWD/src/container/node_modules"        # from repo root
# one-time: install the browser binary Playwright expects
node "$NM/.bin/playwright" install chromium

cd tests/authoring-eval/golden/MultiPageJourney
NODE_PATH="$NM" node "$NM/.bin/playwright" test --config playwright.config.ts
```

> **Note:** image-template fallback probes (`no-stable-locator`,
> `moving-element`) match against a tightly-cropped PNG. Exact pixel matching can
> differ across host fonts/rendering; those pairs are verified authoritatively
> **inside the AI container**, where fonts match the authored-test runtime. Every
> other golden test passes on a plain host.

## ⚠ Verification status

**The gated eval has been run to completion on the opencode backend
(spec 022)**: all 12 cases pass — 9/9 positive cases (SC-001, SC-003) and all
3 adversarial cases (SC-002), each correctly refusing/flagging rather than
fabricating a passing package. The default free `opencode/big-pickle` model
is keyless, so this required no paid key — only patience across a couple of
transient rate-limit windows on the free tier (a quota/rate-limit hit is
classified `quota_error` and **fails** the run immediately; there is no
skip/retry — see the gating knobs below).

## C. Run the gated behavioural eval (needs AI image + `CEP_AI_EVAL=1`)

The eval is gated **solely by the explicit `CEP_AI_EVAL=1` opt-in** — the
default model is keyless, so credential presence can no longer be the gate.
With the flag unset the eval cases `skip` and the fast/offline suite stays
green.

```bash
make image-ai                                  # → localhost/check_cep:ai-latest
export CEP_AI_EVAL=1                            # THE gate (explicit opt-in)
# optional: export OPENCODE_MODEL=opencode/big-pickle   # already the default

# flagship case only (conserves quota):
pytest -m authoring_eval tests/integration/test_authoring_eval.py -k MultiPageJourney -v

# full positive + adversarial set (nightly / on-demand):
pytest -m authoring_eval tests/integration/test_authoring_eval.py -v
```

Watch it happen (optional, headed + slow-motion):

```bash
export HEADED=1
export CEP_SLOW_MO=400        # FR-016: slows the verification RUN so it's watchable
# ...then run the eval as above. Exploration + verification run visible at 1280×720.
```

## Gating knobs (harness)

| Env | Default | Effect |
|---|---|---|
| `CEP_AI_EVAL` | unset | **The gate.** `1` ⇒ eval eligible; unset ⇒ all cases skip. |
| `CEP_AI_IMAGE` | `localhost/check_cep:ai-latest` | AI image; missing ⇒ skip. |
| `OPENCODE_MODEL` | `opencode/big-pickle` | Pinned model (FR-014); keyless by default. |
| `OPENCODE_API_KEY` / `GEMINI_API_KEY` | unset | Passed through if set on the host (curated paid Zen model / Gemini connection); never the gate. |
| `CEP_MAX_ITERATIONS` | `5` | Passed to `cep_authoring -n` (pass bar). |
| `CEP_SLOW_MO` | unset | With `HEADED=1`, slows the verification RUN (FR-016). |

A quota/rate-limit hit **fails** the eval immediately with a distinct
`quota_error` classification — there is no retry or skip/spread mode
(user decision 2026-07-20). The fix is more budget (another free model or a
Zen key via `OPENCODE_MODEL`), then a fresh run.

See `specs/022-opencode-authoring/` for the backend-migration spec, contracts,
and research (`specs/021-ai-test-hardening/` for the original hardening spec).
