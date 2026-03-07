# Plinth

On-demand site intelligence reports for real estate professionals.

Enter a US address, pay, receive a PDF — within minutes. The report aggregates environmental risk, physical conditions, climate, solar, and demographic data from public datasets into a client-ready summary.

**Status:** Pre-development (POC phase)

---

## Stack

Python · FastAPI · PostgreSQL 15 + PostGIS · MinIO · Prefect · Docker Compose

---

## Getting Started

```bash
cp .env.example .env
# Fill in API keys and passwords

./scripts/bootstrap.sh
```

Services run on a single self-hosted Ubuntu server. See `docs/Predevelopment Checklist.md` for hardware and environment setup.

---

## Development

```bash
docker compose up -d

uv run plinth-cli --help
uv run pytest
```

See `docs/plans/` for the phased implementation plan and `docs/Plinth Requirements.md` for full product requirements.

---

## Environment Variables

See `.env.example`. Required keys: `MAPBOX_TOKEN`, `CENSUS_API_KEY`, `EPA_AQS_KEY`, `EPA_AQS_EMAIL`, `POSTGRES_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`.

`.env` is never committed.
