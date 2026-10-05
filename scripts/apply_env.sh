#!/bin/sh
# Make a cafe that already has a database use the passwords in .env, without wiping anything.
# Run it after scripts/make_env.py when you want to keep your pieces, votes and replies:
#
#     sh scripts/apply_env.sh                          # your own machine
#     sh scripts/apply_env.sh compose-deployment.yml   # on the server
#
# It sets the database password and the admin login to what .env says, then starts the site.
set -e
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f ${1:-compose.yml}"

$COMPOSE up -d db

# Inside its own container the database trusts local connections, so the old password is not needed.
$COMPOSE exec -T db sh -c '
    until pg_isready -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do sleep 1; done
    echo "ALTER USER \"$POSTGRES_USER\" PASSWORD :'"'"'pw'"'"';" \
        | psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v pw="$POSTGRES_PASSWORD"
'
echo "Database password now matches .env."

$COMPOSE up -d --build

$COMPOSE exec -T footballcafe python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
name = os.environ['DJANGO_SUPERUSER_USERNAME']
user, _ = get_user_model().objects.get_or_create(username=name, defaults={'is_staff': True, 'is_superuser': True})
user.set_password(os.environ['DJANGO_SUPERUSER_PASSWORD'])
user.save()
print('Admin login', name, 'now uses the password in .env.')
" | tail -1
