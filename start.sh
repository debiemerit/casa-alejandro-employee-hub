#!/bin/sh
set -eu
flask --app app init-db
exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 2 --timeout 60 app:app
