# Authoring Quality Checklist

The scorable gate evaluated before a test may be packaged. **All nine items
are binary and all must be YES.** A single NO means the test is not ready —
fix the cause, do not weaken the check to force a pass (FR-013).

The `cep_authoring` orchestrator evaluates this list at its GATE phase; a
supervised session walks it before invoking `cep_package`.

| # | Gate item | Pass when… | Ref |
|---|-----------|-----------|-----|
| 1 | **Robustness patterns** | Every interactive action on an element that could move/re-render/vary uses a sanctioned fallback (`clickBestEffort`, `clickByImageOr`/`typeByImageOr`, or an equivalent chain) — not a bespoke sleep/retry. | FR-008 |
| 2 | **Every interaction validated** | After every meaningful action the test asserts the observable consequence (navigation, element/text appeared, value present). No unasserted clicks. | FR-013 |
| 3 | **Credentials only in `.env`** | No secret appears inline, in the test, in helpers, in `README.md`, `KNOWLEDGE.md`, `VERIFICATION.md`, or the intent file. `.env` is the only place. | FR-019 |
| 4 | **Requested values emitted** | Every value in the intent's `## Values to Capture` is emitted as perfdata (`NagiosPerfData:` stdout line or a `perfdata_*` annotation). No thresholds. | FR-009 |
| 5 | **KNOWLEDGE.md updated** | New site-general findings from this session are appended to the site `KNOWLEDGE.md` (no credentials). | FR-016 |
| 6 | **Screenshots honored** | Each `@`-attached screenshot was tried as a vision template or replaced by a fresh crop; every template the test actually uses is copied into the test folder. | FR-008a |
| 7 | **Consecutive clean runs** | The required number of consecutive clean `npx playwright test` runs was achieved (default 2; recommend 3 for volatile sites). | FR-015 |
| 8 | **Critic pass / resolved** | The independent critic verdict is `pass`, or every finding it raised has been explicitly resolved. The critic also flags apparent edits to the immutable intent region (convention-based, no hash). | FR-012, FR-011 |
| 9 | **VERIFICATION.md complete** | `VERIFICATION.md` exists with all mandatory sections (Verified / Assumed / Could not verify / Deviations / Human inspection advisory), skimmable in 60 seconds. | FR-014 |

If any item is NO, the test is **not** packaged. In orchestrator mode this
consumes an iteration; the loop tries again up to the iteration cap and, if
the cap is reached without all-YES, writes a progress report and produces no
package (SC-007).
