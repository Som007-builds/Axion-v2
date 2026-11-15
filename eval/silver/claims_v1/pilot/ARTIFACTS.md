# P1-10 pilot silver artifacts

Run `p1-10-pilot-s20261114-n5`, teacher `openai/gpt-oss-120b`, prompt
`claim-extraction-v1`, seed `20261114`. This is a **silver** pilot: it is
training/plumbing only, never evaluation data.

The raw JSONL files contain article text excerpts and stay local (ignored by
git). The manifest and reports below are tracked so the run can be audited
without redistributing the excerpts.

| File | SHA-256 | Bytes |
| :-- | :-- | --: |
| `candidates.jsonl` | `22dce5908f00818135c750b526b44f8b411d4d1460e102a4b77903e904034e2a` | 55,643 |
| `silver_claims.jsonl` | `aa10a98be45f9fbe9bfab19889ee11ab2c35e76fc5d71d9cc932c5c494580be1` | 16,241 |
| `failures.jsonl` | `9b23a20884000c34a2db5a9ab458f08be4f76423d8c0a3baf2078dffa9f28bdc` | 2,452 |
| `papers_processed.jsonl` | `51c3f10f359bb9906c7876a58184e02ca3ec58ea7d7cf841ece5d471ccc1ad83` | 92 |
| `run_report.json` | `c31810613a05b4aa2d3b8cb033219d891265584e9da767c74a4c888dfbea5402` | 1,405 |
| `run_report.md` | `134544fdf9e613f7318e3c1ee6b7ea98e7468740365ae695c51bab0c47368cc9` | 1,316 |
| `estimate.json` | `c942248066277c1922101b4752e6518217bf0526af07cdf34b17962c9c7fa818` | 1,244 |
| `estimate.md` | `38cc2128fb3f19b3348bcadd8155054ef578b7cc6f1d09b974e5ce18e48e6662` | 1,959 |
| `silver_manifest.json` | `7ded6933226e5d59b62c5b846f10b2c9ce6eb0a31d9bd2b3a25cf8c530f20436` | 786 |

Regenerate only with an approved paid run; a new run will have different
teacher output and therefore different hashes:

```powershell
$env:AXION_DRY_RUN = "false"
$env:GROQ_API_KEY = "<set locally, never commit>"
python scripts/run_baseline_extraction.py --execute --sample 5 `
  --seed 20261114 --run-id p1-10-pilot-s20261114-n5
```

The pilot stopped after one paper because the next request needed 12,111 tokens
against Groq's free-tier limit of 8,000 tokens per minute. See
`docs/reports/P1-baseline-pilot.md`.
