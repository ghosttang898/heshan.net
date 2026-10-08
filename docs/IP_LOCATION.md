# IP Location v0.1

## Choice and trade-offs

| Option | Accuracy and maintenance | License and privacy |
| --- | --- | --- |
| MaxMind GeoLite2 City local MMDB | Approximate city/region; maintain current database through GeoIP Update; account and download license key required | GeoLite EULA and attribution apply; old-version/data obligations need review before retaining long-lived snapshots. Local queries do not send visitor IPs outside the server. |
| Third-party city API (e.g. IPinfo) | Provider maintains data; city coverage depends on paid plan; requires network timeouts and quota handling | Provider-specific display/retention terms and API token; visitor IPs are disclosed to the provider at publication time. |
| **DB-IP City Lite local MMDB (selected)** | Free database with reduced coverage/accuracy; monthly updates; country/region/city and IPv4/IPv6 | CC BY 4.0 attribution; no runtime API key or external lookup. Compatible with persistent publication snapshots without adopting GeoLite-specific update/data restrictions. |

All options are approximate, not GPS. None establishes an individual's physical location.
The local choice keeps implementation and privacy controls simple. Review production licensing and
local privacy obligations for your deployment; this comparison is not legal advice.
For higher accuracy/SLA, evaluate a commercial local database with appropriate display/retention rights.

Sources:
- [DB-IP Lite license, monthly releases, reduced accuracy](https://db-ip.com/db/lite.php)
- [DB-IP City Lite MMDB download](https://db-ip.com/db/download/ip-to-city-lite)
- [GeoLite overview and approximate location](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data/)
- [GeoLite EULA](https://www.maxmind.com/en/geolite/eula)
- [MaxMind updates](https://dev.maxmind.com/geoip/updating-databases/)
- [IPinfo API tokens and quotas](https://ipinfo.io/developers)

The only added dependency is MaxMind's Apache-2.0 Java MMDB reader (`geoip2` 5.2.0, Java 17).
**The reader library is not the data provider:** it reads DB-IP's compatible City MMDB format.
GeoLite City could technically be read by the same code, but do not switch without reviewing its
distinct license/retention requirements and updating the site's attribution/privacy notice.

## Database setup and updates

1. Download the current **City Lite MMDB** from the official DB-IP page above. Review CC BY 4.0
   and keep the source attribution included in the public/admin footers. No account or API key is needed.
2. Decompress the `.mmdb.gz` file, verify its uncompressed checksum against the publisher's page,
   and place it outside Git, for example `/var/lib/tonghehui/geoip/dbip-city-lite.mmdb`.
3. Give the application read-only access and set:

```bash
export APP_GEOLOCATION_DATABASE_PATH=/var/lib/tonghehui/geoip/dbip-city-lite.mmdb
export APP_GEOLOCATION_TIMEOUT_MS=200
# No proxies are trusted by default. Only list actual controlled proxy peers.
export APP_GEOLOCATION_TRUSTED_PROXIES=127.0.0.1/32,::1/128
cd backend
mvn spring-boot:run
```

Use Java 17. The proxy setting above is only an example for a local Nginx deployment, not a default.
Leave it unset when clients connect directly or when using the local Vite development server.
Localhost/private requests deliberately show unknown even with a database installed.
Do not trust loopback merely to make a browser-supplied X-Forwarded-For header work in development.

Download and validate the new database monthly. Atomically replace it, then restart the backend
to load the new copy; no hot reload is implemented. The reader loads the file into memory once,
so allow roughly the uncompressed database size plus reader/JVM overhead (October 2026 file about 121 MB).
H2 is currently in-memory: restarting also removes community data; schedule changes appropriately
and use the existing administrator bootstrap if needed. Historical snapshots are never recalculated.
No production database or credentials are bundled in Git; `.mmdb` and `.mmdb.gz` are ignored.

## Trusted proxy handling

`server.forward-headers-strategy=none` preserves the actual socket peer. Do not enable Tomcat's
RemoteIpValve or a ForwardedHeaderFilter ahead of the resolver: that can discard the trust boundary.

`ClientIpResolver` accepts only numeric IPv4/IPv6 literals (no DNS, ports, zone identifiers).
It trusts `X-Forwarded-For` only when the socket peer matches configured CIDRs, walks right-to-left
through trusted hops, and stops at the first untrusted address. Duplicate, malformed, overlong,
or excessive chains yield unknown. Universal `/0` proxy CIDRs are rejected. Trust only exact owned
addresses/narrow CIDRs; a broad network containing clients permits spoofing.
`Forwarded`, `X-Real-IP`, and `CF-Connecting-IP` are deliberately ignored by this version.

For a single Nginx edge, replace user-supplied forwarding information rather than copying it:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

Bind/firewall the Spring port so it cannot bypass the proxy. For multiple controlled hops, each
proxy must append its observed upstream peer, and configure each trusted hop explicitly.
For Cloudflare, restrict ingress to Cloudflare's current published CIDRs and normalize its client
header at the trusted edge (e.g. Nginx real-IP configuration with only Cloudflare trusted).
Then Nginx must overwrite X-Forwarded-For with that verified client address. Do not blindly pass
CF-Connecting-IP to Spring or trust it on public/direct connections. Alternatively, Cloudflare
must supply a trustworthy XFF chain and its socket ranges must be explicitly configured.
Refresh Cloudflare ranges operationally; no all-proxy trust or automatic range download is enabled.

## Schema and APIs

Both `posts` and `comments` add nullable columns:
- `ip_country_code` (2 characters)
- `ip_country`, `ip_region`, `ip_city` (128 characters each)
- `ip_location_status` (32-character enum)

Existing H2 schema update adds columns without backfilling. Null status reads as `UNKNOWN`.
No field is added to `users`. There is no raw-IP, latitude/longitude, postal-code or address column.
The common mapped superclass keeps Post/Comment snapshots consistent.

Existing public and admin post/comment responses include camelCase versions of the five fields.
Requests cannot assign them: post JSON location properties are read-only and the server overwrites
the snapshot; comment input accepts only its existing content field. Moderation does not alter location.
No new query API or client-supplied IP endpoint is added. Country filtering is deferred (optional in v0.1).

Statuses:
- `RESOLVED`: country found (region/city may be absent)
- `UNKNOWN`: historical/no publication snapshot
- `NON_PUBLIC`: private, loopback, link-local, reserved/documentation or multicast address
- `INVALID_IP`: missing/invalid numeric IP or malformed trusted forwarding chain
- `DATABASE_UNAVAILABLE`: unconfigured, missing or unreadable database
- `NOT_FOUND`: database has no usable country record
- `TIMEOUT`: lookup exceeded deadline or bounded worker queue is saturated
- `LOOKUP_FAILED`: reader error or interruption

Public display is `IP属地：国家 · 城市`, with region used if city is absent, country alone if neither
is known, and `未知` for every unresolved/historical case. The admin tables and detail panels show
all three names and query status. Source link attribution appears on both public and admin pages.

## Failure handling and privacy

Only new post/comment publications perform a lookup. Browsing, authentication, user details,
dashboard refresh and moderation never query a new IP. The IP exists transiently in the request
and bounded lookup task, is neither persisted nor serialized, and is not included in geolocation logs.
No HTTP geolocation requests occur; the local reader has a default 200 ms deadline, capped at
1000 ms, one worker and 16 queued tasks. Failures return an empty snapshot with a diagnostic status,
not a publication error. If a worker fails to respond to interruption, subsequent requests still
time out rather than spawning unbounded threads or blocking publishing indefinitely.

The public `/privacy` page explains snapshot collection/display, approximate accuracy, VPN egress,
no original-IP/GPS storage, no third-party lookup, and content-linked retention (soft delete is not
physical deletion). Reverse-proxy/hosting access logs are independent: review/redact their IP and
retention settings separately. Do not enable request/header/body debug logs containing personal data.

## Testing

```bash
cd backend
mvn test
# Optional real-data check; no network download happens during tests.
mvn package -Dgeoip.test.database=/absolute/path/to/dbip-city-lite.mmdb
cd ../frontend
node --test src/ipLocation.test.js
npm run build
```

Unit tests use explicit synthetic geography, not claims about where a DNS/anycast address lives.
The opt-in local database smoke test uses public infrastructure IPs: US IPv4, CN IPv4, IPv6.
IPv6 asserts a valid resolved country rather than a hard-coded country; anycast/VPN exits and
provider updates can change that result. VPN behavior is tested with a simulated proxy/exit chain,
not an actual VPN tunnel or real Nginx/Cloudflare deployment.

Integration tests cover server-side snapshot creation, spoofed JSON/forwarding rejection,
anonymous and signed-in comments, admin DTOs, unchanged moderation snapshots, no lookup during reads,
history/null compatibility, timeout fallback and user-profile non-disclosure. Existing Admin tests
continue exercising registration/login/JWT, roles, moderation, search, counts and pagination.

## Completed verification (2026-10-08)

- Java 17 `mvn clean package -Dgeoip.test.database=...`: 20 tests passed, no failures/errors/skips,
  including the original 8 Admin tests and real local DB-IP queries for US, CN and IPv6.
- The October 2026 City MMDB's uncompressed SHA1 matched the official publisher checksum:
  `df17bd24390108ed1d24dcb7718dc60f6b9abd4f`.
- `node --test src/ipLocation.test.js` and `npm run build` passed.
- Browser checks: localhost CHAT/FIND_PERSON post/comment creation, public detail/labels, Admin post/comment columns
  and detail status (`NON_PUBLIC`), privacy/source links, and responsive layouts.
- The running local backend uses `backend/data/dbip-city-lite.mmdb` via environment configuration;
  that file is ignored by Git. The application still defaults to unknown when no path is configured.
- Actual Nginx/Cloudflare and a real VPN tunnel were not deployed; trust-boundary behavior is
  covered by unit/MockMvc tests with simulated peers and chains.

## Remaining limits

- City/region accuracy and coverage are limited; display must not be treated as identity or address evidence.
- Monthly database replacement requires backend restart; no hot reload or automated downloader is included.
- No API fallback, country filter, audit IP storage, GPS tracking or user-profile geography is implemented.
- Private/local test environments correctly display unknown; production needs database and trusted-edge setup.
- Existing H2 memory storage remains unchanged. For persistent production data, review additive migrations and backups.
