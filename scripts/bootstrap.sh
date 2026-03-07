#!/usr/bin/env bash
# bootstrap.sh — one-shot environment setup for Plinth
# Run this once on a fresh clone to bring the full stack up from scratch.
# Safe to re-run; all steps are idempotent.
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${BOLD}==> $*${NC}"; }
ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
die()  { echo -e "  ${RED}✗${NC}  $*" >&2; exit 1; }

cd "$(dirname "$0")/.."   # always run from repo root

# ── 1. .env ─────────────────────────────────────────────────────────────────
log "Checking .env"
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn ".env created from .env.example — edit it and fill in real secrets before continuing."
    warn "Re-run bootstrap.sh after updating .env."
    exit 0
else
    ok ".env exists"
fi

# ── 2. uv ────────────────────────────────────────────────────────────────────
log "Checking uv"
if ! command -v uv &>/dev/null; then
    echo "  Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
ok "uv $(uv --version)"

# ── 3. Lock file ─────────────────────────────────────────────────────────────
log "Resolving dependencies"
uv lock --quiet
ok "uv.lock up to date"

# ── 4. Local staging directory ───────────────────────────────────────────────
log "Creating local staging directory"
mkdir -p staging
ok "staging/"

# ── 5. Build containers ──────────────────────────────────────────────────────
log "Building Docker images"
docker compose build --quiet
ok "Images built"

# ── 6. Start services ────────────────────────────────────────────────────────
log "Starting services"
docker compose up -d
ok "Containers started"

# ── 7. Wait for PostgreSQL ───────────────────────────────────────────────────
log "Waiting for PostgreSQL to be healthy"
RETRIES=30
until docker compose exec -T postgres \
        pg_isready -U plinth -d plinth &>/dev/null; do
    RETRIES=$((RETRIES - 1))
    [ "$RETRIES" -le 0 ] && die "PostgreSQL did not become healthy in time."
    sleep 2
done
ok "PostgreSQL healthy"

# ── 8. Wait for Prefect server ───────────────────────────────────────────────
log "Waiting for Prefect server to be healthy"
RETRIES=30
until docker compose exec -T prefect-server \
        curl -sf http://localhost:4200/api/health &>/dev/null; do
    RETRIES=$((RETRIES - 1))
    [ "$RETRIES" -le 0 ] && die "Prefect server did not become healthy in time."
    sleep 3
done
ok "Prefect server healthy"

# ── 9. Create Prefect work pool ──────────────────────────────────────────────
log "Creating Prefect work pool (plinth-pool)"
docker compose exec -T prefect-worker \
    uv run prefect work-pool create plinth-pool --type process \
    2>&1 | grep -v "already exists" || true
ok "Work pool ready"

# ── 10. Run database migrations ──────────────────────────────────────────────
log "Running database migrations"
docker compose exec -T prefect-worker uv run plinth-cli db migrate
ok "Migrations complete"

# ── 11. Initialize MinIO bucket ──────────────────────────────────────────────
log "Initializing MinIO bucket"
docker compose exec -T prefect-worker uv run plinth-cli infra init
ok "MinIO ready"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}Bootstrap complete.${NC}"
echo ""
echo "  PostgreSQL:    localhost:5432"
echo "  MinIO API:     http://localhost:9000"
echo "  MinIO Console: http://localhost:9001"
echo "  Prefect UI:    http://localhost:4200"
echo ""
echo "  Verify with:"
echo "    docker compose exec prefect-worker uv run plinth-cli db status"
