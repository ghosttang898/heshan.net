# B2 restricted Staging key: owner-run local setup

> PAUSED under MVP. The owner previously ran the creation tool; this document's
> preparation-only wording is historical, not proof that no credentials exist.
> Do not create or deploy more keys. Revoke/rotate the management key exposed in
> a screenshot using the owner's B2 console; never paste credentials into chat.
> See [V1 handover](V1_HANDOVER.md).

No real key has been created by the agent. No VPS connection, upload, database,
bucket/lifecycle modification, alert ping or scheduler activation is involved.

The script uses only Python standard libraries and runs creation only in an
interactive Mac terminal without sudo. Without its execution flag it prints an
offline preview and does not contact B2 or write files.

```bash
python3 /Users/qizhitang/Documents/heshan.net/docs/scripts/create-b2-staging-key.py
```

Scope: bucket `heshan-staging-backups-001`, verified bucket ID
`321b7358da54367ead16001a`, prefix `staging/`, exactly `listBuckets`, `listFiles`,
`readFiles`, `writeFiles`, expiring after 30 days. No delete, bucket modification,
key management or all-bucket listing capabilities in the newly created key.

When ready, run once:

```bash
python3 /Users/qizhitang/Documents/heshan.net/docs/scripts/create-b2-staging-key.py --execute-create
```

Type the requested bucket/prefix confirmation. Supply an EXISTING management
key ID and application key with `writeKeys` and `listBuckets` capabilities using
the hidden terminal prompts. This is not your website password and not the
restricted backup key. Do not type keys in commands, environment exports,
chat, screenshots or Git. Do not reset an existing Master Key to retrieve it:
that can invalidate clients using it. If you have no securely saved management
credential or are unsure whether a Master Key already exists, stop and clarify
before generating/resetting anything in the web console.

Management credentials are used only in memory for B2 authentication over
verified HTTPS. The script disables proxy environment settings, rejects API
host/path changes and redirects, bounds response size/time and does not print
raw API responses/error bodies or retry requests. Python cannot guarantee
zeroing every in-memory copy; run on a trusted Mac, not a recorded/shared terminal.

It lists only the specified bucket to confirm name, ID, account and private
status, then creates ONE scoped key using Native API v4. It checks the returned
scope and separately authenticates the new key to verify actual restrictions.

The new backup credential, but NOT management credentials or tokens, is saved
to a newly generated file under `~/.config/heshan-backup/` (directory 0700,
file 0600, exclusive no-overwrite/no-symlink creation). The filename ends in
`.backup-credentials.json`, excluded by .gitignore even if accidentally copied
into the repository. Do not paste or screenshot its contents. Record the
expiry and arrange rotation before enabling long-lived unattended backups.

If creation times out, B2 may still have created the key. Do not rerun blindly.
Inspect the Application Keys page and revoke only the newly created unusable
key manually if required. If the response fails scope/authentication checks,
any received new key material is retained privately with `FAIL_DO_NOT_USE`.
An empty reserved file on failure is not proof that B2 created no key. Existing
keys are never deleted/replaced by the script.

Real API execution is NOT TESTED. Local tests use mocked responses only. This
does not validate upload/download, client-side encryption or deletion denial
against actual provider endpoints. In particular, restricted API-v4 keys need
a compatible client: verify the selected rclone version before VPS configuration;
do not assume the old image pin works or upgrade it without approval.

References: [authorize](https://www.backblaze.com/apidocs/b2-authorize-account),
[list one bucket](https://www.backblaze.com/apidocs/b2-list-buckets),
[create key](https://www.backblaze.com/apidocs/b2-create-key).
