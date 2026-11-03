# AMAZING RACE 2026 — Event Readiness Report

Audit date: 2026-10-31 (Asia/Saigon). Verification results below are completed software checks unless explicitly marked pending/manual.

**Physical event assessment: NO-GO.** Exact camera model/vendor SDK integration, physical printer/paper and venue network/device acceptance are not available for verification. The vendor CameraAdapter deliberately remains blocked. Passing MockCamera/MockPrinter tests must not be treated as physical event approval.

## 1. Deployment architecture

The iPad uses the built Guest UI on the private FastAPI host. That host owns the existing SQLite runtime, CameraAdapter, durable print queue and composite files. Host Dashboard remains local to the laptop. Event Live Gallery uses a separate display credential and explicitly approved composites. The kiosk sidebar reuses the same approval/file checks through a paired-kiosk read-only feed.

A separate loopback public-photo gateway serves only token-scoped `/p/...` pages/images/QR/downloads. A deliberately configured public HTTPS tunnel may point only to that gateway. No tunnel was created or activated during this audit. No second database or third-party image hosting was added.

Each completed session has one immutable official composite and one stable share token. Original camera JPG/working captures remain temporary until a successful final commit; print-ready is a derivative with a separate QR footer. Existing completed photos and archived legacy source were preserved.

## 2. Audit findings and changes

| Finding | Implemented response |
|---|---|
| Network environment and demonstration hardware policy were conflated | Separate `APP_ENV` from `OPERATION_MODE`; explicit rehearsal permission; Event rejects mock/unverified camera, demo/manual uploads and MockPrinter |
| Launcher overwrote configured camera/printer/URL values | Explicit config-file/environment/CLI precedence, strict booleans, profile mismatch errors and platform-relative paths |
| A stale/occupied server could be mistaken for a newly launched service | Runtime ownership locks retained; occupied-port check before child startup; clear restart guidance |
| Technical/demo text appeared throughout Guest UI | Server-driven Event presentation, concise guest errors, retained detailed Host diagnostics, visible rehearsal labels |
| Reload could lose kiosk access to its already saved shots/final | Same-origin sessionStorage recovery of owner/create context; authenticated backend reload; never auto-confirm working shots |
| Idle behavior needed a safe boundary | Configurable timeout resets only confirmed sessions with no active save/capture/submission; unfinished work remains |
| Sidebar polling repeatedly rebuilt/re-encoded unchanged images | Reuse review thumbnails through a WeakMap and keep unchanged approved-gallery DOM |
| Print adapter was Windows-only | Lazy Windows GDI import and optional CUPS adapter, same SQLite queue, explicit permission, conservative uncertain submission handling |
| Low-disk errors occurred too late | Configurable reserve checked before new image writes/shutter commands; retain old slots/final data |
| Toast messages were interpolated as HTML | Render message text through DOM textContent; browser injection regression check |
| Operator diagnostics/logging were incomplete | Private readiness data (mode/OS/disk/hardware blockers), rotating redacted private/public logs |
| macOS operation and host migration were undocumented | Shared Python launcher, PowerShell/shell wrappers, separate macOS instructions and consistent backup/migration procedure |

The new MIME check also rejects images whose declared JPEG/PNG/WebP type does not match the decoded file format. Real-camera transfer requires a camera-original JPEG receipt; no preview element is used as its substitute.

## 3. Files changed in this audit

The working tree already contained earlier Phase 0-6 changes. This list describes this audit's scope, not every pre-existing uncommitted file.

- Configuration/operations: `backend/app/config.py`, `scripts/run_host.py`, `scripts/run_local_backend.py`, `scripts/stop_host.py`, `scripts/serve_app.py`, `scripts/frontend_command.py`, new `scripts/host_environment.py`, `scripts/start_event.ps1`, `scripts/stop_event.ps1`, `scripts/start_event.sh`, `scripts/stop_event.sh`, `.gitattributes`, `.gitignore`, `backend/.env.example`, new `deployment/event.env.example`, `deployment/cloudflared.example.yml`.
- Backend/Host: `backend/app/booth_access.py`, `routers.py`, `printing_routes.py`, `logging_filters.py`, new `readiness.py`, `event_logging.py`, `admin_ui/index.html`, `admin_ui/dashboard.js`, `admin_ui/dashboard.css`.
- Storage/hardware services: `services/repository.py`, `images.py`, `sharing.py`, `print_ready.py`, `printing.py`, `printers.py`, new `cups_printer.py`, `camera/controller.py`, `camera/uvc_demo.py`.
- Guest frontend: `frontend/src/main.js`, `core/bootstrap.js`, `core/store.js`, `core/events.js`, `features/home/home.js`, `features/home/kiosk.js`, `features/capture/capture.js`, `services/host-camera.js`, `photo-repository.js`, `print-client.js`, new `event-config.js`, `session-recovery.js`, `components/toast.js`, `qr-status.js`, `qr-view.js`, `styles/kiosk.css`.
- Tests: new `backend/tests/test_event_configuration.py`, `test_event_stability.py`; adjusted `test_printing.py`, `test_restart.py`, `test_windows_launcher.py`; `frontend/tests/backend-server.js`, `deployment/production.spec.js`, new `deployment/event-readiness.spec.js`, `session-recovery.test.js`, `event-display/event-display.spec.js`.
- Documentation/evidence: `README.md`, `docs/WINDOWS_EVENT_GUIDE.md`, new `MACOS_SETUP.md`, `EVENT_CONFIGURATION.md`, this report, updated `HARDWARE_COMPATIBILITY.md`, `EVENT_DAY_CHECKLIST.md` and generated synthetic browser screenshots, including `event-clean-blocked.png`.

No commit, push, merge, Git-history change, public deployment, automatic system startup task or uncontrolled physical print job was performed.

## 4. Required environment and operation modes

See [EVENT_CONFIGURATION.md](EVENT_CONFIGURATION.md) and [event.env.example](../deployment/event.env.example) for the complete variable table and precedence.

Required for an event configuration: `APP_ENV=production`, `OPERATION_MODE=event`, `ALLOW_MOCK_HARDWARE=false`, `HOST_PROFILE=https`, trusted private TLS/proxy settings, actual `PUBLIC_BASE_URL`, `OSA_STORAGE_ROOT`, built `OSA_FRONTEND_DIST`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `BOOTH_PAIRING_KEY`, an implemented/verified real camera adapter/model and the intended physical printer/driver/name. Physical printing additionally requires `ENABLE_PHYSICAL_PRINTING=true` and an available printer. The example intentionally does not fabricate credentials, hostname, SDK or printer readiness.

Development keeps diagnostics and demonstration behavior. Rehearsal requires explicit mock permission and keeps DEMO labels/printing warnings. Event mode gets its policy from the backend, blocks unsupported capture at both backend and guest boundary, hides operator details and preserves concise errors. Changing OS/laptop uses configuration, compatible SDK/driver dependencies and runtime restore; the shared application logic stays the same.

The database remains `OSA_STORAGE_ROOT/photobooth.sqlite3`, alongside its SQLite WAL/SHM and photo data, to preserve the verified single-runtime backup procedure. Logs default to `runtime/logs`. `PRINTER_NAME` supplies the initial choice; an existing Host printer selection remains persisted for its adapter.

## 5. Verification environment and test results

Environment: Windows 11, build `10.0.26300`, AMD64; Python `3.12.10`; Node `26.13.0`; npm `11.20.0`; desktop Chrome `156.0.8078.48`. Browser viewports emulate iPad sizes and 16:9 displays; this is not physical iPad Safari/projector verification.

| Check | Result |
|---|---|
| Pre-change backend baseline | 95 passed |
| Pre-change frontend baseline | 11 passed |
| Backend regression/security/hardware mocks/backup/restart, excluding separate long-run case | 100 passed; 1 pre-existing Starlette/httpx deprecation warning |
| Latest focused configuration/logging/launcher TLS checks, including two additional cases after that collection | 8 passed (overlaps earlier cases) |
| 30-session stability case | PASS; metrics below; separate invocation also passed its focused configuration/GDI cases |
| Final frontend unit/baseline | 13 passed, including corrupt-cache guard and credential clearing |
| Demo, production-disabled and host builds | All passed; 50 modules each |
| Deployment E2E (existing full flow + new recovery/idle/Event guard) | 2 passed |
| Existing isolated frontend regression | 22 passed |
| QR confirmation/error E2E | 3 passed |
| Event Display 16:9 approval/slideshow/hide/reconnect/restart E2E | 1 passed |
| PowerShell wrappers | Start/stop `--help` passed; actual shared Python launcher startup/shutdown verified through TLS and browser tests |
| POSIX wrappers | Shell syntax checked on Windows tooling; actual macOS/Linux execution NOT TESTED |
| Whitespace/diff check | Passed |

The focused checks cover default production fail-closed policy, explicit rehearsal, backend camera guard before any shutter, source-upload denial in Event mode, no anonymous Host API access, disk reserve preserving old photos, config-file paths/precedence/no shell interpolation, CUPS fake submission/timeout, typed log redaction and preflight from another working directory without starting services.

The browser suites completed 28 cases in total. After those runs, a final guard was added so corrupt browser recovery data blocks capture rather than creating a replacement session. The final 13 frontend unit cases and all three builds passed with this guard. Its additional browser assertion was not rerun at the operator's explicit request to stop further checks and conserve quota. No further test runs were started after that request; only already-running builds were completed and this report finalized.

Browser deployment checks cover 6 shots, retake, filters/stickers/frame adjustment, confirmation before finalization, real generated QR/Guest download, mock two-copy request, Host, a second 4-photo session, automatic approved-sidebar ordering, page refresh/New Session persistence, actual subprocess restart and verified offline backup. New checks reload unconfirmed shots and finalized delivery, preserve the same QR, keep unconfirmed work through idle timeout, reset only confirmed idle state and reject an unverified camera under simulated Event presentation. The latter is a presentation test; actual backend Event guards have separate tests and no physical camera was verified.

## 6. Thirty-session measurements

Measurements from the [stability test](../backend/tests/test_event_stability.py) were produced from synthetic camera-generated JPEG files and a real composite assembled from each session's saved shots. There was no physical camera or OS print submission.

| Measurement | Observed result |
|---|---|
| Sessions | 30: fifteen 4-photo and fifteen 6-photo sessions |
| Retakes | 10; total Mock shutter calls 160 |
| Official composite/token count | Exactly 30 / 30, one per completed session; tokens stable on replay/restart |
| Mock print jobs | Exactly 30, two copies requested per job; duplicate request keys reused the same job |
| Approved gallery items | 15; unapproved sessions absent; approved state survived restart |
| Full simulation elapsed | 135.431 seconds, including assertions/restart |
| Mean / min / max session loop | 4.359 / 2.668 / 7.909 seconds |
| Retained Python allocation growth after warm-up | 0.117 MiB |
| Traced Python peak | 3.585 MiB |
| Active threads during samples | Constant at 5 |

The loop omits guest countdown/human interaction and is not an event-throughput promise. Memory uses tracemalloc Python allocations, not process RSS, browser heap, native Pillow buffers or a vendor SDK. A long physical soak, Safari memory/suspension and native-driver resource behavior remain untested. Fault injection verified transfer retry without another shutter and final-save failure with retained captures; recovery then completed successfully. All 30 downloads retained identical hashes after backend restart, and their temporary source images were cleaned only after finalization.

## 7. Camera and printer readiness

Camera: Mock and optional webcam-frame contracts work for demonstrations. The fake SDK contract verifies original-file boundaries only. A real model, firmware, manufacturer SDK/version/license, supported OS/CPU architecture and connected device are still missing. `vendor` remains BLOCKED BY HARDWARE. No source-code edit is needed for ordinary event configuration changes, but actual vendor integration must be completed and accepted **before event day**.

Printer: Windows GDI/Spooler has existing fake-driver/copy/contain/ambiguous-failure tests. The CUPS adapter uses the existing durable queue and documented [`lp`](https://openprinting.github.io/cups/doc/man-lp.html) / [`lpstat`](https://openprinting.github.io/cups/doc/man-lpstat.html) interfaces; fake-process tests verify options, explicit permission and uncertain timeout handling. Actual Windows/CUPS drivers, paper dimensions, color, margins, filters, USB/network disconnect and paper output remain NOT TESTED. The current CUPS discovery supports ASCII queue names made from letters, numbers, underscores, dots and hyphens; configure a compatible queue name. Spooler acceptance never sets physical_print_confirmed=true.

## 8. QR, iPad and Event Gallery readiness

QR generation/decoding, individual Guest page isolation/download, missing/invalid origin errors and stable tokens are software-tested. Public DNS, persistent Cloudflare tunnel, trusted private TLS on iPad and a phone download over 4G/5G were NOT TESTED. Browser offline indication avoids claiming downloads are available during an outage; configured HTTPS is not a connectivity probe. Preserve the original hostname for printed QR codes.

Guest layout retains the centered event title, approximately 75/25 setup/review layout, approved composite sidebar, fullscreen capture interface, progress within Capture/Review and explicit final confirmation. Capture hides the sidebar. New Session keeps approved gallery data while clearing guest state. Frontend reload restores backend-saved shots/final, but unsaved filter/sticker/custom-frame edits must be reviewed/reapplied. Tab closure, cleared storage, lost pairing or changed origin can block automatic browser recovery; backend finals remain durable.

Event Gallery retains explicit Host consent/authorization, independent display access, hide without deletion, approved-only media and minimal metadata. Real projector brightness/HDMI/USB-C, Safari fullscreen/touch and venue network loss still need manual acceptance. Previously approved rehearsal photos must be hidden manually or kept in a separate rehearsal runtime; mode switching never deletes existing photos.

## 9. Security and failure-recovery assessment

Completed software checks preserve Host authentication/CSRF/loopback restrictions, paired kiosk ownership, owner-token session isolation, immutable final composites, share-token scoping, path validation and approved-only gallery access. Public gateway has no booth/admin/gallery/control/storage routes. Config secrets are not returned by the guest configuration endpoint. Toast HTML injection was removed, and token paths are redacted from supervised logs without breaking access-log formatting.

| Failure | Software behavior / remaining manual check |
|---|---|
| Backend/process restart | Final/QR/gallery/queue survive; uncertain capture/print work is not blindly resubmitted |
| Frontend reload | Saved session restored using the tab credential; no automatic guest confirmation |
| Lost capture/final/print ACK | Existing idempotency keys retained; backend replay prevents duplicate commands/jobs |
| Camera transfer/save error | Retain old slots and transfer receipt; explicit retry; physical USB/SDK reconnect still NOT TESTED |
| Low disk / injected write failure | New write/shutter refused, old photo retained; physical power loss/filesystem failure NOT TESTED |
| Printer unavailable/uncertain | Photo remains; queue record retained; explicit review/retry; native physical behavior NOT TESTED |
| Simulated connection loss | Polling/error recovery tested; real Wi-Fi/Internet/tunnel outage NOT TESTED |
| Browser navigation-cache suspension | Normal reload is the safe recovery procedure; real Safari suspension NOT TESTED |

Do not expose config/runtime/logs or use a public tunnel on the private host port. There was no comprehensive external penetration test. Protect sessionStorage through the application's same-origin/CSP controls and keep kiosk/Host use under operator control; do not clear the tab or storage while a guest's save outcome is unresolved.

## 10. Platform validation matrix

| Platform | Startup/stop/restart | Camera | Printing | Platform claim |
|---|---|---|---|---|
| Windows 11 AMD64 (this environment) | Shared Python launcher, TLS secure cookies, runtime exclusivity, graceful stop and backup TESTED; wrapper entrypoints checked | Mock/contracts TESTED; real vendor camera BLOCKED BY HARDWARE; actual webcam NOT TESTED | Mock/GDI contracts TESTED; physical output NOT TESTED | Software local-demo validation only; not fully hardware-supported |
| macOS | Shell/Python paths and guide provided; syntax reviewed, native execution NOT TESTED | SDK/model/OS/CPU compatibility NOT TESTED | CUPS fake contracts tested on Windows; real macOS CUPS/output NOT TESTED | Alternative platform implementation; full support NOT claimed |
| Linux | POSIX-oriented shared code and shell wrappers; native execution NOT TESTED | NOT TESTED | CUPS availability/driver/output NOT TESTED | Optional best-effort only |

Changing laptops requires restoring one consistent runtime/configuration and compatible OS-specific SDK/drivers, not rewriting the frontend/API/QR/gallery/storage logic. Repeat all hardware/network acceptance after migration.

## 11. Startup commands and manual acceptance

From the repository root, a Windows local rehearsal:

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\run_host.py --mode rehearsal --allow-mock-hardware --build
```

macOS equivalent (native execution still NOT TESTED):

```sh
sh scripts/start_event.sh --mode rehearsal --allow-mock-hardware --build
```

For a configured private HTTPS deployment, use `scripts/start_event.ps1 --env-file deployment/event.env --build` or `sh scripts/start_event.sh --env-file deployment/event.env --build`, after `run_host.py --env-file ... --check --no-prompt`. Replace example values and establish private TLS/public routing deliberately. These commands do not bypass the real-camera blocker or authorize a public tunnel/physical test print.

Stop the old operator launcher before running updated code; the already loaded server on port 8000 is not upgraded by rebuilding frontend files. Keep the same runtime, credentials and pairing key. Automated tests used isolated temporary runtimes/ports and did not restart the operator's existing instance or modify its completed photos.

Follow [EVENT_DAY_CHECKLIST.md](EVENT_DAY_CHECKLIST.md): record real camera shutter/JPG/retake/disconnect evidence, one controlled physical print and paper QR scan, iPad Safari and projector operation, Wi-Fi reconnection, public QR over 4G/5G and offline backup restore. Do not mark those items passed from mock results.

## 12. Final Go/No-Go

- **READY FOR LOCAL DEMO:** software-tested on the Windows environment above, using the new built app and explicit rehearsal/mock configuration.
- **READY FOR LAN DEMO:** configuration/URL safeguards prepared; real iPad/Wi-Fi/firewall acceptance NOT TESTED, so not awarded for the venue.
- **READY FOR HTTPS DEMO:** loopback TLS/security and routing tests passed; real public hostname/tunnel/4G/5G acceptance NOT TESTED, so public-event readiness is not awarded.
- **READY FOR PHYSICAL EVENT:** **NO-GO** until actual vendor-camera integration, printer/paper and all required hardware/network checks pass on the intended host OS. macOS/Linux are not claimed fully supported.

Remaining blockers require actual model/SDK/driver/device/network information and evidence. All available software work was performed without activating a public deployment. Stop here for operator review and hardware acceptance.
