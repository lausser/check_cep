---
name: cep-test-authoring
description: Expert guidance for turning a plain-language intent file (*.ai) into a deterministic, deployable check_cep Playwright test. Use when authoring a check_cep test from a user's described flow, exploring a site to find stable locators, enforcing the authoring quality gate, or recording site knowledge. Triggers on cep-test-authoring, intent file, *.ai, authoring mode, cep_authoring, cep_package, KNOWLEDGE.md, quality gate, critic pass, VERIFICATION.md.
---

# cep-test-authoring: From Plain-Language Intent to Deployed Check

Turn a non-technical user's **intent file** (`*.ai`) into a deterministic
Playwright test that `check_cep` runs on schedule — with **no AI at run
time**. One authoring session: explore the site, assess whether the intent
is coherent, author the test reusing sanctioned robustness patterns, run it
until it is stably green, compare the result against the user's intent, and
package it.

## When to Use

Use this skill when an admin has entered `check_cep --authoring` (a bash
shell in the `ai` image, site workspace mounted read-write, `GEMINI_API_KEY`
set) and wants to produce a check from an intent file. You are working
inside the container as `pwuser`; the site workspace is at
`/home/pwuser/tests`.

## The Golden Rule

The output is a **deterministic Playwright test**. Once packaged and
deployed, it runs on a schedule with **no AI, no `GEMINI_API_KEY`, and no
browser-inspection tooling** (FR-007, FR-020). Never author anything that
would need a model at run time. If you cannot express a check
deterministically, say so — do not fake it.

## Workflow Overview

```
PREFLIGHT → EXPLORE → ASSESS → AUTHOR → RUN → COMPARE → (gate → package)
```

The quality gate and packaging are covered under **Quality Gate** below.
This section covers PREFLIGHT through COMPARE.

### PREFLIGHT — validate the intent before touching the browser

1. Read the intent file (`<TestName>.ai`). Confirm the **required
   sections** are present: the title, `## Target URL`, `## Desired Flow`,
   `## Success Criteria`, and a `## Lessons Learned` heading (may be empty).
   A missing required section is a hard stop — report which section is
   missing, by name, and ask the admin to complete the intent (FR-001b).
2. Resolve every `@relative-filename` reference in the file. Each referenced
   file (e.g. `@login-button.png`) MUST exist next to the intent file. If
   any is missing, stop and name the missing file — do not proceed
   (FR-001b).
3. Read the site-level `KNOWLEDGE.md` (workspace root) before exploring from
   scratch — earlier sessions may already have solved consent dialogs,
   selectors, timing, or login quirks (see **Site Knowledge**).

### EXPLORE — a two-tool discover-then-confirm workflow

Exploration is **two tools, two purposes**. Never author a selector on
faith: the tool that will *run* the test is the tool that confirms the
locator.

1. **DISCOVER with `chrome-devtools-mcp`.** Use it to drive a live browser:
   navigate to the target URL, search the DOM / accessibility tree for the
   element that matches a plain-language hint ("the big green *Anmelden*
   button", "the portfolio total"), and diagnose the hard cases — inspect
   **network requests**, **console messages**, and **timing/performance**
   traces to understand dynamic values, lazy loading, and when a value is
   actually ready. This is where you find *what* to interact with and
   *why* a page behaves the way it does.
2. **CONFIRM with the Playwright-native tooling.** Take each discovered
   candidate and confirm it as a stable **Playwright** locator using the
   `@playwright/cli` skill / the Playwright locator API. Prefer, in order:
   `getByRole()`, `getByText()`, `getByLabel()`, `getByTestId()`. A good
   locator resolves to **exactly one** element (`await
   locator.count()` === 1). If it is ambiguous or brittle, refine it or pick
   a different anchor.
3. **Fall back to vision only when there is no stable locator.** Canvas,
   WebGL, dynamic class-name soup, or PDF content with no DOM anchor →
   `check-cep-vision` template matching (see **Reuse Conventions** and the
   `check-cep-vision` skill). DOM locators first; vision when DOM is
   insufficient (FR-008).
4. `npx playwright test` is **not** an exploration tool — it is reserved for
   the RUN phase.

### ASSESS — is this intent coherent and deterministic?

Before authoring, judge whether a faithful, deterministic test is even
possible.

- **Refuse to fabricate** a test for an intent that is incoherent,
  self-contradictory, or fundamentally non-deterministic (e.g. "check that
  a random promo appears" with no stable success signal). Explain the
  problem and propose how the intent could be revised — do not invent an
  assertion that merely passes (FR-005).
- **Recognise non-technical omissions and ASK — do not guess** (FR-006).
  The intent author performed a manual session and may not have mentioned
  things a machine must handle:
  - **Login walls / auth** — where do credentials come from? (They belong
    in `.env`, never inline — see **Reuse Conventions**.)
  - **Consent / cookie dialogs** — do they appear on every run, only the
    first, region-dependent?
  - **Dynamic values** — a total that changes each load, a timestamp, a
    session id. What is the *stable* success signal?
  - **Ambiguous success** — "the page looks right" is not checkable. Pin it
    to something observable.
  - **Variant layouts** — A/B tests, responsive breakpoints, logged-in vs
    logged-out.
  When any of these is unclear, ask the admin one concrete question with a
  recommended default. Do not silently pick one and hope.
- **Threshold wishes belong downstream.** If the intent prose asks for
  alert thresholds ("warn if load > 3s", "critical if total < 100"),
  acknowledge it and note that thresholding is handled by the
  metrics/alerting system downstream — then author **without** thresholds.
  Your job is to *emit the measurement* as perfdata (see **Reuse
  Conventions**), not to decide alert levels.

### AUTHOR — write the deterministic test

- Create `tests/<site>/<TestName>/<TestName>.test.ts` plus a per-test
  `playwright.config.ts` and any helpers under `functions/`.
- **Keep a consistent viewport.** The exploration browser and the standard
  test runtime both use **1280×720**. Author the test at that viewport (the
  Playwright default, or set it explicitly) unless the intent genuinely needs
  another — so what you inspected during exploration is the same layout the
  deployed check runs against (a responsive site can look very different at a
  different size).
- Use the locators you **confirmed** in EXPLORE. Every interactive step
  uses a sanctioned robustness pattern (see **Reuse Conventions**), not
  bespoke `waitForTimeout` sleeps or ad-hoc retry loops.
- **Validate every interaction.** After each meaningful action, assert the
  observable consequence (navigation happened, the expected element/text
  appeared). A click with no assertion proves nothing.
- Emit every value the intent asked to capture as **perfdata** (see below).

### RUN — prove it is stably green

- Run the test with `npx playwright test` (from the test's directory, using
  its `playwright.config.ts`).
- A single green run is not enough. Require the configured number of
  **consecutive clean runs** (default 2) before the test is a candidate for
  packaging — flakiness surfaces on the second and third run, not the first
  (FR-015). The **Quality Gate** section covers this.

### COMPARE — measure the result against the intent, not against "it passed"

- Re-read `## Desired Flow` and `## Success Criteria`. For each claim the
  user made, confirm the test actually demonstrates it. A test that passes
  but skips a success criterion is a failure of authoring, not a success.
- Anything you assumed (because the intent was silent), could not verify, or
  where the site differed from the described flow goes into the verification
  report and — for site-general findings — into `KNOWLEDGE.md`.

## Worked examples

Before authoring, read the proven exemplars in `examples/` — hand-written
(intent → ideal test) pairs that show the target shape of a good test:

- **`examples/MultiPageJourney/`** — the flagship **multi-page pattern**: a busy
  landing page with a non-obvious "Online Banking" entry, an interstitial, a
  login wall, then a dashboard. Shows targeting non-obvious elements by stable
  ids amid noise, business-named `test.step()`s, capturing a stable value as
  perfdata, and never asserting a dynamic value.
- **`examples/StableVsDynamic/`** — everyday value-capture discipline: assert the
  stable identity, capture the number as perfdata, leave the ticking clock
  unasserted.

Each ships a `VERIFICATION.md`. They are verified against the eval sample app in
`tests/authoring-eval/golden/`.

## Reuse Conventions

Do not reinvent robustness. The container already ships the sanctioned
building blocks; use them.

### Robustness / fallback patterns (FR-008)

For any element that can move, re-render, or vary between runs, use the
`check-cep-vision` best-effort helpers instead of hand-rolled retry logic:

- `clickBestEffort(locator, options?)` — scroll into view + click with a
  progressive fallback chain (standard → forced → DOM-level).
- `clickByImageOr(page, template, locatorFallback)` /
  `typeByImageOr(...)` — hybrid image-or-DOM interaction with automatic
  fallback.

These are the building blocks the existing suite uses (e.g. the onvista
cookie/consent fallback chain). Reuse them; add a bespoke retry only when no
sanctioned pattern fits, and explain why.

### User-attached screenshots as vision templates (FR-008a)

The intent file may attach tightly-cropped screenshots via `@filename`.
Treat each as a **candidate `check-cep-vision` template**:

1. Try the user's crop directly as a template image.
2. If it does not match reliably (scale/rendering differences), capture your
   own fresh crop of the same element and use that instead.
3. Whichever template images the final test actually uses are **copied into
   the test folder** so they ship in the package (template images live
   beside the test — the spec-003 convention).

### Site-generic helpers (FR-010)

Write helpers that are useful to the **whole site**, not just this one test
— `acceptCookies(page)`, `openLoginPage(page)`, `logout(page)`,
`loadCredentials()`. Put them under the test's `functions/` and keep them
reusable so a later test for the same site imports them instead of
duplicating the flow. Credentials come from `.env` via a loader; never
inline them.

### Perfdata emission (FR-009)

Every value in `## Values to Capture` must leave the test as **perfdata**,
using one of the two existing mechanisms — no core changes, no new plumbing:

1. **Stdout convention** — print a line of the exact form:

   ```
   NagiosPerfData: 'portfolioTotal'=1234.5
   NagiosPerfData: 'loadTime'=0.83s
   ```

   Parsed as `'label'=value<unit>` (unit optional: letters or `%`).

2. **Step annotation** — attach a `perfdata_*`-typed annotation whose
   description is the numeric value (optionally with a unit):

   ```ts
   test.info().annotations.push({
     type: "perfdata_portfolioTotal",
     description: "1234.5",
   });
   ```

Use whichever is cleaner for the value at hand. Do **not** add thresholds —
emit the measurement; alerting is configured downstream.

## Quality Gate

A test is not done when it turns green — it is done when it is provably
faithful to the intent. Before offering a package, pass the full gate. The
scorable list lives in `references/quality-checklist.md` (nine binary
items, all must be YES). The behaviours below back it up.

- **Success Criteria are immutable.** Treat everything above the "DO NOT
  ALTER THE LINES ABOVE" marker — especially `## Success Criteria` — as
  read-only. If you believe a criterion is wrong, unmet, or needs revising,
  **surface the proposal to the admin** (and record it in `VERIFICATION.md`);
  never edit the immutable region to make the test pass (FR-011).
- **Never weaken a verification to force a pass.** If a criterion cannot be
  met, that is a finding, not something to assert around. A test that passes
  by checking less than the intent asked is a failed authoring (FR-013).
- **Require consecutive clean runs.** Run `npx playwright test` until you get
  the required number of **consecutive** clean runs (default 2; use 3 for
  volatile sites) before the test is a packaging candidate. Flakiness shows
  up on run two or three (FR-015).
- **Run the independent critic pass.** Hand the original intent file and the
  finished test files to a **fresh** model process using the fixed prompt in
  `references/critic-prompt.md`. It sees only those files — never this
  conversation — and returns `{"verdict","findings"}`. Resolve every finding,
  or fix the test, before packaging. Treat its verdict as the gate, not a
  suggestion (FR-012).
- **Spectate advisory (non-blocking).** Recommend the admin watch the
  finished test once in spectate mode (`CEP_SPECTATE=1`, `--headed`/`--vnc`,
  `CEP_SLOW_MO`, `CEP_VISION_HIGHLIGHT_MS`). This is human inspection, offered
  and encouraged — it never blocks packaging (FR-012a).
- **Write `VERIFICATION.md`** in the test folder, skimmable in 60 seconds,
  with all five mandatory sections (SC-005, FR-014):
  - **Verified** — intent claims demonstrated by passing runs.
  - **Assumed** — defaults chosen where the intent was silent.
  - **Could not verify** — intent claims not demonstrable, with reasons.
  - **Deviations** — where the site differed from the described flow.
  - **Human inspection advisory** — the spectate-mode invitation.
- **Package.** Only when every checklist item is YES, build the deployable
  archive by invoking the shared tool on the finished test folder (FR-018):

  ```bash
  cep_package <TestName>/        # → <TestName>-<YYYYMMDD>.tar.gz
  ```

  `cep_package` also refuses to build if it finds a secret outside `.env`.

## Site Knowledge

Findings compound. A later session for the same site should start from
experience, not re-explore from scratch.

- **Read before exploring.** At the start of every session, read the
  site-level `KNOWLEDGE.md` at the workspace root (`tests/<site>/KNOWLEDGE.md`)
  before touching the browser. It may already document the consent-dialog
  handling, reliable roles/selectors, iframe quirks, timing/polling behaviour,
  or login peculiarities you would otherwise rediscover (FR-017).
- **Write at session end.** Append or update `KNOWLEDGE.md` with the new
  **site-general** findings from this session. Keep it terse and durable —
  what a future author needs to know about *this site*, not this one test.
- **Never write credentials** into `KNOWLEDGE.md` (or `VERIFICATION.md`, or
  `README.md`, or the intent file). Secrets live only in `.env` (FR-019,
  FR-016).

**Which note goes where** — three distinct places, do not conflate them:

| Where | Scope | Written by | Contains |
|---|---|---|---|
| `tests/<site>/KNOWLEDGE.md` | site-general | authoring sessions | consent dialogs, reliable roles/selectors, iframe/timing/login quirks — anything true for the whole site |
| `<TestName>.ai` → `## Lessons Learned` | this test's attempts | authoring sessions (below the marker only) | dated bullets: what was tried on this test, what failed, what to do instead |
| `tests/<site>/<TestName>/README.md` | this one test | optional | test-specific notes (existing convention) |

- **Write site-generic helpers.** Helpers you create (cookie/consent
  handling, login, credential loading) belong to the whole site — keep them
  reusable so the next test imports them instead of duplicating the flow
  (FR-010). Site-wide behaviour learned while writing them is exactly what
  `KNOWLEDGE.md` should capture.
