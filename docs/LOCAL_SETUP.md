# Local setup (Day 0)

This is the minimal local stack for the foundation phase: **Neo4j only**. Redis, workers, and the API are intentionally deferred.

## Prerequisites

- Python 3.11 (the project requires `>=3.11,<3.12`).
- Docker Desktop with Docker Compose v2.
- A local `.env` copied from `.env.example` and filled in. Never commit it.
- `NEO4J_PASSWORD` set to a non-empty password (Neo4j rejects the default `neo4j` password).
- `NEO4J_URI=bolt://127.0.0.1:7888` to match the Compose port mapping.

## Start and stop

From the repository root:

```bash
docker compose up -d
docker compose ps
```

The browser UI is on `http://127.0.0.1:7475`; Bolt is on `127.0.0.1:7888`. Both bindings are loopback-only. Data and logs live in the named volumes `neo4j_data` and `neo4j_logs`.

Stop the container without deleting data:

```bash
docker compose down
```

Delete the local database as well (destructive):

```bash
docker compose down -v
```

V1's Neo4j uses host ports 7474/7887; V2 uses 7475/7888, so both stacks can run side by side. Never point V2 at V1's data volumes or reuse V1's credentials — V2 needs its own database and schema.

## Checks

Run the offline Day-0 checks (no network, no secret values printed):

```bash
make day0-check
```

On a host without GNU `make`, use:

```bash
python scripts/day0_check.py
```

To include the opt-in Europe PMC and Crossref reachability checks, populate both contact-email variables in `.env` and run:

```bash
python scripts/day0_check.py --network
```

The network checks send only a polite `User-Agent`/`mailto` contact; they never send API keys or other secrets. Neo4j is checked when `NEO4J_URI` is configured and the service is running; otherwise the check reports `SKIP`.

## Pre-commit

Run every hook on the working tree before a commit:

```bash
.venv/Scripts/pre-commit.exe run --all-files
```

**On this Windows host, use Python 3.12 for the hooks.** The project venv (3.11)
cannot build pre-commit hook environments: its base interpreter lives at `D:\`,
and virtualenv fails with `ValueError: 'D:\Scripts' is not in the subpath of
...py_env-python3.11`. Hook environments built by the system 3.12 work, and the
`secret-scan` hook runs `scripts/check_secrets.py` (stdlib only) inside such an
environment instead of the host's broken bare `python`. Install once, then run:

```bash
py -3.12 -m pre_commit install --install-hooks
py -3.12 -m pre_commit run --all-files
```

CI (Ubuntu) uses the job interpreter and needs none of this. Do not skip hooks.
If the secret scan has to be run by hand, the exact equivalent is:

```bash
.venv/Scripts/python.exe scripts/check_secrets.py
```

## P1 stores (Neo4j schema v2 + Chroma)

The corpus loader needs the optional store packages and a running Neo4j. Keep
the default install small; add the extras only when loading:

```bash
# CPU-only PyTorch first. Do not let sentence-transformers pull a CUDA build.
python -m pip install "torch==2.5.1" --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e ".[store,embeddings]"
```

Then start Neo4j and load the ID-only manifest twice:

```bash
docker compose up -d
python scripts/load_stores.py --manifest docs/reports/P1-corpus-manifest.json --twice
```

`--twice` fails if the second load changes any graph or vector count. Use
`--embedder hash` for a dependency-free plumbing check; it is not a semantic
model. The real local embedder is `sentence-transformers/all-MiniLM-L6-v2`
(384-d, CPU) and is selected with `--embedder sentence-transformers`.
`--in-memory` runs the full loader without Docker or Chroma and is useful for a
smoke test.

### Verified environment facts (2026-11-14)

- **Use the venv interpreter explicitly on this host:** `.venv/Scripts/python.exe`.
  The bare `python` on PATH resolves to a `D:\` shim whose venv launcher fails
  with `No pyvenv.cfg file`; pre-commit hooks that call `python` fail for the
  same reason unless the venv `Scripts` directory is first on PATH.
- **Neo4j 5.18 memory settings are verified**, not assumed: after
  `docker compose up -d --force-recreate neo4j`,
  `CALL dbms.listConfig()` reports heap initial `512.00MiB`, heap max `1.00GiB`,
  and page cache `512.00MiB`. The env names are therefore correct for the
  pinned image.
- **Host resources at verification time:** 15.6 GB RAM; 134.3 GB free on `D:`
  (repository/work drive); 9.1 GB free on `C:`. Docker Desktop uses the WSL2
  backend and **no `C:\Users\<you>\.wslconfig` exists yet**; the cap below is
  guidance until the owner creates it and runs `wsl --shutdown`.
- **Chroma telemetry is disabled** in the adapter. With the pinned
  `chromadb==0.6.3` the bundled telemetry client logs a posthog API mismatch
  on every collection creation; it does not affect the load.
- **One ingest at a time.** The checkpoint directory is shared state. Before
  starting a run, check for a stale `scripts/ingest_corpus.py` process from an
  earlier session; two concurrent runs duplicate requests and interleave
  checkpoint appends. Stop only the exact stale PID, never by name pattern.
- The CPU semantic stack is installed and verified (2026-11-15): torch
  `2.5.1+cpu` with CUDA unavailable, sentence-transformers `3.3.1`, and
  `sentence-transformers/all-MiniLM-L6-v2` (384-d, L2-normalized). The HF cache
  was set to `D:/hf-cache` and the pip cache to `D:/pip-cache`. The full store
  load used `--embedder sentence-transformers`. The hash embedder remains a
  deterministic offline plumbing option only.
- **Measured P1 store sizes:** JATS raw cache 801 MB on disk (644 MiB of file
  bytes), Chroma `data/chroma-full` 53 MB, Neo4j named volume 545 MB. Docker
  Desktop stores its data in WSL (`/var/lib/docker`) on `C:`, which had only
  **8.6 GB free** at verification time; the Neo4j volume is the part that grows
  on `C:` and needs monitoring.

### Memory and disk caps

`docker-compose.yml` caps Neo4j at a 1 GB heap and a 512 MB page cache using
the Neo4j 5 environment-variable naming scheme (dots become `_`; literal
underscores become `__`):

- `NEO4J_server_memory_heap_initial__size=512m`
- `NEO4J_server_memory_heap_max__size=1G`
- `NEO4J_server_memory_pagecache_size=512m`

On Windows, Docker Desktop normally uses the WSL2 backend. Cap the whole WSL2
VM in `C:\Users\<you>\.wslconfig` so Neo4j and the Python process cannot take
the laptop's entire RAM:

```ini
[wsl2]
memory=8GB
processors=4
swap=2GB
```

Apply it with `wsl --shutdown`, then restart Docker Desktop. On a 16 GB laptop,
leave at least half the host RAM outside WSL2.

The measured P1 stack is about **1.4 GB**: 801 MB of untracked JATS cache,
53 MB of Chroma persistence, and a 545 MB Neo4j volume (plus the Python
environment). The exact ingest usage is in `docs/reports/P1-corpus.md`; raw
full text and Chroma persistence stay under `data/` and are never committed.

## Files

- `docker-compose.yml` — Neo4j 5.x, healthcheck, memory caps, loopback ports, environment password, named volumes.
- `.env.example` — names only, with blank secret values.
- `scripts/day0_check.py` — Python, Docker, env-name, Neo4j, and opt-in API checks.
- `scripts/ingest_corpus.py` — resumable corpus ingest and ID-only manifest.
- `scripts/load_stores.py` — idempotent Neo4j/Chroma loader (`--twice` check).
