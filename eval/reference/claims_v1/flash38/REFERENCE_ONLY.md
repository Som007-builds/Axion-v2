# Reference comparison — NOT baseline, NOT silver

Run `p1-10-ref-flash38-s20261114-n5`: the first 5 seeded papers, once, on
`gemini-3.8-flash` with the baseline prompt and config (thinking `default`,
temperature 0.0, max output 16,384, prompt `claim-extraction-v1`).

Owner decision (ADR-0019): this is a **reference comparison only**. It is

- **not** the P1 baseline (that is `gemini-3.5-flash-lite`, run
  `p1-10-flashlite-s20261114-n100`),
- **not** silver training data — do not train on these claims,
- **not** an evaluation set and not a quality verdict: 5 papers is a small,
  non-random subset.

The generated `silver_manifest.json` in this folder is the runner's default
schema and therefore says `label_kind: silver` / `usable_for: [student_training]`.
That provenance does **not** apply to this folder; treat every claim here as
reference-only. Nothing ingests this directory.

Headline numbers (`run_report.md`):

- 74 claims, 0 failures, 100% evidence-span verbatim
- 28,087 prompt / 22,073 completion tokens, of which 9,177 were thinking
- list price $0.103838 ($0.001403 per claim; 1.9× the Flash-Lite baseline)
- latency mean 196.6 s, p95 291.0 s (≈30× the baseline); 17 of 18 daily requests
