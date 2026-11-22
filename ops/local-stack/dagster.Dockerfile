# Local stack only: a thin development layer on orchestration/Dockerfile (the image Railway
# builds for `dagster`). Never used by Railway. Policy and profile: as in python.Dockerfile.
# Run history lives in DAGSTER_HOME=/app/.dagster_local (a named volume, SQLite), so each
# machine keeps its own and never shares a run queue through the shared dev database.
# APP_UID: the host user's uid (ops/local_stack.py), so the read-only mounted .env.local (mode
# 600) is readable on Linux, where bind mounts keep the host owner.
ARG BASE
FROM ${BASE}
ARG APP_UID=1000
USER root
RUN usermod -u ${APP_UID} dagster \
    && chown -R dagster /app/.dagster_home /app/warehouse \
    && install -d -o root -g root -m 0755 /etc/bizqlab \
    && install -o dagster -g dagster -m 0600 /dev/null /app/.env.local \
    && install -d -o dagster -g dagster -m 0700 /app/.dagster_local
COPY --chown=root:root --chmod=0644 db-policy.json /etc/bizqlab/db-policy.json
COPY --chown=root:root --chmod=0755 bizqlab-dev-start /usr/local/bin/bizqlab-dev-start
ENV BIZQLAB_PROFILE=/app/.env.local DAGSTER_HOME=/app/.dagster_local
USER dagster
