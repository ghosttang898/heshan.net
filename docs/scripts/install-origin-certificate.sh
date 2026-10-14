#!/usr/bin/env bash
# TLS preparation only: preserve key/CSR, do not enable or start any service.
set -Eeuo pipefail
set +x
umask 077
[[ $EUID == 0 && $# == 1 && $1 == --install-verified-origin-certificate ]] || exit 1
[[ $(uname -s) == Linux ]] || exit 1
export LC_ALL=C
unset DOCKER_CONTEXT
export DOCKER_HOST=unix:///var/run/docker.sock
DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
(cd "$DIR"; sha256sum -c SHA256SUMS)
for dir in /etc/heshan /etc/heshan/tls; do
  [[ -d $dir && ! -L $dir && $(stat -c '%a %u:%g' "$dir") == '700 0:0' ]] || exit 1
done
key=/etc/heshan/tls/privkey.pem
csr=/etc/heshan/tls/origin.csr
for file in "$key" "$csr"; do
  [[ -f $file && ! -L $file && $(stat -c '%a %u:%g' "$file") == '600 0:0' ]] || exit 1
done
for file in /etc/heshan/tls/fullchain.pem /etc/heshan/tls/cloudflare-origin-rsa-root.pem \
  /etc/heshan/nginx-site-https.conf.candidate /etc/heshan/nginx-cloudflare-realip.conf.candidate \
  /etc/heshan/nginx-validation.conf; do
  [[ ! -e $file && ! -L $file ]] || { printf 'STOP: existing target, no overwrite\n'; exit 1; }
done
if systemctl is-active --quiet nginx || systemctl is-enabled --quiet nginx; then
  printf 'STOP: Nginx must remain stopped and disabled\n'; exit 1;
fi
snapshot() {
  docker inspect heshan-staging-db-1 heshan-staging-backend-1 heshan-staging-web-1 \
    --format '{{.Id}} {{.State.Status}} {{.State.Health.Status}} {{.State.OOMKilled}} {{.RestartCount}}'
}
before=$(snapshot)
[[ $(printf '%s\n' "$before" | awk '$2=="running" && $3=="healthy" && $4=="false" && $5==0 {n++} END {print n+0}') == 3 ]] || exit 1
openssl verify -purpose sslserver -CAfile "$DIR/cloudflare-origin-rsa-root.pem" "$DIR/origin.pem"
openssl verify -verify_hostname heshan.net -CAfile "$DIR/cloudflare-origin-rsa-root.pem" "$DIR/origin.pem"
openssl verify -verify_hostname www.heshan.net -CAfile "$DIR/cloudflare-origin-rsa-root.pem" "$DIR/origin.pem"
openssl req -in "$csr" -verify -noout
cert_public=$(openssl x509 -in "$DIR/origin.pem" -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum)
key_public=$(openssl pkey -in "$key" -pubout -outform DER | sha256sum)
csr_public=$(openssl req -in "$csr" -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum)
[[ $cert_public == "$key_public" && $cert_public == "$csr_public" ]] || {
  printf 'STOP: certificate/key/CSR mismatch; nothing installed\n'; exit 1;
}
printf 'PASS: CA signature, time, hostnames and existing key/CSR match\n'
install -m 0600 -o root -g root "$DIR/origin.pem" /etc/heshan/tls/fullchain.pem
install -m 0600 -o root -g root "$DIR/cloudflare-origin-rsa-root.pem" /etc/heshan/tls/cloudflare-origin-rsa-root.pem
install -m 0600 -o root -g root "$DIR/nginx-site-https.conf.candidate" /etc/heshan/nginx-site-https.conf.candidate
install -m 0600 -o root -g root "$DIR/cloudflare-realip.conf.example" /etc/heshan/nginx-cloudflare-realip.conf.candidate
install -m 0600 -o root -g root "$DIR/nginx-validation.conf" /etc/heshan/nginx-validation.conf
nginx -t -c /etc/heshan/nginx-validation.conf
[[ $(snapshot) == "$before" ]] || { printf 'STOP: Staging state changed; inspect\n'; exit 1; }
if systemctl is-active --quiet nginx || systemctl is-enabled --quiet nginx; then exit 1; fi
openssl x509 -in /etc/heshan/tls/fullchain.pem -noout -dates -fingerprint -sha256
printf 'PASS: TLS installed, candidate Nginx syntax valid; Nginx stopped/disabled; Staging unchanged.\n'
printf 'No DNS, proxy, database, service startup, key overwrite or migration operations.\n'
