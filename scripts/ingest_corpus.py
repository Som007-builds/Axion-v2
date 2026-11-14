"""Ingest the P1 corpus: resumable, batched, and checkpointed.

Zero LLM cost. The committed output is an ID-only manifest bundle (papers,
cites, summary); full text stays in the untracked Europe PMC cache.

Usage:
    python scripts/ingest_corpus.py
    python scripts/ingest_corpus.py --config src/axion/config/corpus/infectious-disease.yaml

Stages checkpoint under ``data/corpus/<corpus_id>/``. Re-running after a crash,
sleep, or interrupted download resumes from the last completed batch. Europe
PMC requests are polite (1 request/second by default), and the contact email is
read from ``EUROPEPMC_CONTACT_EMAIL``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from axion.config.settings import Settings
from axion.ingest.corpus import load_corpus_config
from axion.ingest.corpus_pipeline import (
    MIN_CONTEXTS,
    MIN_SOURCES,
    IngestError,
    run_ingest,
)
from axion.ingest.europepmc import EuropePmcClient

DEFAULT_CONFIG = Path("src/axion/config/corpus/infectious-disease.yaml")
DEFAULT_RW_CSV = Path("data/retraction-watch/retraction_watch.csv")
DEFAULT_RW_MANIFEST = Path("docs/reports/P1-retraction-manifest.json")
DEFAULT_OUT_PREFIX = Path("docs/reports/P1-corpus")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--rw-csv", type=Path, default=DEFAULT_RW_CSV)
    parser.add_argument("--rw-manifest", type=Path, default=DEFAULT_RW_MANIFEST)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT_PREFIX)
    parser.add_argument(
        "--max-sources",
        type=int,
        default=None,
        help="diagnostic smoke limit; never use for the committed P1 manifest",
    )
    args = parser.parse_args(argv)

    config = load_corpus_config(args.config)
    work_dir = args.work_dir or Path("data") / "corpus" / config.corpus_id
    settings = Settings()
    client = EuropePmcClient.from_settings(settings)

    try:
        manifest = run_ingest(
            config_path=args.config,
            rw_csv_path=args.rw_csv,
            rw_manifest_path=args.rw_manifest,
            work_dir=work_dir,
            out_prefix=args.out_prefix,
            client=client,
            base_url=settings.europepmc_base_url,
            max_sources=args.max_sources,
        )
    except KeyboardInterrupt:
        print(
            "Interrupted. Checkpoints under "
            f"{work_dir} are flushed; re-run the same command to resume.",
            file=sys.stderr,
            flush=True,
        )
        return 130
    except IngestError as exc:
        print(f"ingest stopped: {exc}", file=sys.stderr, flush=True)
        return 1

    counts = manifest.counts
    print(
        f"papers={counts.papers_total:,} sources={counts.sources_total:,} "
        f"citers={counts.citers_included:,} contexts={counts.contexts_total:,}",
        flush=True,
    )
    print(f"manifest: {args.out_prefix}-manifest.json", flush=True)
    if counts.sources_total < MIN_SOURCES or counts.contexts_total < MIN_CONTEXTS:
        print(
            "BELOW CONTEXT §4 MINIMUMS: stop and propose a fallback via a new "
            "Proposed ADR; do not proceed silently.",
            file=sys.stderr,
            flush=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
