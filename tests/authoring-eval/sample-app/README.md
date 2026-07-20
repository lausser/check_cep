# Sample App — Hard-Case Catalogue

A self-contained, deterministic target for the AI test-authoring eval. Two parts:

- **`journey/`** — a realistic, distraction-rich multi-page fake bank (the
  flagship *multi-page distraction navigation* case). Static HTML, relative
  links, served by `file://`.
- **`probes/<name>/`** — isolated single-difficulty routes, one hard case each,
  for diagnosability.

Everything is deterministic across reloads **except** values explicitly marked
dynamic. No real secrets; login uses dummy credentials.

## Catalogue

Each hard case maps to the spec-020 requirement it guards, and to whether a
golden intent→test pair exists for it (`golden/<Capability>/`).

| Difficulty | Page / Route | 020 FR guarded | Golden pair? |
|---|---|---|---|
| Multi-page distraction navigation (flagship) | `journey/` (landing → onlinebanking → login → dashboard) | 020 FR-006/008 | ✅ `MultiPageJourney` |
| Sometimes-present consent dialog (per-context first visit) | `probes/consent-first-visit/` | 020 FR-006 | ✅ `ConsentFirstVisit` |
| Ambiguous elements → locator disambiguation | `probes/ambiguous-elements/` | 020 FR-006/008 | ✅ `AmbiguousElements` |
| Icon-only / no stable locator → image fallback | `probes/no-stable-locator/` | 020 FR-008 | ✅ `NoStableLocator` |
| Stable vs. dynamic value (capture discipline) | `probes/stable-vs-dynamic/` | 020 FR-006/009 | ✅ `StableVsDynamic` |
| Async loading → wait-on-state, not sleep | `probes/async-loading/` | 020 FR-006 | ✅ `AsyncLoading` |
| Responsive breakpoint (viewport-alignment guard) | `probes/responsive-breakpoint/` | 020 FR-008 | ✅ `ResponsiveBreakpoint` |
| Iframe-embedded content (HTTP-served) | `probes/iframe/` | 020 FR-008 | ✅ `Iframe` |
| Deterministic-but-moving target → best-effort/image | `probes/moving-element/` | 020 FR-008 | ✅ `MovingElement` |

## Serving

All pages open via `file://` with relative links — no server needed — **except**
`probes/iframe/`, which needs a real HTTP origin for cross-frame access and ships
its own Playwright `webServer` (`python3 -m http.server`). See the top-level
`tests/authoring-eval/README.md` for run recipes.

## Determinism contract

- The journey landing page has **no login form**; the actionable path spans ≥3
  pages via non-obvious links buried in realistic noise.
- Dynamic values (timestamps, tickers, moving positions, per-load counters) are
  the *only* things that change between reloads/contexts, and they change
  reproducibly (seeded, or from a `localStorage` counter).
- Consent / first-visit dialogs are gated on `localStorage`, so a fresh
  Playwright context (the default per test) deterministically sees "first visit".
