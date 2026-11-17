#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# Seed demo test data if requested (safe-guarded against already-seeded tables)
if [ "$SEED_DEMO_DATA" = "true" ]; then
    python seed_local_db.py || true
fi
