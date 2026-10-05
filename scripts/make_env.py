#!/usr/bin/env python3
"""Write a .env with strong random secrets for Football Cafe.

    python3 scripts/make_env.py                        # for your own machine
    python3 scripts/make_env.py --ip 203.0.113.7 --port 30082   # for a server reached by IP (plain http)
    python3 scripts/make_env.py --domain cafe.example           # for a server behind an https address
    python3 scripts/make_env.py --force                # replace an existing .env (keeps your API key)

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
    parser = argparse.ArgumentParser(description='Write a .env with strong random secrets.')
    parser.add_argument('--ip', help="Your server's public IP. Server settings, plain http.")
    parser.add_argument('--port', default='30082', help='Public port on the server (with --ip). Default 30082.')
    parser.add_argument('--domain', help='Your site address, e.g. cafe.example.com. Server settings, https.')
    parser.add_argument(
        '--force', action='store_true', help='Replace an existing .env. The old one is kept as .env.backup.'
    )
    parser.add_argument('--output', default=str(ROOT / '.env'), help='Where to write it (default: .env).')
    args = parser.parse_args()

    target = Path(args.output)
    old = {}
    if target.exists():
        if not args.force:
            print(f'{target} already exists. Run again with --force to replace it (your API key is kept).')
            return 1
        old = read_env(target)
        shutil.copy(target, target.with_name(target.name + '.backup'))

    if args.ip and args.domain:
        parser.error('Give --ip or --domain, not both.')
    server = bool(args.ip or args.domain)
    admin_password = secrets.token_urlsafe(12)
    if args.domain:
        hosts, origins, address = args.domain, f'https://{args.domain}', f'https://{args.domain}'
    elif args.ip:
        hosts, origins, address = args.ip, f'http://{args.ip}:{args.port}', f'http://{args.ip}:{args.port}'
    else:
        hosts, origins = 'localhost,127.0.0.1,0.0.0.0', 'http://localhost:8010,http://127.0.0.1:8010'
        address = 'http://localhost:8010'
    web_port = args.port if args.ip else old.get('WEB_PORT', '8010')

    target.write_text(f"""\
# Written by scripts/make_env.py. Keep this file out of git.

# Claude. Without a key every reply waits in your queue instead of being checked by the moderator.
ANTHROPIC_API_KEY={old.get('ANTHROPIC_API_KEY', '')}
# claude-haiku-4-5 is the cheapest and fastest model. Either agent can be given a bigger one.
CAFE_MODERATOR_MODEL={CHEAP_MODEL}
CAFE_NOTETAKER_MODEL={CHEAP_MODEL}

# Your login for /counter/. Used once, when the database is first created.
DJANGO_SUPERUSER_USERNAME=house
DJANGO_SUPERUSER_PASSWORD={admin_password}
DJANGO_SUPERUSER_EMAIL=house@example.com

# Django
DJANGO_SECRET_KEY={secrets.token_urlsafe(50)}
DEBUG={'False' if server else 'True'}
DEV={'false' if server else 'true'}
SEED_DEMO={'false' if server else 'true'}
# True only when the site is reached through an https address.
HTTPS={'True' if args.domain else 'False'}
DJANGO_LOGLEVEL=info
DJANGO_ALLOWED_HOSTS={hosts}
DJANGO_CSRF_TRUSTED_ORIGINS={origins}

# Database. The password is set when the database is first created.
DATABASE_NAME=footballcafe
DATABASE_USERNAME=footballcafe
DATABASE_PASSWORD={secrets.token_urlsafe(24)}

# Ports on your machine
WEB_PORT={web_port}
DATABASE_PUBLIC_PORT={old.get('DATABASE_PUBLIC_PORT', '5440')}
""")
    target.chmod(0o600)

    print(f'Wrote {target} ({"server" if server else "local"} settings).')
    print(f'Admin login: house / {admin_password}')
    if not old.get('ANTHROPIC_API_KEY'):
        print('Add your ANTHROPIC_API_KEY to it to switch the two agents on.')
    print()
    start = 'docker compose -f compose-deployment.yml up -d --build' if server else 'docker compose up -d --build'
    print('First time? Start the cafe:')
    print(f'    {start}')
    print(f'It will answer on {address}')
    if not server:
        print('Started it before? The old database still has the old passwords. Bring it in line, keeping your data:')
        print('    sh scripts/apply_env.sh')
    return 0


if __name__ == '__main__':
    sys.exit(main())
