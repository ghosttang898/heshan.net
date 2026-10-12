# Staging TLS permission recovery

## Confirmed failure

The VPS logs show `cannot load certificate ... Permission denied`. The TLS
directory is root-owned, GID 101, mode 0700; Nginx runs as UID/GID 101.
The installer sets umask 077 and previously relied on mkdir(mode=0750),
which produces mode 0700. The private key already has the correct mode 0640.
`messagebus` is the host's name for numeric group 101, not an ownership error.

Nginx exited with code 1 and OOMKilled=false. Its health log is empty because
it failed during startup. Published ports correctly specify 127.0.0.1:18443.
All three Staging containers are stopped. Do not rerun the first-install
bundle or init-env: retain the existing database, secrets, TLS files and volume.

The same restrictive umask also affected copied public asset directories.
This is verified locally, not yet confirmed by a VPS stat; inspect their modes
below before fixing public directory traversal. No certificate or key contents
are displayed by these commands.

## Recovery (owner's interactive terminal)

Connect from Mac:

```bash
ssh -t -i ~/.ssh/id_ed25519 heshan@165.232.156.104
```

On the VPS, execute the following block. It stops on errors, checks ownership
and stopped containers, changes only permissions in the existing Staging TLS
directory and public frontend directory tree, validates Nginx before startup,
then uses the existing deployment controller. Do not ignore a failed command.
The transient nginx-test container is the only resource removed by `--rm`.

```bash
sudo bash <<'SH'
set -eu
R=/srv/heshan-staging/releases/eca42d278f39c64415f9946fec9f51aa6c113459
E=/etc/heshan-staging/staging.env
T=/etc/heshan-staging/tls
test -d "$T" && test ! -L "$T"
test "$(stat -c '%u:%g' "$T")" = 0:101
test -d "$R/frontend" && test ! -L "$R/frontend"
test "$(stat -c '%u' "$R/frontend")" = 0
test -z "$(docker ps -q --filter label=com.docker.compose.project=heshan-staging)"
stat -c '%a %u:%g %n' "$T" "$T/fullchain.pem" "$T/privkey.pem" "$R/frontend"
chmod 0750 "$T"
find "$R/frontend" -type d -exec chmod 0755 {} +
stat -c '%a %u:%g %n' "$T" "$T/fullchain.pem" "$T/privkey.pem" "$R/frontend"
python3 "$R/docs/scripts/staging.py" preflight --env-file "$E"
docker run --rm --network none --user 101:101 --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --memory 64m --cpus 0.10 --pids-limit 40 \
  --tmpfs /tmp:size=32m,mode=1777 --add-host backend:127.0.0.1 \
  --mount "type=bind,src=$R/deploy/staging/nginx.conf,dst=/etc/nginx/nginx.conf,readonly" \
  --mount "type=bind,src=$R/frontend,dst=/usr/share/nginx/html,readonly" \
  --mount "type=bind,src=$T,dst=/etc/nginx/tls,readonly" \
  --entrypoint nginx nginx:stable-alpine -t
python3 "$R/docs/scripts/staging.py" deploy --env-file "$E" --execute
python3 "$R/docs/scripts/staging.py" status --env-file "$E"
python3 "$R/docs/scripts/staging-http-smoke.py" \
  --origin https://localhost:18443 --ca-cert "$T/rootCA.pem"
docker ps --filter label=com.docker.compose.project=heshan-staging \
  --format '{{.Names}} | {{.Status}} | {{.Ports}}'
for C in heshan-staging-db-1 heshan-staging-backend-1 heshan-staging-web-1; do
  docker inspect "$C" --format '{{.Name}} Health={{.State.Health.Status}} OOM={{.State.OOMKilled}} Restarts={{.RestartCount}}'
done
ss -lnt
free -m
docker stats --no-stream heshan-staging-db-1 heshan-staging-backend-1 heshan-staging-web-1
SH
```

The isolated nginx-test uses a temporary hosts entry because the real backend
is stopped. It checks syntax and TLS file access only, publishes no ports, and
does not test backend connectivity. The entry is NOT applied to Staging.
The HTTP smoke test above is read-only; it tests SPA routes, security headers,
API forwarding and unauthenticated access. Registration/login/post/comment
testing additionally requires `--exercise-test-user`, which creates synthetic
Staging data only. No founder/admin account is initialized.
If validation after deployment fails, stop only Staging with the command below,
retain logs/data, and report the failing output. The prior deployment reports
are not rewritten by this recovery; successful recovery must be verified from
new command outputs and browser access, not inferred from an old result.json.

## Tunnel and lifecycle

### Healthy web with missing actual port binding

If ConfiguredPorts contains 127.0.0.1:18443 but ActualPorts is null and web
is attached exclusively to an internal network, add the web-only ingress
bridge. Docker's networking documentation describes this frontend topology:
https://docs.docker.com/engine/network/#connecting-to-multiple-networks
The observed Docker 29 failure is also reported in the engine repository:
https://github.com/moby/moby/discussions/53256

The local Compose/controller now include this network permanently. For the
already-running old release, the following owner command uses the uploaded
overlay to recreate ONLY web. Database/backend containers and their networks
are unchanged. Keep the overlay for all future Compose startup/recreation;
do not rerun old deploy/first-install. No existing release file is overwritten.
The ingress bridge permits web
outbound networking; it does NOT publish PostgreSQL/backend or wildcard ports.

```bash
sudo bash <<'SH'
set -eu
R=/srv/heshan-staging/releases/eca42d278f39c64415f9946fec9f51aa6c113459
E=/etc/heshan-staging/staging.env
O=/etc/heshan-staging/web-ingress.override.yml
S=/var/tmp/heshan-staging-network-gCA042si/web-ingress.override.yml
test "$(docker inspect heshan-staging-web-1 --format '{{index .Config.Labels "com.docker.compose.project"}}')" = heshan-staging
test "$(docker inspect heshan-staging-backend-1 --format '{{.State.Health.Status}}')" = healthy
test "$(docker inspect heshan-staging-db-1 --format '{{.State.Health.Status}}')" = healthy
awk '/MemAvailable:/ {if ($2 < 262144) exit 1}' /proc/meminfo
if test -e "$O"; then
  test ! -L "$O"
  cmp "$S" "$O"
else
  install -o root -g root -m 0600 "$S" "$O"
fi
docker compose -p heshan-staging --env-file "$E" \
  -f "$R/deploy/staging/compose.yml" -f "$O" \
  up -d --no-deps --force-recreate --wait --wait-timeout 120 web
test "$(docker port heshan-staging-web-1 8443/tcp)" = 127.0.0.1:18443
docker port heshan-staging-web-1 8443/tcp
python3 "$R/docs/scripts/staging-http-smoke.py" \
  --origin https://localhost:18443 --ca-cert /etc/heshan-staging/tls/rootCA.pem
docker ps --filter label=com.docker.compose.project=heshan-staging \
  --format '{{.Names}} | {{.Status}} | {{.Ports}}'
free -m
SH
```

For rollback, repeat the web-only Compose up command with ONLY the original
Compose file (omit -f "$O"). This restores the inaccessible-but-isolated prior
web configuration. Keep the overlay, network and all volumes; do not prune.

In a second Mac terminal (leave open):

```bash
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:18443:127.0.0.1:18443 \
  -i ~/.ssh/id_ed25519 heshan@165.232.156.104
```

Visit https://localhost:18443/ using the previously trusted local test CA.
On the VPS, safe stop preserves all data:

```bash
sudo python3 /srv/heshan-staging/releases/eca42d278f39c64415f9946fec9f51aa6c113459/docs/scripts/staging.py stop --env-file /etc/heshan-staging/staging.env --execute
```

Next startup must include both Compose files until the corrected controller and
base Compose are installed. Do not use the old controller deploy command after
the ingress repair. No DNS, SSH, firewall, production service or database changes.
Only classify Staging PASS after all services are healthy, HTTPS/API/browser
checks succeed, loopback-only bindings are confirmed, and OOM/restarts are clear.
