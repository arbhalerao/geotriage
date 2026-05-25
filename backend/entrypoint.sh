#!/bin/bash
set -e
if [ "${SKIP_MIGRATIONS:-false}" != "true" ]; then
    echo "Running migrations..."
    alembic upgrade head
fi

echo "Initializing object storage..."
for i in 1 2 3 4 5; do
    if python -m storage init; then
        break
    fi
    echo "  storage init attempt $i failed; retrying in 2s..."
    sleep 2
done

exec "$@"
