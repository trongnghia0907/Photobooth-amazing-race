# Current Phase 6 extension — Event Live Gallery

The restricted projection requirement is now implemented separately from Host/Guest pages. Current extension evidence and test counts: [Event Live Gallery verification](EVENT_LIVE_GALLERY_VERIFICATION.md); operator guide: [Event Live Gallery](EVENT_LIVE_GALLERY.md). The 88-backend/25-browser results below describe the earlier Phase 6 baseline; the extension report records the new complete regression run. Current schema is 8. No photo is auto-approved by upgrade, and the public photo gateway remains unchanged.

---

# Full Phase 0–6 audit and Phase 6 integration

Date: 2026-10-30. Scope: current working tree, Windows 11, Chrome headless, isolated SQLite/storage, MockCameraAdapter and MockPrinterAdapter. No commit, push, merge, public tunnel or external resources created. Existing uncommitted Phase 3–5 work preserved. Current deployment instructions supersede historical Phase 2–5 instructions: [Windows event guide](WINDOWS_EVENT_GUIDE.md).

## Evidence and phase summary

The original technical specification, refactor prompt, frontend modules, backend routes/services/migrations, tests and historical reports were inspected. Reports alone were not used as PASS evidence. Before Phase 6 changes: backend **79 passed** (80.80s), Node **9 passed**, browser **21 passed** (3.8m), demo/production/host builds passed. Baseline logs: `.tools/phase6-baseline-backend.txt` plus prior E2E tool output. Runtime user photos were not used as test fixtures or deleted.

Final verification results are recorded below after the final run. PASS in this matrix means the software behavior was executed with mocks/isolated fixtures, not physical hardware.

| Phase | Status | Evidence and limit |
|---|---|---|
| 0 Legacy audit | PASS | Node byte identity + all 80 legacy functions mapped/callable; FUNCTION_INVENTORY; compositor pixel parity in browser |
| 1 Frontend modules | PASS | Node regression, all build modes, browser navigation/editor/layout/retake tests; existing modules reused |
| 2 Backend | PASS | API/retry/filesystem/concurrency tests and actual Uvicorn restart; SQLite remains local |
| 3 QR/Guest | PASS | Confirm→complete→finalize→real QR decode→Guest/download; stable tokens and checksum after restart; Internet/phone not tested |
| 4 Printing/Host | PARTIAL | Mock queue/auth/gallery/reprint tests pass; Windows spooler interface exists, physical printer not tested |
| 5 Camera | PARTIAL | Mock controller, frame/capture/native JPG/transfer/recovery/4+6 shots pass; vendor SDK intentionally not implemented until camera confirmed |
| 6 Integration | PARTIAL | Built same-origin kiosk, 75/25 responsive layout, pairing/CSRF, private/public separation and Windows loopback HTTPS tested; actual iPad/LAN/public tunnel pending |

## Detailed audit matrix

| Feature | Expected / actual behavior | Test evidence | Status | Corrective action / remaining limit |
|---|---|---|---|---|
| Legacy files | Original and legacy remain byte-identical | Node baseline test | PASS | None |
| Function mapping | All 80 old functions retained in module facade | FUNCTION_INVENTORY + Node | PASS | New functions extend facade |
| Navigation/state | Setup/Capture/Result, timer cancellation | E2E setup/capture and Node clearTimers | PASS | None |
| Frames/layouts | Preset/custom transparent PNG; 4 and 6 slots | E2E upload/custom regions/4+6 | PASS | Advanced Frame Editor outside scope |
| Filters | Nine filters, same compositor output | Browser 18 combinations vs legacy; Node | PASS | No compositor rewrite |
| Stickers/text/touch | Existing customization retained | E2E mouse/touch/sticker/text | PASS | Real Safari touch NOT TESTED |
| Old integrations | No external image host, browser-print production path | E2E request guards; production adapter refusal | PASS | Historical legacy file retained only as reference |
| SQLite/images | Durable ownership, valid uploads, atomic file writes | test_sessions, storage failure injection | PASS | Disk backups remain operator responsibility |
| Retry/concurrency | Stable operation keys; no duplicate capture/save/print | Backend concurrency + dropped-ACK E2E | PASS | Uncertain physical shutter/print needs operator inspection |
| Session lifecycle | Working → confirmed immutable official composite | test_storage_lifecycle | PASS | Editing after finalization intentionally closed |
| Cleanup | Final hash checked before allowlisted per-file cleanup | Locked-file, missing/corrupt final, traversal tests | PASS | New confirmations only; interrupted drafts retained |
| Existing-data upgrade | Preserve all pre-existing photo files/share URLs | test_upgrade_preserves_preexisting_completed_files | PASS | Migration 7 changes old pending/blocked to retained_legacy |
| One official final/token | Same session cannot create a second final/share | Backend + full production E2E | PASS | Historical published links kept compatible |
| Real QR | Created only after successful save and complete | QR decode tests + browser confirm | PASS | No fake token or third-party QR service |
| Guest download | Exactly token's own completed composite/QR derivative | Image checksums, isolation, direct/refresh, restart | PASS | Share token is bearer access; anyone given it can view that photo |
| Invalid/missing files | Safe 404/503 without private filesystem paths | Backend sharing/missing-file tests | PASS | No public directory/gallery |
| URL config | Strict HTTPS public, explicit localhost/LAN development | Sharing and deployment tests | PASS | Published origin pinned; plan stable hostname before event |
| Print-ready | Adds QR footer below slots, preserves original | Pixel crop/hash and QR decode tests | PASS | Actual paper margins/QR readability NOT TESTED |
| Queue/copies | Bounded copies, persisted states, idempotent keys | test_printing and production E2E two copies/restart | PASS | submitted is OS acceptance, not paper completion |
| Printer failure/reprint | Failed/uncertain jobs retained; explicit Host retry | Mock error/cancel/retry tests | PASS | Hardware disconnect NOT TESTED |
| Host auth/logout | Password hash, strict HttpOnly cookie, CSRF/login throttle | Backend auth + real loopback HTTPS | PASS | Operator supplies credentials, no defaults |
| Gallery | One item per completed session, final + print-ready only | Backend + production Host browser | PASS | Incomplete recovery metadata only via explicit include_working |
| Camera abstraction | Status/capabilities, exclusive process/session lease | test_camera | PASS | Mock SOFTWARE VERIFIED |
| Live Preview | Same-origin JPEG sequence/stale watchdog | Mock moving frame E2E and timeout tests | PASS | Actual latency/USB not tested |
| Capture sequence | One command/slot, wait transfer before next | E2E 6+retake+4 asserts 11 capture commands | PASS | No Live Preview screenshots used by host capture |
| Physical original JPG | Trigger supported shutter, retrieve native file | Vendor adapter refuses unsupported operation | NOT IMPLEMENTED | Camera model/SDK/device required; no invented support |
| UVC demo | Explicit frame-only demo, never real DSLR claim | Adapter capability/production refusal tests | PASS | Physical OpenCV/webcam NOT TESTED; native hung call may need process recovery |
| Setup 75/25 | Centered event heading, same-session sidebar, preview/options | Production browser geometry + screenshots | PASS | Real iPad acceptance pending |
| Fullscreen | CSS overlay hides setup/header/sidebar, preserves preview ratio | Host 4/6 E2E, production sequence | PASS | Native Fullscreen optional; Safari CSS fallback not hardware tested |
| New Session | Clears photos/stickers/text/filter/QR; confirm discard | Production privacy reset + browser state | PASS | Full page reload cannot restore working canvases automatically |
| Touch/responsive | 44px controls, focus rings, safe areas, zoom allowed | 820×1180 /1180×820 viewport, screenshots | PASS | Physical iPad NOT TESTED |
| Same-origin built app | `/`, `/booth`, `/assets`, `/api`, `/p` without Vite | Launcher E2E + static/API route tests | PASS | No catch-all SPA route swallowing API |
| Kiosk permissions | Paired station + owner token + mutation CSRF | Cross-station/owner/CSRF/logout/rate tests | PASS | Pair code grants trusted kiosk access; protect it |
| Admin isolation | Actual loopback client only, authenticated data | Remote spoofed forwarded header denied | PASS | Trust only configured loopback reverse proxy |
| Production security | Secure cookies, no CORS grants, no Swagger/assets/secrets leak | TLS/cookie/404/token/path/rate tests | PASS | Private kiosk CSP permits legacy inline handlers; no user HTML interpolation added |
| Public boundary | Dedicated app serves only token page/media and minimal health | Public route-denial tests; E2E gateway | PASS | Tunnel config routes `/p` only; never tunnel port 8000 |
| Windows launcher | One private worker, optional photo-only worker, graceful stop/restart | Actual subprocess TLS + E2E restart | PASS | Not a Windows service installer |
| Backup/recovery | Offline coherent DB/files/secret, hash manifest, no overwrite, restore | Active backup refusal + E2E backup hash checks + test_backup_restore | PASS | Keep backup private; restore to another runtime directory |
| Actual LAN | iPad and phone access same Wi-Fi IP | Config/URL software validation only | NOT TESTED | Must test real Wi-Fi, firewall, DHCP/client isolation |
| Public HTTPS | Phone over 4G/5G reaches stable tunnel hostname | Config prepared; no tunnel started | NOT TESTED | Operator enables tunnel and tests certificate/routing |
| Physical print/camera/event | Original capture/real paper/device recovery | Manual checklist only | NOT TESTED | Hardware blockers; NO-GO for physical event |

## Fixes and integration choices

Migration 7 preserves old pending cleanup files before workers start. New confirmations retain the existing durable-final-first cleanup policy. Failed saves and unconfirmed sessions keep working originals. No broad directory deletion or retention timer was introduced.

The existing home cards, camera preview panel, countdown, editor and result controls were moved/reused. The mirror control now also updates the host preview (preview only; original JPG unchanged). New kiosk module/styles arrange Setup and the private current-session sidebar; a CSS fullscreen overlay works independently of native Fullscreen permission. New Session clears prior guest's custom text, filter, canvases and QR along with existing photo/sticker/session cleanup.

The previous development backend allowed session creation without station enrollment. Built deployment now requires pairing, a separate owner token, station binding and CSRF for camera/save/print operations. Host stays loopback-only and authenticated. Public photo process has no private routes, Swagger or hardware workers. Development Vite remains loopback-oriented and must not be used as the public gateway.

The Windows launcher uses process leases and supervised stop markers. A shutdown race found during E2E was fixed: stop intent survives until the supervisor sees it. Startup failures release already-started workers and process locks. Backup refuses an active runtime and checks hashes without deleting original files.

## Final test results

Environment: Windows, Python 3.12.10, Node v26.13.0, npm 11.20.0, Chrome headless. All runtime test data isolated.

| Command (working directory) | Actual final result | Evidence |
|---|---|---|
| `npm.cmd ci` (`frontend`) | PASS; 85 packages installed, npm audit reported 0 vulnerabilities | `.tools/phase6-install.txt` |
| `.venv/Scripts/python.exe -m pytest tests -q` (`backend`) | **88 passed, 1 warning in 182.83s (0:03:02)** | `.tools/phase6-final-backend.txt` |
| `npm.cmd test` (`frontend`) | **9 passed**, including 80-method mapping and legacy byte identity | Tool output after final builds |
| `npm.cmd run build` | PASS, 48 modules | Final tool output |
| `npm.cmd run build:production -- --outDir dist-production` | PASS, 48 modules; demo capture disabled | Final tool output + production guard E2E |
| `npm.cmd run build:host` | PASS, 48 modules; built private kiosk | Final tool output + deployment E2E |
| `npm.cmd run test:e2e -- --config playwright.isolated.config.js` | **21 passed (5.6m)** | `.tools/phase6-final-regression-e2e.txt` |
| `npm.cmd run test:e2e -- --config playwright.deployment.config.js` | **1 passed (1.5m)**, complete two-guest workflow, actual process restart, sidebar retake/cancel-discard/privacy/mirror/backup | `.tools/phase6-production-e2e.txt` |
| `npm.cmd run test:e2e -- --config playwright.qr-confirm.config.js` | **3 passed (1.1m)**; automatic localhost QR, missing config, retry/image failure, download | `.tools/phase6-qr-smoke.txt` |
| `git diff --check` | PASS; Windows LF/CRLF notices only | Final tool output |

Backend suite includes decoded LAN QR, actual loopback TLS with certificate verification (no system trust changes), Secure-cookie login/logout, duplicate runtime refusal, active-backup refusal, and offline restore preserving both photo downloads/share tokens and two-copy submitted queue. Browser suites total **25 passing scenarios**. The final preview-only mirror fix was rebuilt and checked in deployment E2E; original captured JPG/compositor paths remain unchanged.

Minor test warnings: upstream Starlette/httpx deprecation and Playwright NO_COLOR/FORCE_COLOR notice (PowerShell may label redirected native stderr as NativeCommandError; the Playwright result is passed with no failed tests). npm 11 initially declined an undeclared dependency install script; `package.json` now explicitly allows only the locked `esbuild@0.28.2` postinstall, and fresh `npm ci` passed. No new runtime dependency was added. The final HTTPS CA-trust adjustment was rechecked with `pytest tests/test_windows_launcher.py -q`: **1 passed in 7.23s**, evidence `.tools/phase6-tls-final.txt`. Python compileall and diff whitespace checks also passed.

Screenshots: `docs/screenshots/phase6-setup-landscape.png`, `phase6-setup-portrait.png`, `phase6-current-session-sidebar.png`; previous capture/result/Host evidence remains available. Headless desktop viewports are not a physical Safari/iPad test.

Early validation found a wrong test metadata field (`token` vs `share_url`) and a wrong DOM selector; corrected tests to match the real API/UI. Three browser checks initially timed out during concurrent heavy canvas/backend runs; all passed when rechecked serially. Final isolated suite uses 15-second asynchronous UI assertions and 180-second per-test budget (same behavior assertions), separate output folders, no automatic retries. A test invocation from repository root initially lacked the backend package path; documented command runs from `backend`.

## Files

Phase 6 additions: `backend/app/{booth_access,deployment,public_main,runtime_lock}.py`, migration `007_deployment.sql`, `backend/tests/{test_deployment,test_windows_launcher,test_backup_restore}.py`; `frontend/src/features/home/kiosk.js`, `frontend/src/services/booth-access.js`, `frontend/src/styles/kiosk.css`, deployment Playwright config/spec; `scripts/{run_host,serve_app,stop_host,backup_runtime}.py`; deployment Caddy/cloudflared examples; this report, Windows event guide, hardware/event checklist and screenshots.

Phase 6 edits: backend configuration/lifespan/routes/root/admin auth/gallery/sharing/print footer/schema expectations; frontend bootstrap/store/router/home/capture/host-camera/API client/camera selector/QR warning/index/CSS imports; environment/gitignore and current README/API/security/storage/migration notes. No source file intentionally removed. [Full working-tree inventory](PHASE6_FILE_INVENTORY.md) includes pre-existing uncommitted Phase 3–5 changes, labeled as such.

## Readiness and remaining issues

**READY FOR LOCAL SOFTWARE DEMO** (Mock camera/printer). **LAN demo:** configuration ready, actual network NOT TESTED. **Public HTTPS demo:** isolated loopback TLS verified, real hostname/tunnel/phone NOT TESTED. **Physical event:** NOT READY; camera model/SDK, camera original transfer, printer, iPad and both real networks remain unverified.

Critical known software issues: none reproduced in the verified workflows. Hardware-dependent major blocker: vendor capture integration cannot be completed honestly without model/SDK/device. Deployment-dependent: certificate trust, domain/tunnel authorization, firewall and stable IP. Minor: private kiosk retains legacy inline event handlers (`unsafe-inline` CSP); full working-session recovery after browser reload is not implemented, though server working files remain and same-operation network retries work while browser is open. Rate limits are process-local for a single private worker. Automatic age-based deletion of interrupted sessions is deliberately absent pending an approved retention policy.

See [Windows commands and operator/troubleshooting guide](WINDOWS_EVENT_GUIDE.md) and [manual acceptance/event checklist](EVENT_DAY_CHECKLIST.md). Stop at Phase 6; no additional phase initiated.
