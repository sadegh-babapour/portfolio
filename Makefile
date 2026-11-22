# Owner shortcuts. Run from the repository root.

.PHONY: secrets-plan secrets-inventory rotate-secrets dagster dev dev-down dev-logs dev-migrate

# The secret rotation runbook (offline).
secrets-plan:
	python3 ops/rotate_secrets.py plan

# Railway variable names per service, classified. Never prints a value.
secrets-inventory:
	python3 ops/rotate_secrets.py inventory

# Stage new secret values in Railway without deploying. Dry run unless APPLY=1.
rotate-secrets:
	python3 ops/rotate_secrets.py rotate $(if $(APPLY),--apply,)

# Dagster UI on http://127.0.0.1:3000 (this Mac only; it has no login). Runs write to PC
# portfolio_dev through the runtime gate. Run history lives in .dagster_home/ (SQLite).
dagster:
	mkdir -p .dagster_home && cp orchestration/dagster.yaml .dagster_home/dagster.yaml
	DAGSTER_HOME="$(CURDIR)/.dagster_home" .venv/bin/python ops/dev.py run --expected-db portfolio_dev -- \
		.venv-data/bin/dagster dev -m orchestration.definitions -h 127.0.0.1 -p 3000

# The local stack (compose.local.yaml, ops/local_stack.py): production's images and start
# commands on the approved dev database, every port on 127.0.0.1. Needs Docker (Colima),
# Compose, buildx and Railpack 0.43.0. POLLER=1 adds the realtime poller (it writes to the
# dev database the Railway VM shares). DEV_DB names the database the preflight must find.
DEV_DB ?= portfolio_dev
dev:
	.venv/bin/python ops/local_stack.py up --expected-db $(DEV_DB) $(if $(POLLER),--poller,)

dev-down:
	.venv/bin/python ops/local_stack.py down

dev-logs:
	.venv/bin/python ops/local_stack.py logs

# Schema only (Alembic + scripts/db), no data load. Asks for the database name first.
dev-migrate:
	.venv/bin/python ops/local_stack.py migrate --expected-db $(DEV_DB)
