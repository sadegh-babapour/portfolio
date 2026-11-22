# Local stack only: a thin development layer on the Railpack image of the repository root
# (the same image Railway builds for `portfolio` and `transit-poller`). Never used by Railway.
#
# - The DB policy is copied in as root (it holds no password). A mounted policy can't be
#   trusted under Colima, and as root the gate refuses because /etc is writable by root.
# - The service runs as an unprivileged user, with an empty profile it fills at start
#   (bizqlab-dev-start) from the read-only mounted .env.local.
# APP_UID: the host user's uid (ops/local_stack.py), so the read-only mounted .env.local (mode
# 600) is readable on Linux, where bind mounts keep the host owner.
ARG BASE
FROM ${BASE}
ARG APP_UID=1000
USER root
RUN install -d -o root -g root -m 0755 /etc/bizqlab \
    && useradd --uid ${APP_UID} --user-group --no-create-home --home-dir /app bizqlab \
    && install -o bizqlab -g bizqlab -m 0600 /dev/null /app/.env.local \
    && install -d -o bizqlab -g bizqlab -m 0700 /tmp/bizqlab /tmp/bizqlab/home
COPY --chown=root:root --chmod=0644 db-policy.json /etc/bizqlab/db-policy.json
COPY --chown=root:root --chmod=0755 bizqlab-dev-start /usr/local/bin/bizqlab-dev-start
# NiceGUI writes its storage in the working directory by default; /app belongs to root.
# HOME: Railpack's mise wants to write state there.
ENV BIZQLAB_PROFILE=/app/.env.local NICEGUI_STORAGE_PATH=/tmp/bizqlab/nicegui HOME=/tmp/bizqlab/home
USER bizqlab
