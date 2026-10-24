# The Railway `dagster` service (openspec/changes/dagster-railway). Railway setting:
# RAILWAY_DOCKERFILE_PATH=orchestration/Dockerfile, built from the repository root.
# Only the data environment (requirements-data.txt): never the web app's, whose
# protobuf 5 pin conflicts with dbt's protobuf 6.
FROM python:3.13-slim

# Railway passes its build identifiers only to ARGs declared here. The attestation binds
# the image to this service, environment and commit (app/runtime_env.py); without them
# the build fails.
ARG RAILWAY_SERVICE_ID
ARG RAILWAY_ENVIRONMENT_ID
ARG RAILWAY_PROJECT_ID
ARG RAILWAY_GIT_COMMIT_SHA

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DAGSTER_HOME=/app/.dagster_home
WORKDIR /app

COPY requirements-data.txt ./
RUN python -m venv .venv-data && .venv-data/bin/pip install --no-cache-dir -r requirements-data.txt

# Only what a run needs: the gate, the loader, the dbt project and the definitions.
COPY app/__init__.py app/runtime_env.py app/runtime_state.py app/runtime_db.py app/
COPY pipelines/ pipelines/
COPY warehouse/ warehouse/
COPY orchestration/ orchestration/
COPY ops/write_build_attestation.py ops/

RUN .venv-data/bin/python ops/write_build_attestation.py \
    && mkdir .dagster_home && cp orchestration/dagster.production.yaml .dagster_home/dagster.yaml \
    && useradd --system --no-create-home --home-dir /app dagster \
    && chown -R dagster .dagster_home warehouse

USER dagster
CMD [".venv-data/bin/python", "-m", "orchestration.production"]
