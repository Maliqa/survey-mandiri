#!/usr/bin/env bash
# Usage on the VPS: ./deploy.sh <image-tag>
#
# First run (no .env yet) bootstraps everything: random secrets, DB password,
# demo accounts. Needs DOMAIN and BACKEND_IMAGE in the environment (the GitHub
# workflow passes them). Later runs: pull, migrate, restart, health check.
set -euo pipefail
cd "$(dirname "$0")"

TAG="${1:?usage: deploy.sh <image-tag>}"
# Subshell without pipefail: tr exits via SIGPIPE once head has enough bytes.
rand() { (set +o pipefail; LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-48}"); }

if [ ! -f .env ]; then
  : "${DOMAIN:?first run needs DOMAIN}" "${BACKEND_IMAGE:?first run needs BACKEND_IMAGE}"
  echo "==> First run: generating .env for ${DOMAIN}"
  DB_PASS=$(rand 32)
  sed -e "s|^DOMAIN=.*|DOMAIN=${DOMAIN}|" \
      -e "s|^BACKEND_IMAGE=.*|BACKEND_IMAGE=${BACKEND_IMAGE}|" \
      -e "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(rand 64)|" \
      -e "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=${DOMAIN}|" \
      -e "s|^DJANGO_CSRF_TRUSTED_ORIGINS=.*|DJANGO_CSRF_TRUSTED_ORIGINS=https://${DOMAIN}|" \
      -e "s|^DJANGO_ADMIN_URL=.*|DJANGO_ADMIN_URL=kelola-$(rand 6 | tr 'A-Z' 'a-z')/|" \
      -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${DB_PASS}|" \
      -e "s|^DATABASE_URL=.*|DATABASE_URL=postgres://survey_mandiri:${DB_PASS}@db:5432/survey_mandiri|" \
      .env.example > .env
  chmod 600 .env
fi

sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${TAG}|" .env
DOMAIN=$(grep -E '^DOMAIN=' .env | cut -d= -f2-)

echo "==> Pulling ${TAG}"
docker compose pull web worker beat

echo "==> Starting db/redis"
docker compose up -d db redis

echo "==> Migrating"
docker compose run --rm web python manage.py migrate --noinput

echo "==> Restarting app"
docker compose up -d --remove-orphans
# Caddyfile is a bind mount: recreate so config changes always apply (certs live in a volume).
docker compose up -d --force-recreate --no-deps caddy

echo "==> Health check https://${DOMAIN}/api/health (first TLS certificate can take ~1 min)"
for _ in $(seq 1 45); do
  if curl -fsS "https://${DOMAIN}/api/health" >/dev/null 2>&1; then
    echo "OK: ${TAG} is live at https://${DOMAIN}"
    if [ ! -f demo-credentials.txt ]; then
      PASS="Demo-$(rand 10)"
      docker compose exec -T web python manage.py seed_demo --password "${PASS}"
      ADMIN_PATH=$(grep -E '^DJANGO_ADMIN_URL=' .env | cut -d= -f2-)
      umask 077
      printf 'API      https://%s/api/docs\nAdmin    https://%s/%s\nPassword (all demo accounts): %s\n' \
        "$DOMAIN" "$DOMAIN" "$ADMIN_PATH" "$PASS" > demo-credentials.txt
      echo "==> Demo accounts created. On the VPS run: cat ~/sm-demo/demo-credentials.txt"
    fi
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 4
done
echo "Health check failed"
docker compose ps
docker compose logs --tail=60 caddy web
exit 1
