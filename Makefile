# Owner shortcuts. Run from the repository root.

.PHONY: secrets-plan secrets-inventory rotate-secrets dagster

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
