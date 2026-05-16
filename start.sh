#!/bin/sh
set -e

if [ -f /app/bgutil-pot/server/build/main.js ]; then
  echo "Starting bgutil PO token provider on :4416"
  node /app/bgutil-pot/server/build/main.js --port 4416 &
  sleep 4
  if command -v curl >/dev/null 2>&1; then
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      if curl -sf "http://127.0.0.1:4416/" >/dev/null 2>&1; then
        echo "bgutil PO provider is ready"
        break
      fi
      sleep 1
    done
  fi
fi

cd /app/backend
exec gunicorn app:app --bind "0.0.0.0:${PORT:-5000}" --workers 1 --threads 8 --timeout 300
