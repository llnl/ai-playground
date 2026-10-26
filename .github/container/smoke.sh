#!/bin/bash
set -euo pipefail

repository_root=$(pwd)
container_name="ai-playground-smoke-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"

cleanup() {
    docker logs "$container_name" || true
    docker rm --force "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --detach --name "$container_name" \
    --user 1001230000:0 \
    --publish 127.0.0.1::8000 \
    --volume "$repository_root/.github/container/smoke_settings.py:/app/container_smoke_settings.py:ro" \
    --env HOME=/ \
    --env PYTHONPATH=/app:/app/src \
    --env DJANGO_SETTINGS_MODULE=container_smoke_settings \
    --env SECRET_KEY=ci-only-not-a-deployment-secret \
    --env DB_NAME=smoke \
    --env DB_USER=smoke \
    --env DB_PASSWORD= \
    --env DB_HOST=unused \
    --env DB_PORT=5432 \
    --env DEBUG=false \
    --env PROXY_AUTH_ENABLED=true \
    --env RUN_MIGRATIONS=true \
    --env RUN_COLLECTSTATIC=true \
    ai-playground:ci

address=$(docker port "$container_name" 8000/tcp)
url="http://$address"

request() {
    local path="$1"
    shift
    curl --fail --silent --show-error --max-time 10 \
        --header 'X-Wormhole-Host: smoke.example.org' \
        --header 'X-Wormhole-Scheme: https' \
        --header 'X-Forwarded-Host: internal.example.org:8000' \
        --header 'X-Forwarded-Proto: http' \
        --header 'X-Forwarded-User: container-smoke-user' \
        "$@" "$url$path"
}

ready=false
for ((attempt = 0; attempt < 60; attempt++)); do
    if request / >/dev/null 2>&1; then
        ready=true
        break
    fi
    if [[ $(docker inspect --format '{{.State.Running}}' "$container_name") != true ]]; then
        break
    fi
    sleep 2
done
if [[ "$ready" != true ]]; then
    echo 'Container did not become ready.' >&2
    exit 1
fi

stylesheet=$(request /static/css/main.css)
[[ "$stylesheet" == *base.css* ]]
request /static/css/components/navbar.css >/dev/null

catalog=$(request '/apps/cards/all/?category=mcp_server')
[[ -n "$catalog" ]]

login_status=$(request '/accounts/login/?next=/apps/cards/all/' --output /dev/null --write-out '%{http_code}')
[[ "$login_status" == 302 ]]

direct_status=$(curl --silent --show-error --max-time 10 --output /dev/null --write-out '%{http_code}' "$url/")
[[ "$direct_status" == 400 ]]

echo 'Container smoke test passed: arbitrary UID, migrations, CSS, proxy login, and origin enforcement.'
