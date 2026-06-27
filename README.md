# Conflict Trends Dashboard — Sahel Information Environment Monitor

An interactive **geospatial dashboard** that monitors **34,681 ACLED conflict events** across the Alliance of Sahel States — **Mali, Burkina Faso, and Niger** — from **1997 to present**. It pairs a Mapbox GL JS map and time-series analytics with an automated ACLED ingestion pipeline, a FastAPI backend, and a PostgreSQL/PostGIS spatial datastore, deployed on Kubernetes.

> **About this repository.** This is an **anonymized portfolio copy** of a system I designed and built as part of my **MA research (Geopolitical Studies, Charles University)**. Live infrastructure details (hosts, domains, namespaces, credentials) have been removed, and no ACLED datasets are included — the data is licensed separately by [ACLED](https://acleddata.com) and lives in the database, not in this repo.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-REST%20API-009688?logo=fastapi&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white">
  <img alt="PostGIS" src="https://img.shields.io/badge/PostGIS-3.5-336791">
  <img alt="Mapbox" src="https://img.shields.io/badge/Mapbox%20GL%20JS-map-000000?logo=mapbox&logoColor=white">
  <img alt="Kubernetes" src="https://img.shields.io/badge/Kubernetes-deployed-326CE5?logo=kubernetes&logoColor=white">
</p>

---

## Highlights

- **Geospatial visualization** — an interactive Mapbox GL JS map of 34k+ georeferenced conflict events, backed by **PostGIS** spatial queries and bounding-box / attribute filtering.
- **Automated data engineering** — an **ACLED ingestion pipeline** (OAuth API) with a one-off **bulk historical load** and a **daily incremental CronJob**, normalizing raw events into a typed PostgreSQL schema.
- **Analytical API** — a FastAPI REST service exposing event, metadata, and filtering endpoints with **JWT authentication** (bcrypt-hashed credentials) and pooled database connections.
- **Conflict-trends analytics** — event frequency, lethality, and actor-composition explored over configurable time windows.
- **Production deployment** — fully **Dockerized** and shipped to **Kubernetes**: a PostgreSQL + PostGIS StatefulSet, the API as a Deployment behind an Ingress/TLS, and ingestion as scheduled Jobs/CronJobs.
- **Single-page frontend** — a static SPA served by the API, with the Mapbox token injected server-side (never committed to the client).

## Architecture

```
            ACLED OAuth API
                  │   bulk load (one-off)  +  daily incremental CronJob
                  ▼
        siem-ingest  (Python · click CLI)
                  │   normalize / transform
                  ▼
   PostgreSQL 17 + PostGIS 3.5   ◀── spatial + temporal store (events, actors, geometry)
                  ▲
                  │   psycopg3 + connection pool
        siem-api  (FastAPI · JWT auth)
                  │   /api/v1/events · /metadata · /auth
                  ▼
   Mapbox GL JS SPA  (interactive map + conflict-trends panel)
```

## Tech stack

| Layer | Tools |
|---|---|
| Backend API | FastAPI, Uvicorn, PyJWT, bcrypt, `psycopg` 3 (+ pool) |
| Data store | PostgreSQL 17, PostGIS 3.5 |
| Ingestion | Python, `click` CLI, `requests` (ACLED OAuth API) |
| Frontend | Mapbox GL JS, vanilla-JS SPA |
| Ops | Docker, Kubernetes (StatefulSet, Deployment, Ingress, CronJobs) |

## Repository layout

```
phase1/
  siem-api/        FastAPI backend + static Mapbox SPA (the map & API)
    src/siem_api/  auth, events, metadata, db, config, main
    static/        index.html (Mapbox GL JS frontend)
    tests/         API + DB tests
  siem-ingest/     ACLED ingestion pipeline
    src/siem_ingest/  acled_api, transform, db, cli
    tests/         transform unit tests
  deploy/
    k8s/           Kubernetes manifests (DB StatefulSet, API, Ingress, CronJobs)
    sql/           schema / init
```

## Running locally

Requires **Python 3.12** and a **PostgreSQL 17 + PostGIS 3.5** instance.

```bash
# --- API ---
cd phase1/siem-api
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
cp .env.example .env          # set DB_*, JWT_SECRET, MAPBOX_ACCESS_TOKEN
uvicorn siem_api.main:app --reload --port 8080

# --- Ingestion (separate venv) ---
cd phase1/siem-ingest
python -m venv .venv && . .venv/bin/activate
pip install -e .
cp .env.example .env          # set ACLED_EMAIL / ACLED_PASSWORD, DB_*
siem-ingest --help            # bulk load + incremental update commands
```

> The map and event endpoints expect a populated PostGIS database. The ingestion pipeline
> fetches events from the ACLED API into that database; an ACLED account is required for the
> live API (see [acleddata.com](https://acleddata.com)).

## Data & licensing

- **Conflict data:** [ACLED](https://acleddata.com) (Armed Conflict Location & Event Data). Used under ACLED's terms; **no ACLED data is redistributed in this repository.**
- **Code:** Proprietary — All Rights Reserved. Published for portfolio review only; see [`LICENSE`](LICENSE).
