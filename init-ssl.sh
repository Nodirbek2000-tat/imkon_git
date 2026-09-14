#!/usr/bin/env bash
#
# SSL sertifikatni BIRINCHI marta olish. Bir marta ishlatiladi —
# keyin certbot konteyneri o'zi yangilaydi.
#
# nginx sertifikatsiz ishga tushmaydi, certbot esa ishlab turgan nginx'ni
# talab qiladi. Shuning uchun avval soxta sertifikat, keyin haqiqiysi.
#
#   ./init-ssl.sh

set -euo pipefail
cd "$(dirname "$0")"

set -a; source .env; set +a
: "${DOMAIN:?.env da DOMAIN yo'q}"
: "${SSL_EMAIL:?.env da SSL_EMAIL yo'q}"

LIVE="/etc/letsencrypt/live/$DOMAIN"

echo "==> Vaqtinchalik sertifikat..."
docker compose run --rm --entrypoint sh certbot -c "
  mkdir -p '$LIVE'
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout '$LIVE/privkey.pem' -out '$LIVE/fullchain.pem' -subj '/CN=$DOMAIN' 2>/dev/null
"

echo "==> nginx..."
docker compose up -d nginx
sleep 5

echo "==> Soxtasini o'chirib, haqiqiysini olamiz..."
docker compose run --rm --entrypoint sh certbot -c \
  "rm -rf '$LIVE' /etc/letsencrypt/archive/$DOMAIN /etc/letsencrypt/renewal/$DOMAIN.conf"

# `--non-interactive` — certbot savol bersa javob kutib osilib qolmasin
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  --email "$SSL_EMAIL" --agree-tos --no-eff-email \
  --non-interactive \
  -d "$DOMAIN" -d "www.$DOMAIN"

docker compose exec nginx nginx -s reload
echo "TAYYOR: https://$DOMAIN"
