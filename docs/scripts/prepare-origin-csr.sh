#!/usr/bin/env bash
# Generate server-local key and PUBLIC CSR only. Never sign/install/start services.
set -Eeuo pipefail
set +x
umask 077
[[ $EUID == 0 && $# == 1 && $1 == --generate-production-csr ]] || exit 1
[[ $(uname -s) == Linux ]] || exit 1
export LC_ALL=C
unset DOCKER_CONTEXT
export DOCKER_HOST=unix:///var/run/docker.sock
for dir in /etc/heshan /etc/heshan/tls; do
  [[ -d $dir && ! -L $dir && $(stat -c '%a %u:%g' "$dir") == '700 0:0' ]] || {
    printf 'STOP: unexpected private directory permissions\n'; exit 1;
  }
done
if systemctl is-active --quiet nginx; then printf 'STOP: Nginx must remain stopped\n'; exit 1; fi
if systemctl is-enabled --quiet nginx; then printf 'STOP: Nginx must remain disabled\n'; exit 1; fi
for file in privkey.pem origin.csr fullchain.pem; do
  [[ ! -e /etc/heshan/tls/$file && ! -L /etc/heshan/tls/$file ]] || {
    printf 'STOP: existing TLS material; do not overwrite or regenerate\n'; exit 1;
  }
done
snapshot() {
  docker inspect heshan-staging-db-1 heshan-staging-backend-1 heshan-staging-web-1 \
    --format '{{.Id}} {{.State.Status}} {{.State.Health.Status}} {{.State.OOMKilled}} {{.RestartCount}}'
}
before=$(snapshot)
[[ $(printf '%s\n' "$before" | awk '$2=="running" && $3=="healthy" && $4=="false" && $5==0 {n++} END {print n+0}') == 3 ]] || exit 1
# Lock with an atomic private directory. Retained on failure to prevent unsafe retries.
mkdir -m 0700 /etc/heshan/tls/.csr-preparation-lock
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out /etc/heshan/tls/privkey.pem 2>/dev/null
chmod 0600 /etc/heshan/tls/privkey.pem
openssl pkey -in /etc/heshan/tls/privkey.pem -check -noout >/dev/null
openssl req -new -sha256 -key /etc/heshan/tls/privkey.pem \
  -subj '/CN=heshan.net' -addext 'subjectAltName=DNS:heshan.net,DNS:www.heshan.net' \
  -out /etc/heshan/tls/origin.csr
chmod 0600 /etc/heshan/tls/origin.csr
openssl req -in /etc/heshan/tls/origin.csr -verify -noout
[[ $(snapshot) == "$before" ]] || { printf 'STOP: Staging state changed; inspect before proceeding\n'; exit 1; }
printf 'PASS: server-local RSA key and verified public CSR; Staging unchanged.\n'
printf 'Private key remains root-only and is NOT printed. No DNS/certificate issuance/service changes.\n'
printf 'PUBLIC CSR BELOW: paste only this request into Cloudflare, not the private key.\n'
cat /etc/heshan/tls/origin.csr
