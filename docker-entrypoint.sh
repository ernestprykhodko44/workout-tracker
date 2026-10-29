#!/bin/sh
set -e
# Named volumes often mount as root; fix ownership for UID 1000 app user.
mkdir -p /app/data
if [ "$(id -u)" = "0" ]; then
  chown -R app:app /app/data
  exec gosu app "$@"
fi
exec "$@"
