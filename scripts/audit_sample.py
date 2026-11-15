"""Draw the P1-11 audit sample and write the labelling template.

Usage:
    python scripts/audit_sample.py --claims data/claims.jsonl \
        --out eval/audit/claims_audit_v1.csv

The export leaves every label field blank: the owner labels it, the agent does
not. Seed and corpus snapshot id are printed and must be recorded with the
audit. No network access and no LLM calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from axion.eval.audit import (
    DEFAULT_SEED,
    MAX_CLAIMS_PER_PAPER,
    MIN_PAPERS,
    MIN_SAMPLE,
    OVERLAP_FRACTION,
    AuditError,
    assign_paper_splits,
    corpus_snapshot_id,
    export_rows,
    load_claims,
    sample_claims_by_paper,
    select_overlap_rows,
    write_export,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=Path, required=True, help="candidate-claim JSONL")
    parser.add_argument(
        "--out", type=Path, default=Path("eval/audit/claims_audit_v1.csv"), help="export CSV"
    )
    parser.add_argument("--sample-size", type=int, default=MIN_SAMPLE)
    parser.add_argument(
        "--max-per-paper",
        type=int,
        default=MAX_CLAIMS_PER_PAPER,
        help="cap on claims drawn from one paper (default 5)",
    )
    parser.add_argument(
        "--min-papers",
        type=int,
        default=MIN_PAPERS,
        help="minimum distinct papers the audit must cover (default 40)",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--allow-small",
        action="store_true",
        help="allow a sample below the rubric minimum (dry runs only)",
    )
    parser.add_argument(
        "--overlap-out",
        type=Path,
        default=None,
        help="optional second-labeler CSV with a seeded overlap subset",
    )
    parser.add_argument(
        "--overlap-fraction",
        type=float,
        default=OVERLAP_FRACTION,
        help="second-labeler overlap share (default 0.20)",
    )
    args = parser.parse_args(argv)

    try:
        claims = load_claims(args.claims)
        if args.sample_size < MIN_SAMPLE and not args.allow_small:
            raise AuditError(
                f"rubric requires at least {MIN_SAMPLE} claims; "
                f"got {args.sample_size} (use --allow-small for a dry run)"
            )
        sample = sample_claims_by_paper(
            claims,
            target_claims=args.sample_size,
            max_per_paper=args.max_per_paper,
            min_papers=args.min_papers,
            seed=args.seed,
        )
        rows = export_rows(sample, seed=args.seed)
        write_export(args.out, rows)
        overlap_rows = select_overlap_rows(rows, fraction=args.overlap_fraction, seed=args.seed)
        if args.overlap_out is not None:
            write_export(args.overlap_out, overlap_rows)
        snapshot = corpus_snapshot_id(claims)
        splits = assign_paper_splits((claim.paper_id for claim in sample), seed=args.seed)
    except AuditError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    split_counts = Counter(splits.values())
    summary = {
        "export": str(args.out),
        "seed": args.seed,
        "corpus_snapshot_id": snapshot,
        "available_claims": len(claims),
        "sampled_claims": len(sample),
        "papers": len(splits),
        "max_claims_per_paper": args.max_per_paper,
        "min_papers": args.min_papers,
        "splits": dict(split_counts),
        "rubric_version": rows[0]["rubric_version"] if rows else "",
        "overlap_claims": len(overlap_rows),
        "overlap_out": str(args.overlap_out) if args.overlap_out else None,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
