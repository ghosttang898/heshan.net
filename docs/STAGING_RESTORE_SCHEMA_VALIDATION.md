# Staging restore: CHECK expression validation

## Confirmed evidence

The retained restore diagnosis in `/var/tmp/heshan-schema-diagnosis-py1glgk5`
found seven differences, all in enum CHECK expression deparsing. Both servers
were PostgreSQL 16.15 with UTF8 and the same locale settings.

| Table | Constraint | Fixed values |
| --- | --- | --- |
| comments | comments_status_check | PUBLISHED, HIDDEN, DELETED |
| posts | posts_status_check | PUBLISHED, HIDDEN, DELETED |
| posts | posts_type_check | CHAT, FIND_PERSON |
| role_change_audit | role_change_audit_action_check | GRANT_ADMIN, REVOKE_ADMIN, INITIALIZE_FOUNDER |
| role_change_audit | role_change_audit_new_role_check | USER, ADMIN, SUPER_ADMIN |
| role_change_audit | role_change_audit_old_role_check | USER, ADMIN, SUPER_ADMIN |
| users | users_role_check | USER, ADMIN, SUPER_ADMIN |

The source casts a fixed array of unconstrained varchar literals to text[].
The restored definition casts each of those same varchar literals to text
before forming the array. With these fixed non-NULL literals, both forms have
the same element values and equality predicate. For a NULL input column both
predicates produce UNKNOWN; PostgreSQL CHECK accepts UNKNOWN. Column NOT NULL
definitions are compared independently and are not removed or relaxed.

## Local fix

- Preserve the raw fingerprint and include the original schema definitions.
- Recognize only the exact two observed strings for each of the seven named
  constraints. This is not a general SQL expression canonicalizer.
- Compare every other definition exactly, including column nullability,
  defaults, field types, indexes, foreign keys and sequence definitions.
- Capture and compare constraint validation, deferrability, initial deferred
  state, inheritance and foreign-key action/match flags independently.
- Missing/extra definitions, changed literals, different columns/operators,
  NULL literals, casts with length limits and unrecognized expressions fail.
- Legacy snapshots without definitions may only match an identical raw hash.
  Different raw hashes without details fail closed; old references must not be
  edited or marked PASS after the fact.
- No database migration or mutation is required for this script fix.

## Reverification plan (not executed)

After separate owner approval, use the existing retained stopped container
`heshan-restore-test-b21f953a0b230fb3080f2b4b` and its volume
`heshan-restore-data-33a647148132f16c72a9c189`. Do not rerun the restore launcher.

1. Upload a new checksum-pinned diagnostic bundle; do not overwrite old reports.
2. Use interactive sudo, verify the full container ID, volume labels/mount,
   network isolation, no exposed ports, 384 MiB RAM/swap limit and 0.25 CPU.
3. Require at least 768 MiB available host RAM and 4 GiB free disk; check all
   three Staging containers are healthy with unchanged identity/restart counts.
4. Start only the retained temporary container. Continuously monitor resources
   and Staging health, and query both databases inside READ ONLY transactions.
5. Compare table counts/full-row fingerprints, raw and normalized structure,
   sequences, identities, roles, founder records, Flyway and orphan counts.
6. Require ghost ID 1 remains USER and founder_identity remains empty. Do not
   call any founder initialization command or alter any account.
7. Stop the temporary container on success or failure; retain its volume,
   backup and all reports. Never restart the source PostgreSQL container.

The new report separately identifies diagnosis completion, data verification,
structure verification and retained restore verification. The historical FAIL
report remains intact. If any check fails, the overall verification stays FAIL.
This verifies the retained restored data, not a newly executed restore.

## Release gates still outstanding

- Actual VPS reverification of this local script fix is NOT TESTED.
- Do not infer validation of database ownership/ACLs: the drill excludes them.
- Database restart persistence verification needs separate owner approval.
- Configure and verify daily off-VPS backups, retention and recovery procedures
  before relying on production backups; a VPS-local dump alone is insufficient.
- Verify the unpublished year-search fix in Staging before rollout.
- Production release still needs its own approved HTTPS/API/DNS/cutover and
  rollback plan; this script fix does not authorize any production deployment.
