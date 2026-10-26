#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    printf '%s\n' 'Applying database migrations...'
    uv run --no-sync python src/manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-true}" = "true" ]; then
    printf '%s\n' 'Collecting static files...'
    uv run --no-sync python src/manage.py collectstatic --noinput
fi

exec "$@"
