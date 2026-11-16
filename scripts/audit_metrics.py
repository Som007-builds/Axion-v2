"""Compute P1-11 audit metrics from a labelled CSV.

Usage:
    python scripts/audit_metrics.py --audit eval/audit/claims_audit_v1.csv \
        --out docs/reports/P1-audit.md

Numbers are computed from the labels present in the file; nothing is invented.
Rows with a blank ``label`` are counted as unlabelled and excluded. The report
includes precision, a Wilson 95% CI, the failure breakdown, and (once filled)
a >=7-day relabel agreement with Cohen's kappa.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from axion.eval.audit import AuditError, compute_metrics, read_audit, render_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True, help="labelled audit CSV")
    parser.add_argument("--out", type=Path, help="write a Markdown report")
    parser.add_argument("--json", action="store_true", help="print metrics as JSON")
    args = parser.parse_args(argv)

    try:
        metrics = compute_metrics(read_audit(args.audit))
    except (AuditError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
    else:
        overall = metrics["overall"]
        assert isinstance(overall, dict)
        print(
            f"n={overall['n']} precision={float(overall['precision']):.4f} "
            f"CI=[{float(overall['ci_low']):.4f}, {float(overall['ci_high']):.4f}]"
        )
        print(f"unlabelled={metrics['unlabelled']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            render_markdown(
                metrics, source=f"python scripts/audit_metrics.py --audit {args.audit}"
            ),
            encoding="utf-8",
        )
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
