# Event configuration and safe operations

Windows 11 is the primary validation platform. macOS has shared launchers and a CUPS adapter, but has not been executed on a Mac here. Linux is best-effort and untested. A successful mock run does not establish physical event readiness.

## Modes and network profiles

`APP_ENV` controls transport/security behavior. `OPERATION_MODE` controls hardware policy. They serve different purposes.

| Mode | Hardware policy | Guest presentation |
|---|---|---|
| development | Mock/webcam-frame demonstrations allowed | Technical diagnostics and DEMO labels |
| rehearsal | Requires explicit `ALLOW_MOCK_HARDWARE=true` | Clearly marked rehearsal/DEMO; mock printing never claims paper output |
| event | Requires `APP_ENV=production`; blocks demo camera/manual uploads and MockPrinter | Clean guest labels, concise errors; detailed diagnostics in Host Dashboard |

Production environment defaults to Event mode when `OPERATION_MODE` is omitted. A production process cannot silently select development mode. Event mode cannot enable fault injection or mock permission. A real camera must report capture, physical shutter, original JPG transfer and verified hardware capabilities; the current vendor adapter remains blocked until the actual SDK/model/OS integration is supplied and tested.

Network profiles: `local` uses loopback HTTP and development security; `lan` uses explicit RFC1918 LAN HTTP and remains a demo; `https` requires a valid private TLS endpoint or an explicitly configured loopback reverse proxy. HTTPS defaults to Event mode. For mock HTTPS testing, explicitly select rehearsal and mock permission. Conflicting `APP_ENV` and network profiles fail instead of changing the environment silently.

## Configuration file

Copy `deployment/event.env.example` to `deployment/event.env`. The latter is ignored by Git. Keep credentials outside shared/public folders. On macOS/Linux, restrict its permissions with `chmod 600 deployment/event.env`; on Windows, restrict its NTFS ACL to the operator account. Do not commit credentials, certificates, tunnel credentials or runtime files.

The launcher accepts `--env-file deployment/event.env`. It reads plain `NAME=value` lines, optional matching quotes and full-line comments. There is **no shell execution, interpolation or automatic `.env` loading**. Do not use `$HOME`, `%USERPROFILE%` or inline comments as values. Paths in the file are relative to the file's directory; use absolute paths for exported path overrides. Precedence: explicit CLI flags, then exported environment, then file, then defaults. Avoid exporting stale values over the file you intend to use.

| Variables | Purpose |
|---|---|
| `OPERATION_MODE`, `ALLOW_MOCK_HARDWARE`, `APP_ENV` | Event/rehearsal policy and cookie/security environment |
| `HOST_PROFILE`, `HOST_BIND`, `HOST_PORT`, `HOST_LAN_IP` | Private listener/network profile |
| `HOST_SSL_CERTFILE`, `HOST_SSL_KEYFILE`, `HOST_TLS_HOST`, `HOST_BEHIND_PROXY` | Private HTTPS certificate or explicit reverse proxy configuration |
| `PUBLIC_BASE_URL`, `PUBLIC_GATEWAY`, `PUBLIC_PORT` | Stable public photo origin and optional photo-only loopback gateway |
| `OSA_STORAGE_ROOT` | One portable runtime root, including `photobooth.sqlite3`, composites, print-ready files and `.share-key` |
| `OSA_FRONTEND_DIST` | Built frontend directory; use the host build, not a Vite dev server |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `BOOTH_PAIRING_KEY` | Host account (password 12+ characters) and kiosk pairing key (16+ characters) |
| `CAMERA_ADAPTER`, `CAMERA_MODEL`, `CAMERA_DEVICE_INDEX` | Adapter, operator-recorded real model and optional webcam index |
| `CAMERA_GUEST_ENABLED`, `CAMERA_TIMEOUT_SECONDS`, `CAMERA_LEASE_SECONDS`, `CAMERA_STALE_SECONDS` | Camera control permission, timeout, exclusive ownership and preview freshness |
| `CAMERA_ALLOW_FAULTS` | Mock failure injection, development only; forbidden in Event mode |
| `PRINTER_MODE`, `PRINTER_NAME`, `ENABLE_PHYSICAL_PRINTING`, `MAX_PRINT_COPIES` | `mock`/`windows`/`cups`, initial printer selection, explicit physical permission and copy limit |
| `CUPS_LP_COMMAND`, `CUPS_LPSTAT_COMMAND` | Optional executable overrides; default `lp` and `lpstat` found on PATH |
| `GUEST_SESSION_IDLE_SECONDS` | Reset an idle **confirmed** session only; `0` disables. Unsaved captures are preserved |
| `EVENT_GALLERY_POLL_SECONDS` | Approved-photo sidebar refresh interval (3-60 seconds); projector uses its existing feed refresh |
| `MIN_FREE_SPACE_MB` | Reserve checked before new image writes and before sending a new shutter command |
| `OSA_MAX_UPLOAD_BYTES`, `OSA_MAX_IMAGE_PIXELS` | Upload/image limits |
| `LOG_LEVEL`, `OSA_LOG_DIRECTORY` | Log level and private rotating logs; default `runtime/logs` |
| `PHOTOBOOTH_PYTHON`, `NPM_COMMAND` | Optional interpreter/package-manager executable overrides |

The database location is controlled by the runtime root; keep the SQLite/WAL/SHM files together. Moving the database independently of the runtime is intentionally unsupported by the current verified backup procedure. Do not create another gallery database.

`PRINTER_NAME` is the initial configured printer when no Host selection has been persisted. A printer selected in Host Dashboard remains selected for that adapter. Confirm the selected printer after changing hosts. Camera model text documents the intended device; it does not install a vendor SDK or prove compatibility.

## Start, check and stop

Run from the repository root. Windows:

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\run_host.py --env-file .\deployment\event.env --check --no-prompt
.\scripts\start_event.ps1 --env-file .\deployment\event.env --build
.\scripts\stop_event.ps1 --env-file .\deployment\event.env
```

If PowerShell script execution is restricted, use the same Python interpreter with `scripts/run_host.py` or `scripts/stop_host.py` directly; no system execution-policy change is required.

macOS/Linux:

```sh
backend/.venv/bin/python scripts/run_host.py --env-file deployment/event.env --check --no-prompt
sh scripts/start_event.sh --env-file deployment/event.env --build
sh scripts/stop_event.sh --env-file deployment/event.env
```

`--check` validates configuration without starting services, camera, print jobs or a public tunnel. It does not prove hardware/network readiness. The example intentionally requires credentials, actual hostname and private TLS configuration before it passes. Keep both start and stop commands pointed at the same configuration/runtime.

For an explicit local rehearsal without a config file:

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\run_host.py --mode rehearsal --allow-mock-hardware --build
```

Use `backend/.venv/bin/python` for the equivalent macOS command. The launcher prompts for credentials if not exported. Add `--camera uvc_demo` only for a clearly marked webcam-frame rehearsal. HTTPS mock rehearsal additionally needs `--profile https --mode rehearsal --allow-mock-hardware` and valid private TLS/proxy settings.

Use a separate `--storage-root` for rehearsals when possible. Switching to Event mode does not delete or revoke previously approved photos; Host should hide rehearsal images from the event display before opening, while preserving any completed originals required by retention policy.

Start prints the correct private `/booth`, `/admin` and `/event-display` URLs. Admin remains accessible only from the laptop. Pair the iPad using the kiosk code. Issue a separate display code through Host Dashboard. The sidebar/projector only show explicitly approved completed composites; a completed but unapproved session remains private. No gallery tokens, private paths or admin APIs are included in the kiosk feed.

Production guest interface reads its mode from the paired backend, not a hidden frontend DEMO toggle. If configuration cannot be loaded, capture stays disabled. Do not serve `dist-production` expecting host-camera behavior; use `npm run build:host` / `dist-host` and the launcher. Standalone Vite development without kiosk pairing does not fetch the restricted recent-photo feed.

## Public HTTPS and network checks

No script creates/activates a public tunnel. Prepare a persistent Cloudflare tunnel and stable hostname separately with operator authorization. `deployment/cloudflared.example.yml` is a template: replace the UUID, credential-file path and hostname, validate the configuration with the installed Cloudflare tooling, then activate deliberately. Windows/macOS credential paths differ; use an absolute path for the host you deploy on.

Route only `/p/...` to the photo-only gateway on loopback port 8001. Never tunnel the private host port, `/booth`, `/admin`, `/event-display`, `/api`, the runtime root or log directory. The public gateway must return 404 for these private routes. A private HTTPS reverse proxy for iPad/projector is separate from the public photo tunnel. See `deployment/Caddyfile.example`; install/trust private certificates deliberately on the real iPad and include the names/IPs actually used.

Set `PUBLIC_BASE_URL` before confirming event photos. Existing share rows retain their original base URL; changing a hostname does not rewrite printed QR codes. A temporary tunnel URL can change and invalidate future access to those old links. Configuration validation does not probe the public endpoint and does not prove DNS/tunnel/Internet availability. Test a real QR download over 4G/5G and again on event Wi-Fi. During an Internet outage, preserve files and explain that public downloads need connectivity; do not rotate tokens or reprint automatically.

## Recovery, logs and migration

- Reload: the kiosk stores its current owner credential/create key in same-origin **sessionStorage**, then restores saved shots or the confirmed composite from authenticated backend endpoints. Closing the tab, clearing browser storage, losing the pairing cookie or changing origin can prevent automatic recovery. Do not clear storage to troubleshoot an unfinished session.
- After a browser suspends/restores an old page from its navigation cache, use a normal reload if preview/polling does not resume. Saved backend data and the tab's retained session credential are the recovery source; real Safari suspension behavior still needs device testing.
- Unconfirmed reload: saved shots are restored; reapply/review edits and custom frame uploads before confirmation. Edits or image data not yet saved to the backend are not durably recovered. Never auto-confirm a restored session.
- Finalized reload: reuse the same composite and QR; New Session clears the kiosk credential while approved gallery photos remain visible. Idle timeout only resets confirmed sessions with no ongoing save/capture/print submission.
- Camera/transfer errors: retain the capture request key. Use the explicit retry control to receive the original file; do not issue a new shutter command while the previous outcome is uncertain. Check Host diagnostics after USB reconnect.
- Print errors: preserve the final and job record. `submitted` means queue acceptance, not paper confirmation. Inspect spooler/CUPS and paper before explicitly retrying an uncertain job. An unavailable printer does not prevent reviewing/saving/downloading photos.
- Low disk: new writes/shutter commands are stopped before replacing existing photos; Host must restore free space. Never delete finalized composites or `.share-key` as a disk-space fix. Unfinished-session source files require an operator-approved retention decision.
- Logs: supervised private/public services write `private.log` / `public.log`, rotating at 5 MiB with 3 backups, under the configured private log directory. Share-token paths are redacted. Files are not served by an HTTP route. Protect log permissions and retention on the host.
- Restart: stop the owned launcher gracefully, keep runtime/configuration/secrets, then start it again. Do not launch another server over the same runtime or occupied port. A running old backend must be restarted after code updates; rebuilding assets alone cannot add API routes to an already loaded process.
- Backup/migrate: stop accepting guests, finish/check pending physical output, stop services and run `scripts/backup_runtime.py --storage-root <runtime> --output <new-backup>`. Verify every hash in `backup-manifest.json`. Protect the backup: it contains photos, SQLite and `.share-key`. Restore into a new directory, configure `OSA_STORAGE_ROOT`, keep the same public hostname and credentials/pairing key, then verify old QR downloads before use. Never overwrite/delete the source runtime during migration. Reinstall OS-specific SDKs/drivers and rerun hardware acceptance on the new laptop.

See [Windows guide](WINDOWS_EVENT_GUIDE.md), [macOS guide](MACOS_SETUP.md), [event checklist](EVENT_DAY_CHECKLIST.md) and [readiness report](EVENT_READINESS_REPORT.md).
