#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    printf '%s\n' 'Applying database migrations...'
    uv run --no-sync python src/manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-false}" = "true" ]; then
    printf '%s\n' 'Collecting static files...'
    uv run --no-sync python src/manage.py collectstatic --noinput
fi

exec "$@"
