# Local setup (Day 0)

This is the minimal local stack for the foundation phase: **Neo4j only**. Redis, workers, and the API are intentionally deferred.

## Prerequisites

- Python 3.11 (the project requires `>=3.11,<3.12`).
- Docker Desktop with Docker Compose v2.
- A local `.env` copied from `.env.example` and filled in. Never commit it.
- `NEO4J_PASSWORD` set to a non-empty password (Neo4j rejects the default `neo4j` password).
- `NEO4J_URI=bolt://127.0.0.1:7887` to match the Compose port mapping.

## Start and stop

From the repository root:

```bash
docker compose up -d
docker compose ps
```

The browser UI is on `http://127.0.0.1:7474`; Bolt is on `127.0.0.1:7887`. Both bindings are loopback-only. Data and logs live in the named volumes `neo4j_data` and `neo4j_logs`.

Stop the container without deleting data:

```bash
docker compose down
```

Delete the local database as well (destructive):

```bash
docker compose down -v
```

Do not run this stack and an old V1 Neo4j container at the same time: both try to own ports 7474 and 7887. Stop the V1 container first, and never point V2 at V1's data volumes.

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

## Files

- `docker-compose.yml` — Neo4j 5.x, healthcheck, loopback ports, environment password, named volumes.
- `.env.example` — names only, with blank secret values.
- `scripts/day0_check.py` — Python, Docker, env-name, Neo4j, and opt-in API checks.
