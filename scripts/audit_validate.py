"""Validate a labelled P1 audit CSV and compute the reported metrics.

Usage:
    python scripts/audit_validate.py --audit eval/audit/claims_audit_v1.csv
    python scripts/audit_validate.py --audit ... --overlap ..._overlap.csv

Validation is deliberately strict: unknown labels, missing notes on non-CORRECT
rows, and unlabelled rows are errors unless ``--allow-partial`` is used for a
work-in-progress file. After validation the existing audit metrics code
(precision, Wilson 95% CI, failure breakdown, and Cohen's kappa) is called;
nothing is guessed or filled in.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from axion.eval.audit import (
    LABELS,
    AuditError,
    compute_metrics,
    read_audit,
    render_markdown,
)


def _validate_rows(rows: list[dict[str, str]], *, allow_partial: bool) -> tuple[list[str], int]:
    errors: list[str] = []
    labelled = 0
    for row in rows:
        claim_id = row.get("claim_id", "?")
        label = (row.get("label") or "").strip()
        note = (row.get("note") or "").strip()
        relabel = (row.get("relabel_label") or "").strip()
        if not label:
            if not allow_partial:
                errors.append(f"{claim_id}: missing label")
            continue
        labelled += 1
        if label not in LABELS:
            errors.append(f"{claim_id}: unknown label {label!r}")
        if label != "CORRECT" and not note:
            errors.append(f"{claim_id}: note required for {label}")
        if relabel and relabel not in LABELS:
            errors.append(f"{claim_id}: unknown relabel_label {relabel!r}")
    return errors, labelled


def _merge_overlap(
    rows: list[dict[str, str]], overlap_path: Path, *, allow_partial: bool
) -> list[str]:
    overlap_rows = read_audit(overlap_path)
    errors, _ = _validate_rows(overlap_rows, allow_partial=allow_partial)
    if errors:
        return [f"overlap: {error}" for error in errors]
    by_id = {row.get("claim_id", ""): row for row in overlap_rows}
    primary_ids = {row.get("claim_id", "") for row in rows}
    extra = [claim_id for claim_id in by_id if claim_id not in primary_ids]
    if extra:
        errors.append(
            "overlap CSV contains claim ids not in the primary audit: " + ", ".join(extra[:5])
        )
    for row in rows:
        other = by_id.get(row["claim_id"])
        if other is None:
            continue
        label = (other.get("label") or "").strip()
        if not label:
            if not allow_partial:
                errors.append(f"{row['claim_id']}: overlap row is unlabelled")
            continue
        if (row.get("relabel_label") or "").strip():
            errors.append(f"{row['claim_id']}: relabel_label already filled")
            continue
        row["relabel_label"] = label
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True, help="primary audit CSV")
    parser.add_argument(
        "--overlap",
        type=Path,
        default=None,
        help="optional second-labeler CSV; labels are merged into relabel_label",
    )
    parser.add_argument("--out", type=Path, help="write the metrics Markdown")
    parser.add_argument("--json", action="store_true", help="print metrics JSON")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="allow blank labels in a work-in-progress audit",
    )
    args = parser.parse_args(argv)

    try:
        rows = read_audit(args.audit)
        errors, labelled = _validate_rows(rows, allow_partial=args.allow_partial)
        if args.overlap is not None:
            errors.extend(_merge_overlap(rows, args.overlap, allow_partial=args.allow_partial))
    except (AuditError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"invalid: {error}", file=sys.stderr)
        return 2
    if labelled == 0:
        print("validated: 0 labelled rows (partial audit; no metrics computed)")
        return 0

    try:
        metrics = compute_metrics(rows)
    except AuditError as exc:
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
        breakdown = metrics["breakdown"]
        assert isinstance(breakdown, dict)
        print("breakdown: " + ", ".join(f"{label}={breakdown[label]}" for label in LABELS))
        agreement = metrics["agreement"]
        if isinstance(agreement, dict):
            print(
                f"agreement: n={agreement['n']} raw={float(agreement['raw_agreement']):.4f} "
                f"kappa={float(agreement['kappa']):.4f}"
            )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            render_markdown(metrics, source=f"--audit {args.audit}"), encoding="utf-8"
        )
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
