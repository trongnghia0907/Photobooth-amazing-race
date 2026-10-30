# Phase 6 extension — Event Live Gallery verification

Date: 2026-10-30. This is a scoped addition to Phase 6, not a rewrite or a new phase. Existing uncommitted Phase 3–6 work retained. No commit/push/public deployment; no real user photos used or deleted in tests.

## Audit and design

Repository searches for event-display, live gallery and slideshow found no existing event presentation feature. Host gallery and token-scoped Guest Photo Page existed; neither was repurposed or exposed. Added a dedicated private-app route using the same Repository/SQLite and immutable session_finals composite.

Schema 8 adds event_display_config, event_display_sessions and event_display_photos. Existing photos are not opted in. Each approved item has a session primary key, immutable composite reference, separate display UUID, consent/authorization basis, approving Host and timestamps. No secondary image store/database/upload service.

Host generates a separate random code (hash only at rest). Display receives only a scoped 12h HttpOnly cookie, no Host or owner credential. Rotation/revoke invalidates all display sessions. Unlock requires custom header and rate limit. Host approval/hide/access controls use existing Host authentication, CSRF and laptop-only deployment restrictions. The public photo process and tunnel routing exclude the entire feature.

## Requirements and evidence

| Requirement | Actual verification | Status |
|---|---|---|
| Title/dark 16:9 wall/slideshow | Browser at 1920×1080, no horizontal/vertical overflow, screenshots | PASS |
| Explicit approval/default private | Unapproved final/draft absent; missing attestation/basis rejected | PASS |
| One session, one official composite | DB uniqueness + repeated approval; original PNG hash/dimensions match, no print-ready footer | PASS |
| 4/6 layouts and newest-first | Both aspect ratios verified in browser; newly approved image promoted | PASS |
| Automatic updates | Browser stays on page while Host approves/hides, no reload | PASS |
| Slideshow/fullscreen | Automatic 5s change + native Fullscreen API after click | PASS |
| Empty/offline recovery | Empty state; abort feed, images clear, unroute restores automatically | PASS |
| Hide/reapprove | Media access closes; original/QR download and token remain intact; same item UUID restored | PASS |
| Access separation | Display cookie cannot call Host/owner APIs; public gateway routes 404 | PASS |
| Metadata minimization | Exact feed field allowlist; no share/session/token/storage/download metadata | PASS |
| CSRF, expiry, revoke, rate limit | Backend tests, Secure cookie over HTTPS TestClient; code rotation clears live display | PASS |
| Migration/restart | Schema-7 upgrade keeps photos private/unchanged; actual launcher restart restores live display and state | PASS |
| Missing/corrupt/path safety | Approve verifies final hash; missing media excluded; altered path/traversal rejected | PASS |
| Projector/LED at venue | No physical projector or venue network available | NOT TESTED |
| Previous Phase 1–6 regressions | 21 legacy + production/QR browser groups re-run successfully | PASS |

The existing reprint browser check initially detected an ambiguous input selector after adding consent inside the old composites container. Moved consent controls to their own eventDisplayApproval sibling, preserving the original image/reprint DOM contract; all 21 existing tests then passed without weakening those tests. Initial event browser run timed out. During follow-up, fixed stale Host detail controls while changing selected sessions, ignored late detail responses after selection/logout, and cleared old access code while rotating. Also constrained the projector stage to the viewport, added bounded browser action timeouts and per-step evidence. Final event scenario passes; the full workflow includes actual process restart and live code revocation.

## Commands and results

- Backend full suite: **94 passed**, 1 upstream Starlette/httpx deprecation warning, 216.81s. Command from backend: .venv/Scripts/python.exe -m pytest tests -q. Log: .tools/event-gallery-backend-full.txt.
- Node regression: **9 passed**, including all 80 legacy methods and original/legacy byte identity.
- Demo, production and host frontend builds: **PASS**, 48 modules each. No new dependency.
- New event browser E2E: **1 passed (45.0s)**. Command from frontend: npm.cmd run test:e2e -- --config playwright.event-display.config.js. Log: .tools/event-gallery-e2e.txt.
- Existing browser regressions: **21 passed (2.8m)** via playwright.isolated.config.js (.tools/event-gallery-regression-e2e.txt); existing built production two-guest capture/QR/print/Host/restart/backup **1 passed (1.2m)** via playwright.deployment.config.js (.tools/event-gallery-production-e2e.txt); localhost QR smoke **3 passed (23.2s)** via playwright.qr-confirm.config.js (.tools/event-gallery-qr-smoke.txt). With the new event scenario, **26 browser scenarios passed**. No automatic test retry/skip was used to claim success.
- Static JavaScript syntax (node --check on display.js/dashboard.js), Python compileall and git diff --check: **PASS**. Event backend cases additionally rechecked after explicit unauthorized-media assertions: **6 passed (11.33s)**; this recheck is not counted twice in the 94-test total.

Screenshots: docs/screenshots/event-display-wall-1920.png and event-display-slideshow-1920.png.

## Relevant files

Added:

- backend/app/event_display.py — service, restricted display routes and Host controls.
- backend/app/event_ui/index.html, display.css, display.js — independent projection UI.
- backend/app/migrations/008_event_display.sql — metadata/access migration; no photo deletion.
- backend/tests/test_event_display.py — consent/privacy/restart/migration/URL tests.
- frontend/playwright.event-display.config.js and tests/event-display/event-display.spec.js — real launcher/browser scenario.
- docs/EVENT_LIVE_GALLERY.md and this verification report.
- Two event-display screenshots.

Edited:

- backend/app/database.py, main.py — migration and private-app registration.
- backend/app/printing_routes.py — Host approval state in completed gallery/detail.
- backend/app/admin_ui/index.html, dashboard.js — consent/access/hide controls and safe detail loading.
- backend/tests/test_sessions.py, test_sharing.py, test_deployment.py — current schema expectations only.
- frontend/vite.config.js — same-origin development proxy for /event-display.
- scripts/run_host.py — print the new operator URL.
- README, Technical Specification and current Phase 6/API/security/migration/acceptance/operator/checklist documentation.

No original HTML, camera SDK, compositor algorithms, Frame Editor, QR/token generation, printer adapter or public-photo app was changed for this feature. Complete working-tree inventory, including earlier uncommitted work: PHASE6_FILE_INVENTORY.md.

## Remaining limitations

Latest 9 photos in the wall, latest 60 in slideshow, 5/8/12-second slide intervals; no multi-event playlist/pagination UI. Polling means a small delay (2.5s after each completed request; 5s request timeout); hiding/revocation reaches connected screens on next poll. During network loss photos are cleared rather than cached offline. Display sessions last 12h; operator re-enters the code when needed. A person who already viewed approved content may retain a screenshot/copy.

Projector/LED hardware, HDMI/USB-C setup, physical fullscreen/brightness/readability and venue network remain NOT TESTED. Existing camera/printer/iPad/public-network hardware limitations remain as stated in the Phase 0–6 report. Operator instructions: EVENT_LIVE_GALLERY.md.
