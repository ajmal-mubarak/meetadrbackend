#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements/base.txt
python manage.py collectstatic --no-input
python manage.py migrate

# Seed demo test data if requested
if [ "$SEED_DEMO_DATA" = "true" ]; then
    python seed_local_db.py
fi
