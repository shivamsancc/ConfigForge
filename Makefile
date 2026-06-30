# ConfigFoundry — developer convenience targets
# Requires: python3, node, npm

.PHONY: help dev-backend dev-frontend dev install-frontend build serve clean

help:
	@echo ""
	@echo "  make install-frontend   Install Node dependencies (frontend/)"
	@echo "  make dev                Run backend + frontend dev servers in parallel"
	@echo "  make dev-backend        Run FastAPI on :8420 only"
	@echo "  make dev-frontend       Run Next.js dev server on :3001 only"
	@echo "  make build              Build Next.js static output → frontend/out/"
	@echo "  make serve              Build frontend + start FastAPI (single-port production)"
	@echo "  make clean              Remove Next.js build artefacts"
	@echo ""

# ── install ──────────────────────────────────────────────────────────────────

install-frontend:
	cd frontend && npm install

# ── development ──────────────────────────────────────────────────────────────

dev-backend:
	python3 server.py

dev-frontend:
	cd frontend && npm run dev

# Run both in parallel (requires GNU make or a POSIX shell that supports &)
dev:
	@echo "Starting backend on :8420 and Next.js dev server on :3001…"
	@trap 'kill 0' INT; \
	  python3 server.py & \
	  (cd frontend && npm run dev) & \
	  wait

# ── production ───────────────────────────────────────────────────────────────

build:
	cd frontend && npm run build

# Build the static frontend, then start FastAPI — everything on one port.
serve: build
	python3 server.py

# ── clean ────────────────────────────────────────────────────────────────────

clean:
	rm -rf frontend/.next frontend/out
