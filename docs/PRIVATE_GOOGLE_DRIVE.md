# Private Google Drive storage and Limited Access audit

Destination is fixed to `1ixmork-KFJ8xdtQCFJIpUTQm-SnJqeez`. The application never modifies Drive sharing permissions or creates another top-level destination.

## What is implemented

- Opt-in `GOOGLE_DRIVE_ENABLED=true`; historical local sessions are not automatically migrated.
- SQLite migration 009 adds `drive_uploads`, preserving existing data. Confirmation durably commits the official composite and upload job in the same transaction.
- One OS-locked worker, persisted reserved Drive IDs, verified MD5/size/parent metadata and ACL, retry backoff capped below five minutes. Lost upload ACKs reconcile the same ID rather than create another file.
- Pending/failed uploads retain local staging. QR generation waits for SYNCED and the Result UI automatically retries the confirmed composite. No Drive URLs/IDs appear in the public QR.
- Token-authorized Guest Photo Page retrieves the private Drive composite through the backend; invalid/revoked/expired tokens are checked first. Historical local shares retain their existing behavior.
- Host Dashboard → Hệ thống → Google Drive shows queue counts/errors/cache size and privacy audit. Connect/reauthorize gives an explicit local login command; check, disposable test upload and retry remain Host-authenticated.
- Optional explicit Host cache eviction API `POST /api/admin/storage/drive/cache/{composite_id}/evict` verifies a fresh private download and refuses pending/failed sync, active/failed print jobs, approved event photos, corrupt files and historical local-only finals. Print-ready derivatives remain available for printing. Missing original cache is rehydrated through existing authenticated image routes.

## Limited Access is not the same as public content access

Drive documents a folder permission with `reader`, `view=metadata` and inherited permission details when inherited content access has been disabled. The folder name can be visible while its contents remain inaccessible.

The guard requests:

```text
files.get:
id,name,mimeType,parents,inheritedPermissionsDisabled,
capabilities(canAddChildren,canListChildren)

permissions.list (all pages):
id,type,role,view,inheritedPermissionsDisabled,
permissionDetails(inherited,inheritedFrom,permissionType,role)
```

Broad entries are accepted as metadata-only only when the item is a folder, `inheritedPermissionsDisabled=true`, the permission is `reader` with `view=metadata`, and all returned nonempty inheritance details explicitly say inherited=true. Any direct grant, conflicting detail, missing proof or unrecognized role remains blocked. Broad file-content grants are never accepted using this folder-only exception.

A proven Limited Access boundary stops traversal into the parent. The parent can remain publicly shared without being treated as effective content access inside that boundary. When no such boundary is proven, ancestor ACLs must also be readable and safe. The guard never silently widens OAuth scope.

## Actual evidence collected on 2026-10-31

Latest authenticated result after Desktop Picker selection: **PASS**. The callback
contained exactly the approved folder ID and the new credentials were saved with
Windows DPAPI. Folder metadata and `canAddChildren` passed. The raw API returned
`inheritedPermissionsDisabled=true`; the anyone/reader entry has `view=metadata`
and inherited permission details, so the privacy guard classified it as
`METADATA_ONLY` and did not traverse or modify the parent.

One disposable `amazing-race-DISPOSABLE-TEST.png` was uploaded privately:
file ID `1BwFzo7effMChS9p370G9YUQdsD7seq8y`, size **185 bytes**. Target parent,
MD5 checksum, file ACL and metadata size/ID were verified. No customer composite
was migrated by this test. The earlier connector-only evidence below is retained
as history; its unresolved access/privacy classification is superseded by this
authenticated result.

- Connector metadata reports parent `amazing race` with anyone/writer, target with anyone/reader.
- The connector normalizes metadata and omits inheritedPermissionsDisabled, view and permissionDetails from its returned payload even when requested. This output cannot determine whether the folder entry is direct or metadata-only inherited.
- A non-customer UTF-8 probe was created inside the exact target: `AMAZING_RACE_PRIVACY_PROBE_2026-10-31.txt`, ID `1oG3j0o9pBXvQqhe_9YYUBjhZv9bLWXZw`.
- Authenticated readback confirmed its marker and exact parent. The new file's returned ACL lists only named users.
- An independent HTTP client without Google authentication read the view/download endpoints. View returned 401; both download paths redirected to Google sign-in and did not return the marker. Login redirects were not counted as public content or conclusive folder-private proof.
- No customer image was uploaded. No sharing permission, existing Drive file, parent folder or file location was changed. The probe is retained, not deleted.
- Conclusion: earlier “anyone entry proves public content” reasoning was insufficient. The probe content was not anonymously accessible in these checks, consistent with Limited Access. Exact direct-vs-inherited classification of the target is still UNVERIFIED until raw authenticated API evidence is obtained.

Official references:

- https://developers.google.com/workspace/drive/api/guides/limited-expansive-access
- https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions
- https://developers.google.com/workspace/drive/api/guides/manage-uploads

## Operator OAuth steps

### Grant the existing folder through Desktop Picker

If OAuth works but `drive.file` cannot read the existing folder, logging in alone
does not grant per-item access. The saved credentials now decrypt correctly with
Windows DPAPI; the real authenticated account check passed, while destination
metadata returned inaccessible. Editor access and privacy are **unverified** at
that point, not evidence of public sharing.

1. Open Google Cloud Console and select the project containing the **existing
   Desktop OAuth client**. Go to **APIs & Services → Library → Google Picker API
   → Enable**. Keep Google Drive API enabled in that same project. If the consent
   app is in Testing, ensure your Google account is listed under **Google Auth
   Platform → Audience → Test users**.
2. Run from the repository root:

   ```powershell
   & .\backend\.venv\Scripts\python.exe -X utf8 scripts/connect_google_drive.py --storage-root runtime --pick-folder --test-upload
   ```

3. In the browser use the account that has Editor/Owner access, select
   **Amazing race-Photobooth**, and confirm **Insert**. Only ID
   `1ixmork-KFJ8xdtQCFJIpUTQm-SnJqeez` is accepted. Cancel, a missing selection, a
   different folder, additional scopes, or missing offline authorization preserves
   the previous saved credentials.
4. The script checks authenticated folder metadata, `canAddChildren` (Editor or
   stronger capability), and the existing privacy guard. `--test-upload` creates
   or reuses exactly one disposable image only after those checks pass, then
   reports its Drive file ID, size and verified checksum. It never migrates old
   customer photos or starts a worker. If any guard blocks, nothing is uploaded.

The OAuth-hosted Picker uses the saved encrypted client ID/secret from the same
project, PKCE, a random loopback port, `trigger_onepick=true`, `prompt=consent`,
`allow_folder_selection=true`,
and **drive.file alone**. No new web OAuth client or browser API key is required.
The Picker uses its normal browse view instead of MIME/file-ID prefilters;
the callback still rejects every selection except the exact destination ID.
An optional `--client-file` must belong to the saved Desktop client. Refresh/access
tokens and authorization codes are never printed. Neither browser selection nor
an authenticated API read alone is treated as proof of folder privacy.

After authorization, a read-only recheck is:

```powershell
& .\backend\.venv\Scripts\python.exe -X utf8 scripts/connect_google_drive.py --storage-root runtime --check --audit
```

If the folder is accessible but `canAddChildren` is false, ask its owner to grant
the selected account Editor access. If ancestor metadata/ACL cannot be verified,
the audit remains blocked; the script does not grant itself access or change
parent-folder permissions. Enabling the upload worker remains an explicit
`GOOGLE_DRIVE_ENABLED=true` Host configuration step, separate from Picker consent.

Official protocol: [Google Desktop/Mobile Picker](https://developers.google.com/workspace/drive/picker/guides/desktop-mobile-picker).

### Initial login when there is no saved credential

Optional Google OAuth dependencies have been installed in this Windows venv. For another host:

```powershell
& .\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-drive-optional.txt
```

1. Enable Google Drive API in your Google Cloud project; configure OAuth consent and test users where applicable.
2. Create a Desktop OAuth client and put its downloaded JSON in `.tools/google-drive/client_secret.json`. This path and credential files are ignored by Git. Do not paste credentials into chat.
3. Run the local login. It uses PKCE, a random 127.0.0.1 callback port and drive.file only:

```powershell
& .\backend\.venv\Scripts\python.exe -X utf8 scripts/connect_google_drive.py --storage-root runtime --client-file .tools/google-drive/client_secret.json
```

Tokens are protected with Windows DPAPI for the current OS user (or OS keychain on supported non-Windows hosts), not plaintext frontend configuration. Refresh tokens are refreshed by the backend.

Existing-folder access under drive.file must be explicitly granted to the same Google Cloud application, normally through Google Picker. A normal Drive URL or a different connected app does not grant this permission. If the OAuth application cannot read the exact folder with drive.file, additional same-project Picker authorization is required; full Drive scope is not automatically requested. Picker onboarding is not currently built into the Guest UI.

Read a raw audit without uploading or changing permissions:

```powershell
& .\backend\.venv\Scripts\python.exe -X utf8 scripts/connect_google_drive.py --audit --storage-root .tools/mobile-qr-demo/storage
```

Only after the audit proves private content access should real-photo upload be enabled. If direct broad permission is proven, the audit identifies the item/permission for an operator to inspect and remove with approval. Do not remove the parent's permissions automatically.

If reliable private verification remains impossible, the fallback recommendation is for the operator to move the destination folder into a private My Drive location outside the public parent and audit again. The application does not perform that move or delete any files.

## Combined mobile demo

The existing local-only Cloudflare demo remains separate from verified Drive integration. To require Drive:

```powershell
.\scripts\stop_mobile_qr_demo.ps1
.\scripts\start_mobile_qr_demo.ps1 -RequireDrive
```

Drive preflight must pass before any new service/tunnel is started. A running local-only demo is not reported as a Drive-enabled success. Startup checks photo-only route isolation, verified private fixture uploads, HTTPS pages/downloads and decoded QR URLs. Tokens and fixture IDs are preserved on restart.

Do not stop an existing demo merely to run the OAuth audit. Complete authorization/privacy first. Without them, `-RequireDrive` fails closed and does not start duplicate processes.

Cloudflare setup and phone testing: [MOBILE_QR_DEMO.md](MOBILE_QR_DEMO.md).

## Cloud-server boundary

Drive storage alone does not keep a laptop-hosted website online after shutdown. A future public server needs a consistent metadata snapshot/replication containing session finals, share nonce/hash/revocation/expiry, Drive ID/checksum and the protected share-signing key. It also needs its own securely authorized Drive credentials; Windows DPAPI ciphertext is not portable to another host/user. Mount only token-authorized public routes, run upload workers only where intended, and retain the Host/kiosk security boundary.

No permanent server deployment or 24/7 availability has been verified.

### Drive configuration after Host restart

Confirmed regression (31/10/2026): the running Host reported `storage.provider=local`; seven older jobs were SYNCED while the newest confirmed session had no upload job. Queue creation is outside the event-consent condition. This was a disabled startup setting, not a consent/UI/OAuth regression.

The launcher now remembers explicit `GOOGLE_DRIVE_ENABLED` choices in `<storage-root>/.drive-config.json` after successful startup. A later launch without that environment variable restores the same choice for that runtime only. Explicit environment/env-file true or false still overrides the remembered value. No OAuth secrets or folder permissions are stored/changed by this file.

For the current runtime the authorized Drive opt-in has been saved as true. Restart the existing Host to load it (or continue using `--env-file deployment/integration.env`). Startup prints whether Drive is enabled. The already-running local-only Host cannot hot-load this flag.

Verification: one disposable four-photo composite with explicit false publication consent automatically queued and reached SYNCED via the existing asynchronous worker. Real file `1SLiECs2QpgRBL7sysZxVvqF1W3df_A2B`, 12350 bytes, size/MD5/local SHA verified. The specifically affected existing final was integrity-checked, queued without changing its image/share/consent, and recovered to verified Drive file `1qTzT_ce6PLpBGGodPxvUJkzSwohsQ1SG`. Other historical finals were not backfilled. The temporary verification worker released its OS lease after completion. No parent/child sharing changes, credential resets or deletions occurred.

Focused tests: five backend cases (runtime-scoped persistence/explicit overrides, false/missing consent private uploads, expiration storage preservation, lost-ACK/restart recovery) and two simplified-Guest UI unit cases passed. No frontend source changes, full suite or build were needed for this fix.
