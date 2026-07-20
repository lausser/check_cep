# Worked examples (few-shot exemplars)

Hand-written, **proven** (intent → ideal test) pairs that anchor the authoring
skill. Each is a faithful copy of a golden pair under
`tests/authoring-eval/golden/` and passes deterministically against the eval
sample app (see each pair's `VERIFICATION.md`).

Read these to learn the target shape of a good authored test:

- **`MultiPageJourney/`** — the flagship. A realistic multi-page distraction
  journey (busy landing → non-obvious "Online Banking" entry → interstitial →
  login wall → dashboard). Shows: targeting non-obvious elements by stable ids
  amid noise, a login flow, business-named `test.step()`s, capturing a stable
  value as perfdata, and **never** asserting a dynamic value (the "Last login"
  timestamp).

- **`StableVsDynamic/`** — everyday value-capture discipline. Asserts the stable
  identity literally, captures the balance as perfdata
  (`NagiosPerfData: 'Label'=value`), and leaves the ticking session clock
  captured-but-unasserted.

> The `functions/index.ts` in each example resolves the shared sample app by
> relative path for offline verification in the repo. In a real deployed package
> the pages travel alongside the test. These copies are teaching references —
> the authoritative, verified copies live in `tests/authoring-eval/golden/`.
