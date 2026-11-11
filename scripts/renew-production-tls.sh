#!/bin/sh
set -eu

deploy_path="${DEPLOY_PATH:-/opt/social-media-agent}"
current_release="${deploy_path}/current"

if [ ! -f "${current_release}/docker-compose.yml" ] || [ ! -f "${current_release}/docker-compose.tls.yml" ]; then
    echo "The current production Compose release was not found." >&2
    exit 1
fi

exec docker compose \
    --project-name social-media-agent \
    --project-directory "$current_release" \
    --env-file "${current_release}/.env" \
    -f "${current_release}/docker-compose.yml" \
    -f "${current_release}/docker-compose.tls.yml" \
    up -d --force-recreate tls_proxy
