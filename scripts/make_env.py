#!/usr/bin/env python3
"""Write the .env for Football Cafe, with strong random secrets.

    python3 scripts/make_env.py                                 # for your own machine
    python3 scripts/make_env.py --ip 203.0.113.7 --port 30082   # for a server reached by IP (plain http)
    python3 scripts/make_env.py --domain cafe.example           # for a server with a domain (https)

If a .env is already there, add --force. Your passwords and keys are kept, so the database keeps
working; only the address settings change. --new-secrets makes new ones as well.

It only uses Python's standard library. Nothing is sent anywhere.
"""

import argparse
import secrets
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHEAP_MODEL = 'claude-haiku-4-5'


def read_env(path: Path) -> dict:
    values = {}
    for line in path.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, _, value = line.partition('=')
            values[key.strip()] = value.strip()
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description='Write the .env, with strong random secrets.')
    parser.add_argument('--ip', help="Your server's public IP. Server settings, plain http.")
    parser.add_argument('--port', help='Public port on the server (with --ip). Default 30082.')
    parser.add_argument('--domain', help='Your domain, e.g. cafe.example.com. Server settings, https.')
    parser.add_argument('--force', action='store_true', help='Replace an existing .env (kept as .env.backup).')
    parser.add_argument('--new-secrets', action='store_true', help='With --force: also make new passwords and keys.')
    parser.add_argument('--output', default=str(ROOT / '.env'), help='Where to write it (default: .env).')
    args = parser.parse_args()
    if args.ip and args.domain:
        parser.error('Give --ip or --domain, not both.')
    domain = (args.domain or '').removeprefix('https://').removeprefix('http://').removeprefix('www.').strip('/')

    target = Path(args.output)
    old = {}
    if target.exists():
        if not args.force:
            print(f'{target} already exists. Run again with --force to replace it (passwords and keys are kept).')
            return 1
        old = read_env(target)
        shutil.copy(target, target.with_name(target.name + '.backup'))

    kept = {} if args.new_secrets else old
    secret_key = kept.get('DJANGO_SECRET_KEY') or secrets.token_urlsafe(50)
    database_password = kept.get('DATABASE_PASSWORD') or secrets.token_urlsafe(24)
    admin_password = kept.get('DJANGO_SUPERUSER_PASSWORD') or secrets.token_urlsafe(12)
    new_passwords = database_password != old.get('DATABASE_PASSWORD')

    server = bool(args.ip or domain)
    if domain:
        hosts, origins, address = domain, f'https://{domain}', f'https://{domain}'
        web_port = old.get('WEB_PORT', '30082')
    elif args.ip:
        web_port = args.port or old.get('WEB_PORT', '30082')
        hosts, origins, address = args.ip, f'http://{args.ip}:{web_port}', f'http://{args.ip}:{web_port}'
    else:
        web_port = old.get('WEB_PORT', '8010')
        hosts, origins = 'localhost,127.0.0.1,0.0.0.0', f'http://localhost:{web_port},http://127.0.0.1:{web_port}'
        address = f'http://localhost:{web_port}'

    target.write_text(f"""\
# Written by scripts/make_env.py. Keep this file out of git.

# Claude. Without a key every reply waits in your queue instead of being checked by the moderator.
ANTHROPIC_API_KEY={old.get('ANTHROPIC_API_KEY', '')}
# claude-haiku-4-5 is the cheapest and fastest model. Either agent can be given a bigger one.
CAFE_MODERATOR_MODEL={old.get('CAFE_MODERATOR_MODEL', CHEAP_MODEL)}
CAFE_NOTETAKER_MODEL={old.get('CAFE_NOTETAKER_MODEL', CHEAP_MODEL)}

# Your login for /counter/. Used once, when the database is first created.
DJANGO_SUPERUSER_USERNAME=house
DJANGO_SUPERUSER_PASSWORD={admin_password}
DJANGO_SUPERUSER_EMAIL=house@example.com

# Django
DJANGO_SECRET_KEY={secret_key}
DEBUG={'False' if server else 'True'}
DEV={'false' if server else 'true'}
SEED_DEMO={'false' if server else 'true'}
DJANGO_LOGLEVEL=info
DJANGO_ALLOWED_HOSTS={hosts}
DJANGO_CSRF_TRUSTED_ORIGINS={origins}

# The address. With a domain, a Caddy container answers on ports 80 and 443, gets the https
# certificate by itself and passes visitors on to the site; the site's own port then stays private.
DOMAIN={domain}
HTTPS={'True' if domain else 'False'}
COMPOSE_PROFILES={'https' if domain else ''}
WEB_BIND={'127.0.0.1' if domain else '0.0.0.0'}
WEB_PORT={web_port}

# Database. The password is set when the database is first created.
DATABASE_NAME=footballcafe
DATABASE_USERNAME=footballcafe
DATABASE_PASSWORD={database_password}
DATABASE_PUBLIC_PORT={old.get('DATABASE_PUBLIC_PORT', '5440')}
""")
    target.chmod(0o600)

    print(f'Wrote {target} ({"server" if server else "local"} settings).')
    if old and not new_passwords:
        print('Your passwords and keys were kept. Only the address settings changed.')
    else:
        print(f'Admin login: house / {admin_password}')
    if not old.get('ANTHROPIC_API_KEY'):
        print('Add your ANTHROPIC_API_KEY to it to switch the two agents on.')
    print()
    print('Start (or restart) the cafe:')
    print(
        f'    {"docker compose -f compose-deployment.yml up -d --build" if server else "docker compose up -d --build"}'
    )
    print(f'It will answer on {address}')
    if old and new_passwords:
        print()
        print('The database you already have still uses the old passwords. Bring it in line, keeping your data:')
        print(f'    sh scripts/apply_env.sh{" compose-deployment.yml" if server else ""}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
