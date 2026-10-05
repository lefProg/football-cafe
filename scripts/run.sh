#!/bin/sh
set -e

python manage.py collectstatic --noinput
python manage.py migrate
python manage.py createcachetable

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput || true
fi

gunicorn --bind 0.0.0.0:8000 footballcafe.wsgi:application --workers 3 --threads 4 --timeout 60 --access-logfile - --error-logfile - --log-level info
