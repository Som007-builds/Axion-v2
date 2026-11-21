# Former name

Developed in Nov 2026 under the working name Axion V2. Renamed RetractionScope on 2026-11-21 when Axion V2 was redefined as the upgrade of the Axion V1 product. This study is frozen.

Nothing else in this repository refers to the old name in a reader-facing way; the exceptions are
recorded, with reasons, in the rename commit and in `docs/PROVENANCE.md`:

- the importable Python package (`src/axion`, imported as `axion`) and the `AXION_*` environment
  variables, kept so the frozen study's code and runtime configuration stay unchanged;
- a few absolute paths inside committed run records, which document where a past run actually
  executed and are not rewritten after the fact;
- three log lines naming the local Neo4j container as it was named on the day it was checked.
