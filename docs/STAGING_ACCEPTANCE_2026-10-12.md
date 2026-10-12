# Staging Functional Acceptance - 2026-10-12

## Scope

Target: https://localhost:18443/ through the Mac SSH tunnel. Backend image is
the existing eca42d278f39c64415f9946fec9f51aa6c113459 release; web uses the
installed ingress overlay. No container restart, deployment, admin promotion,
production data access, DNS/firewall change or resource deletion was performed.

Synthetic users: stage-api-85aff122e569 and stage-ui-mv5eut4y. Passwords/JWTs
were generated and used only in memory, never written to reports. Browser
acceptance temporarily changed the browser login session to the UI fixture;
it was logged out and the agent-created tab closed at completion. No ghost
profile, password, role, post or comment was modified.

## Actual Results

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| Registration, login, logout, re-login | PASS | Actual browser form flow; logout survives refresh; API login/me and bad-password 401 |
| Registration role safety | PASS | Supplied SUPER_ADMIN registration parameter still yields USER |
| Chat post creation/detail/comment | PASS | UI post 4 and comment; API post 2/comment 2; authors match temporary users |
| Find-person creation/detail/comment | PASS | UI post 5 and inline comment; API post 3/comment 3 |
| Find-person filters | PASS | Combined nickname/year/location filter, no-match state, restored match |
| Ordinary user Admin route | PASS | Actual browser /admin and refresh show 403 access denied, no dashboard |
| Ordinary user Admin APIs | PASS | Five GET endpoints return 403 with the temporary USER JWT |
| API read-back after writes | PASS | Both post types and comments re-read over HTTPS; browser refresh retains data |
| Direct PostgreSQL row verification | NOT TESTED | Docker/psql require interactive sudo; prepared read-only owner command below |
| Persistence across container restart | NOT TESTED | No restart requested or performed during acceptance |
| IP location rendering | PASS | Lists/details/comments display unknown for the tunnel's NON_PUBLIC source |
| IP location field spoofing | PASS | Forged country/city/status ignored; X-Forwarded-For spoof attempt still NON_PUBLIC |
| Public API privacy | PASS | Inspected synthetic post/comment responses lack raw IP, password/hash, token fields |
| Public-IP geolocation / VPN / IPv6 lookup | NOT TESTED | Local tunnel cannot establish those exit-source scenarios |
| SPA deep-link refresh/navigation/history | PASS | Real browser navigation, refresh and back/forward; API smoke routes previously verified |
| Responsive widths | PASS | 320/390px: home/chat/find/login/register/post; 1280px post; no horizontal overflow; mobile screenshot reviewed |
| Cloudflare Analytics not loaded | PASS | Zero beacon/data-cf-beacon script tags on tested routes including /admin; localhost is excluded by source allowlist |
| Full external network request trace | NOT TESTED | Browser resource timing API not exposed by automation; no claim of a full network capture |
| Browser console errors | PASS | Captured temporary test tab error/warn logs empty |
| VPS resource readout | PASS | SSH free/df successful; initial available RAM 1185 MiB, swap 0, disk approximately 41 GiB free |
| Current container health/restarts/OOM/logs | NOT TESTED | Earlier recovery health evidence is not substituted for this acceptance run; sudo required |

14 API checks passed. The mobile matrix covers six routes at both 320 and
390 pixels, all reporting scrollWidth equal to clientWidth. Screenshot and
JSON artifacts are outside Git at /private/tmp/heshan-staging-acceptance-20261012/:
api-report.json, layout-report.json, mobile-post.png, desktop-post.png.

## Findings and Recommendations

1. Registration lacks the shared website header/home navigation that login
   and detail pages have. Non-blocking usability inconsistency; reuse SiteHeader
   in a separately approved UI change.
2. Loading lists/comments transiently show empty-state wording before fetching
   finishes. The records then appear and survived refresh. Show an explicit
   loading state until the request completes to avoid implying data loss.
3. SQL and current Docker log/restart verification remain acceptance gates.
   API read-back alone must not be labeled direct PostgreSQL persistence proof.
4. Keep the ingress overlay in every future Compose startup/recreation. Do not
   run the old deploy controller without it. No additional security relaxation
   was performed for this acceptance.

No blocking failure was observed in the tested user workflows. Overall
functional acceptance remains INCOMPLETE, not an authorization to go live.

## Remaining Owner Check

The read-only script has been uploaded as a new file. Run from Mac; enter sudo
password only in the terminal, never in chat:

```bash
ssh -t -i ~/.ssh/id_ed25519 heshan@165.232.156.104 \
  'sudo bash /var/tmp/heshan-staging-network-gCA042si/staging-acceptance-readonly.sh stage-api-85aff122e569 stage-ui-mv5eut4y'
```

This checks ONLY the three named Staging containers, prints redacted log-count
summaries (not log lines or environments), and runs a READ ONLY transaction
against heshan_staging. It selects only the two fixture users, their four posts
and four comments, and Flyway metadata. It does not select password hashes or
tokens, touch ghost, initialize data, restart services or delete volumes.
Any nonzero log error count needs review; it is not automatically a real app
failure, and zero counts cover only the last 30 minutes. These SQL/Docker checks
must remain NOT TESTED until the actual command output is received.

## Local Script Verification

New API acceptance script: actual Staging run, 14/14 PASS, py_compile PASS.
Read-only server diagnostic script: bash -n PASS; not executed with root yet.
Existing script suite: 73 tests, 72 passed and one opt-in local Nginx fixture
skipped in this run. No Git commit/push or production deployment performed.
