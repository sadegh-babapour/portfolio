# Owner shortcuts. Run from the repository root.

.PHONY: secrets-plan secrets-inventory rotate-secrets

# The secret rotation runbook (offline).
secrets-plan:
	python3 ops/rotate_secrets.py plan

# Railway variable names per service, classified. Never prints a value.
secrets-inventory:
	python3 ops/rotate_secrets.py inventory

# Stage new secret values in Railway without deploying. Dry run unless APPLY=1.
rotate-secrets:
	python3 ops/rotate_secrets.py rotate $(if $(APPLY),--apply,)
