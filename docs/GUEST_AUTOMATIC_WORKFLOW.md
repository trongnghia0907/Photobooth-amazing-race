# Guest UI — continuous automatic workflow

The Guest UI no longer contains the numbered three-step navigation. AMAZING RACE 2026 stays centered above the interface. Setup and Review/Delivery reuse the 75% workspace /25% current-session sidebar; fullscreen Capture hides configuration/header/sidebar.

## Guest operation

1. Setup defaults to six photos, portrait grid and a five-second countdown. Guests may choose existing frames, four/six-photo layout and timer, or press BẮT ĐẦU CHỤP NGAY immediately.
2. Start checks camera readiness before countdown/fullscreen. A host connection/capability/preview failure remains on Setup with the actual error, takes no photo and does not switch to a fake camera. Explicit Mock/browser simulation remains labeled DEMO; physical camera behavior is unchanged.
3. The existing capture loop waits for each accepted photo/file save, updates progress and automatically opens Review & Customize after the last selected shot.
4. The current-session sidebar provides individual retakes. A retake enters fullscreen countdown and returns automatically to Review. Existing filters, stickers, text, frame color, frame adjustment settings and composite renderer are reused.
5. Review does not create a composite on the backend or finalize a share. Only the explicit confirmation button saves the chosen composite. After the existing durable-complete ACK, the UI automatically presents QR/download/printing; QR generation and failure retry use the existing logic.
6. Phiên mới clears guest photos, stickers, custom text, filter/tab, saved image/share state and returns to Setup. Busy/unresolved saves retain the existing recovery safeguards; unfinished photos require discard confirmation.

No image is auto-finalized, no job is automatically printed and no token is created during review. One session still produces one official final and one stable QR. Delivery errors show the existing save/QR/printer status and retry actions.

## Implementation

The existing home/capture/result sections remain internal screens. Added guestWorkflowActive and guestStarting state; no stepper is rendered or queried. Removed only stepNavHome, stepNavCapture and stepNavResult IDs. All 80 legacy methods and other legacy IDs remain; original HTML/legacy copies are unchanged.

Old controller helpers remain callable for module/API regression fixtures. The visible Start button always enables the continuous guest flow, independently of the legacy fullAutoMode switch. Existing manual fixture tests use internal prepareSession/goToScreen rather than presenting manual navigation to guests.

Existing DOM nodes are moved rather than duplicated: the current-session sidebar follows Review/Delivery; confirm/print/download/QR/editor controls use their original services and handlers. Delivery/editor groups are switched by confirmed session state. Frame adjustment opens the existing settings modal; no Frame Editor rewrite.

No backend, database, camera SDK, photo storage, QR generation, printer adapter, Host or Event Live Gallery implementation was changed. Camera hardware and venue-network limitations from the Phase 6 report remain.

## Validation

| Check | Result | Evidence |
|---|---|---|
| npm.cmd test | 9 passed | Final command output; 80-method mapping/legacy bytes and explicit 3-ID removal |
| npm.cmd run build | PASS, 48 modules | Final demo build |
| npm.cmd run build:production -- --outDir dist-production | PASS, 48 modules | Production capture guard retained |
| npm.cmd run build:host | PASS, 48 modules | Built same-origin kiosk |
| playwright.isolated.config.js | 22 passed (5.7m) | .tools/guest-workflow-regression.txt |
| playwright.deployment.config.js | 1 passed (1.3m) | .tools/guest-workflow-production.txt |
| playwright.qr-confirm.config.js | 3 passed (38.7s) | .tools/guest-workflow-qr.txt |
| git diff --check | PASS | Final whitespace check |

Total: **26 browser scenarios**. The production-style test presses Start for 6 and 4 shots with legacy fullAutoMode=false, checks fullscreen and automatic Review, verifies no backend composite/finalization before consent, retakes from the sidebar, uses filters/stickers/frame settings, confirms once, checks automatic QR/delivery, two-copy Mock printing, clean New Session, actual backend restart and backup hashes. A new regression proves an unavailable host camera takes zero shots and recovery automatically reaches four-photo Review without finalizing.

During implementation, browser checks caught an invalid editor DOM ancestor, a stale fullscreen class in old manual test setup, and an editor tab persisting into the next guest; these were corrected. Visual review caught QR content overflowing into the sidebar, now stacked within its column and verified without horizontal overflow. One regression run saw a transient Vite proxy connect timeout; the final complete serial run passed all 22. No automatic test retries or skipped assertions were used to claim success.

All automated camera/printer calls use explicit Mock/demo fixtures and isolated storage. Physical camera, printer and iPad/Safari remain unverified. Backend unit tests were not rerun for this frontend-only change; the existing real FastAPI/SQLite/camera/QR/print APIs and process restart were exercised by browser integration. No backend, database migration or runtime dependency was changed.

Evidence logs are in .tools/guest-workflow-*. Screenshots: guest-automatic-review.png and guest-automatic-delivery.png in docs/screenshots, plus the updated setup/portrait/sidebar captures.

## Relevant files

- frontend/index.html — remove the stepper and its implicit Home navigation.
- frontend/src/core/store.js, router.js — guest states and internal routing without navigation pills.
- frontend/src/features/home/home.js, kiosk.js — setup/readiness status, shared 75/25 layout and review/delivery groups.
- frontend/src/features/capture/capture.js, countdown.js, retake.js — preflight, automatic review, retake return and clean New Session.
- frontend/src/features/result/result.js and services/photo-repository.js — remove stepper updates; retain confirmation/storage/share behavior.
- frontend/src/styles/kiosk.css — presentation/visibility rules.
- frontend/tests/baseline.test.js, tests/e2e/photobooth.spec.js, tests/deployment/production.spec.js and playwright.deployment.config.js — updated intentional DOM contract, bounded readiness assertions, automatic 4/6 workflow and camera-error coverage.

No commit or push was performed.
