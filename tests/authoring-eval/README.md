# AI Test-Authoring Hardening (spec 021)

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

**The gated eval has not yet been run to completion** — no sufficient model-token
budget was available. Everything in sections A and B below is fully verified
offline; the live workflow was confirmed to explore the journey site and author a
good test into the workspace on its first iteration, but **no run has produced a
package end-to-end**, so the full positive-path property set (SC-002) and the
adversarial cases (SC-003) remain unproven.

The blocker is budget, not a known defect: a single clean authoring run exhausts
the Gemini free-tier cap (`generate_content_free_tier_input_token_count`,
250 000/day) during exploration. Supply a paid key or a cheaper provider to
finish the verification. Quota exhaustion is classified as a `skip`, so the eval
never reports a false regression when the budget runs out.

## C. Run the gated behavioural eval (needs AI image + a Gemini key + quota)

The eval is gated **solely by the presence of `GEMINI_API_KEY`** — no separate
opt-in flag. With the key unset the eval cases `skip` and the fast/offline suite
stays green.

```bash
make image-ai                                  # → localhost/check_cep:ai-latest
export GEMINI_API_KEY=...                       # THE gate. Secret, never committed.
export GEMINI_MODEL=gemini-3.1-flash-lite       # pinned (FR-014)

# flagship case only (conserves quota):
pytest -m authoring_eval tests/integration/test_authoring_eval.py -k journey -v

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
| `GEMINI_API_KEY` | unset | **The gate.** Set ⇒ eval eligible; unset ⇒ all cases skip. |
| `CEP_AI_IMAGE` | `localhost/check_cep:ai-latest` | AI image; missing ⇒ skip. |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Pinned model (FR-014). |
| `CEP_MAX_ITERATIONS` | `5` | Passed to `cep_authoring -n` (pass bar). |
| `CEP_EVAL_RETRIES` | `1` | Coarse whole-run retries to absorb model flakiness. |
| `CEP_SLOW_MO` | unset | With `HEADED=1`, slows the verification RUN (FR-016). |

See `specs/021-ai-test-hardening/` for the full spec, contracts, and research.
