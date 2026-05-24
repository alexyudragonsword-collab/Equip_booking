#!/bin/sh
set -e
# Fix ownership of the mounted data volume so the app user can write to it.
chown -R app:app /data 2>/dev/null || true
exec gosu app "$@"
