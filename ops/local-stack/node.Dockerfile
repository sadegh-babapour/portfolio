# Local stack only: a thin development layer on the Railpack image of backend/transit_api
# (the same image Railway builds for `transit-api`). Never used by Railway.
#
# In development the Node gate (backend/transit_api/config/runtimeEnv.js) reads .env.local two
# folders above the service and requires scripts/bootstrap_transit_db.py there as proof of a
# repository layout. Railpack puts the service at /app, so this layer moves it to
# /repo/backend/transit_api and adds that file. Policy and user: as in python.Dockerfile.
# APP_UID: the host user's uid (ops/local_stack.py), so the read-only mounted .env.local (mode
# 600) is readable on Linux, where bind mounts keep the host owner.
ARG BASE
FROM ${BASE}
ARG APP_UID=1000
USER root
RUN install -d -o root -g root -m 0755 /etc/bizqlab /repo /repo/backend /repo/scripts \
    && mv /app /repo/backend/transit_api \
    && useradd --uid ${APP_UID} --user-group --no-create-home --home-dir /repo bizqlab \
    && install -o bizqlab -g bizqlab -m 0600 /dev/null /repo/.env.local \
    && install -d -o bizqlab -g bizqlab -m 0700 /tmp/bizqlab-home
COPY --chown=root:root --chmod=0644 bootstrap_transit_db.py /repo/scripts/bootstrap_transit_db.py
COPY --chown=root:root --chmod=0644 db-policy.json /etc/bizqlab/db-policy.json
COPY --chown=root:root --chmod=0755 bizqlab-dev-start /usr/local/bin/bizqlab-dev-start
WORKDIR /repo/backend/transit_api
# HOME: Railpack's mise wants to write state there.
ENV BIZQLAB_PROFILE=/repo/.env.local HOME=/tmp/bizqlab-home
USER bizqlab
