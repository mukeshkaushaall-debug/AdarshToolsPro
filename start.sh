#!/bin/sh
set -e

if [ -f /app/bgutil-pot/server/build/main.js ]; then
  echo "Starting bgutil PO token provider on :4416"
  node /app/bgutil-pot/server/build/main.js --port 4416 &
fi

cd /app/backend
exec gunicorn app:app --bind "0.0.0.0:${PORT:-5000}" --workers 1 --threads 4 --timeout 300
