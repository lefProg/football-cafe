#!/usr/bin/env python3
"""Write the .env for Football Cafe, with strong random secrets.

    python3 scripts/make_env.py                        # for your own machine
    python3 scripts/make_env.py --ip 203.0.113.7       # for a server reached by IP (plain http)
    python3 scripts/make_env.py --domain cafe.example  # for a server with a domain (https)

If a .env is already there, add --force. Your passwords and keys are kept, so the database keeps
working; only the address settings change. --new-secrets makes new ones as well.

On a server it looks at the machine before writing anything: it picks a public port nobody else is
using, and with --domain it checks whether another program already answers on ports 80 and 443.

It only uses Python's standard library. Nothing is sent anywhere.
"""

import argparse
import secrets
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHEAP_MODEL = 'claude-haiku-4-5'
CONTAINER = 'football-cafe-backend'
FIRST_PORT, LAST_PORT = 30082, 30999
PLACEHOLDERS = {'yourdomain.com', 'your-domain.com', 'example.com', 'cafe.example.com', 'cafe.example', 'domain.com'}


def read_env(path: Path) -> dict:
    values = {}
    for line in path.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, _, value = line.partition('=')
            values[key.strip()] = value.strip()
    return values


def port_is_free(port: int) -> bool:
    """Nobody listens on the port, and nothing answers on it either (some setups answer without listening)."""
    with socket.socket() as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            return False
    with socket.socket() as probe:
        try:
            probe.bind(('0.0.0.0', port))
        except OSError:
            return False
    return True


def our_published_ports() -> set:
    """Ports the cafe's own containers hold right now, so a restart does not count them as taken."""
    try:
        result = subprocess.run(
            ['docker', 'ps', '--filter', 'label=com.docker.compose.project=football-cafe', '--format', '{{.Ports}}'],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    ports = set()
    for chunk in result.stdout.replace('\n', ',').split(','):
        published = chunk.split('->')[0].rsplit(':', 1)[-1].strip()
        if '->' in chunk and published.isdigit():
            ports.add(int(published))
    return ports


def pick_port(wanted, ours: set) -> int:
    """`wanted` if it can be used, otherwise the first free port in the range the firewall leaves open."""
    usable = lambda port: port in ours or port_is_free(port)  # noqa: E731
    if wanted and usable(int(wanted)):
        return int(wanted)
    for port in range(FIRST_PORT, LAST_PORT + 1):
        if usable(port):
            if wanted:
                print(f'Port {wanted} is used by something else on this machine. Using {port} instead.')
            return port
    raise SystemExit(f'No free port between {FIRST_PORT} and {LAST_PORT}.')


def this_machine_ip() -> str:
    """The address this machine uses to reach the internet. No data is sent: it only asks the routing table."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(('192.0.2.1', 9))
            return probe.getsockname()[0]
        except OSError:
            return ''


def main() -> int:
    parser = argparse.ArgumentParser(description='Write the .env, with strong random secrets.')
    parser.add_argument('--ip', help="Your server's public IP. Server settings, plain http.")
    parser.add_argument('--domain', help='Your domain, e.g. footballcafe.com. Server settings, https.')
    parser.add_argument('--port', help='Public port for the site. Left out: a free one is found.')
    parser.add_argument('--force', action='store_true', help='Replace an existing .env (kept as .env.backup).')
    parser.add_argument('--new-secrets', action='store_true', help='With --force: also make new passwords and keys.')
    parser.add_argument('--output', default=str(ROOT / '.env'), help='Where to write it (default: .env).')
    args = parser.parse_args()
    if args.ip and args.domain:
        parser.error('Give --ip or --domain, not both.')
    domain = (args.domain or '').removeprefix('https://').removeprefix('http://').removeprefix('www.').strip('/').lower()
    if args.domain and (domain in PLACEHOLDERS or '.' not in domain):
        print(f'"{args.domain}" is the example from the instructions. Put the domain you bought, like:')
        print('    python3 scripts/make_env.py --domain footballcafe.gr --force')
        return 1

    target = Path(args.output)
    old = {}
    if target.exists():
        if not args.force:
            print(f'{target} already exists. Run again with --force to replace it (passwords and keys are kept).')
            return 1
        old = read_env(target)

    kept = {} if args.new_secrets else old
    secret_key = kept.get('DJANGO_SECRET_KEY') or secrets.token_urlsafe(50)
    database_password = kept.get('DATABASE_PASSWORD') or secrets.token_urlsafe(24)
    admin_password = kept.get('DJANGO_SUPERUSER_PASSWORD') or secrets.token_urlsafe(12)
    new_passwords = database_password != old.get('DATABASE_PASSWORD')

    server = bool(args.ip or domain)
    own_caddy = False
    if server:
        ours = our_published_ports()
        web_port = pick_port(args.port or old.get('WEB_PORT'), ours)
    else:
        web_port = int(args.port or old.get('WEB_PORT') or 8010)

    if domain:
        # Our own Caddy takes ports 80 and 443, unless some other program on the server already has them.
        own_caddy = all(port in ours or port_is_free(port) for port in (80, 443))
        hosts, origins, address = domain, f'https://{domain}', f'https://{domain}'
    elif args.ip:
        hosts, origins, address = args.ip, f'http://{args.ip}:{web_port}', f'http://{args.ip}:{web_port}'
    else:
        hosts, origins = 'localhost,127.0.0.1,0.0.0.0', f'http://localhost:{web_port},http://127.0.0.1:{web_port}'
        address = f'http://localhost:{web_port}'

    if old:
        shutil.copy(target, target.with_name(target.name + '.backup'))
    target.write_text(f"""\
# Written by scripts/make_env.py. Keep this file out of git.

# Which compose file a plain `docker compose up -d --build` uses in this folder.
COMPOSE_FILE={'compose-deployment.yml' if server else 'compose.yml'}

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

# The address. HTTPS=True means visitors arrive through an https address.
# COMPOSE_PROFILES=https starts our own Caddy on ports 80 and 443; it is left empty when another
# program on the server (for example Nginx Proxy Manager) already answers there and passes visitors on.
DOMAIN={domain}
HTTPS={'True' if domain else 'False'}
COMPOSE_PROFILES={'https' if own_caddy else ''}
WEB_BIND={'127.0.0.1' if own_caddy else '0.0.0.0'}
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
    print('Now start (or restart) the cafe:')
    print('    docker compose up -d --build')
    if old and new_passwords:
        print('The database you already have still uses the old passwords. Run this instead, it keeps your data:')
        print(f'    sh scripts/apply_env.sh{" compose-deployment.yml" if server else ""}')

    print()
    if not domain:
        print(f'It will answer on {address}')
        return 0

    try:
        points_at = socket.gethostbyname(domain)
    except OSError:
        points_at = ''
    here = this_machine_ip()
    if not points_at:
        print(f'Note: {domain} does not point anywhere yet. Add the two A records at your registrar, then wait a little.')
    elif here and points_at != here:
        print(f'Note: {domain} points at {points_at}, and this machine is {here}. Check the A records at your registrar.')

    if own_caddy:
        print(f'It will answer on {address} (the https certificate can take a minute the first time).')
    else:
        print('Another program on this server already answers on ports 80 and 443, so the cafe leaves them alone.')
        print(f'The cafe itself listens on port {web_port}. In that program (for example Nginx Proxy Manager), add a host:')
        print(f'    domain name:       {domain}')
        print(f'    forward to:        http://172.17.0.1:{web_port}')
        print('    SSL:               request a new certificate, force SSL')
        print(f'Then it will answer on {address}')
        print(f'For www.{domain} add a redirection host there that sends it to {domain}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
