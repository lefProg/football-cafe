#!/bin/sh
set -e

python manage.py migrate
python manage.py createcachetable

# A login for /counter/ on a fresh database. Does nothing once the user exists.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput || true
fi

# One sample piece, so a fresh install has something to look at.
if [ "$SEED_DEMO" = "true" ]; then
    python manage.py seed_demo
fi

python manage.py runserver 0.0.0.0:8000
