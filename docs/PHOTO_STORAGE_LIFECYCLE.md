# Event Live Gallery — schema 8 metadata addition

Current schema is **8**. Migration 008 adds only restricted display approval/access metadata. Existing photos are not approved automatically and no image file is changed/deleted by this migration. Official final/QR/temporary-file lifecycle below remains unchanged. Event display reads only the saved official composite after explicit Host consent/authorization approval; hide removes display permission only. [Display guide](EVENT_LIVE_GALLERY.md).

# Phase 6 storage migration clarification (schema 7 history)

Current schema is **7**. Migration 007 runs after 006 and **retains all pre-existing pending/blocked cleanup as retained_legacy**, so upgrading does not delete completed users' original photo files. The historical statement below that migration 006 schedules cleanup must be read with this overriding preservation rule. Existing published QR URLs/files remain compatible. New confirmations after upgrade alone enqueue automatic cleanup under the existing durable-final/hash/ownership guards.

One session still has one official final composite and one stable QR; print-ready is a derivative, not a separate gallery product. Backend working files for incomplete sessions are retained for recovery/manual retention decisions. Offline backup includes DB/photos/QR/print-ready/.share-key with hash manifest. [Runbook](WINDOWS_EVENT_GUIDE.md), [event checklist](EVENT_DAY_CHECKLIST.md).

---

# Photo storage lifecycle — current requirement (schema 6)

One session has **one official completed composite**. Its QR PNG and optional print-ready PNG are derivatives of that same session photo, not additional guest photos. Guest Photo Page and Host Dashboard show only the official composite/print-ready version. The following supersedes historical Phase 2–5 descriptions allowing edits/new shares after confirmation or retaining all original captures indefinitely.

## Capture / edit / retake

Native camera JPGs in `camera_originals/<session>/`, normalized editor PNGs in `originals/<session>/`, and optional UVC `camera_spool/<capture>.jpg` files are temporary working assets. They remain private to the owning capture session. Draft composite revisions are private working files too. Retake/filter/frame/text/sticker editing remain available before confirmation. Host gallery does not preview unconfirmed drafts or individual captures; it can list the session as still in progress.

No physical-camera requirement changes: host adapter must retrieve the camera's original JPG/file through a supported capture API. Browser canvas/live-view screenshots are not substitutes for a real camera capture. Mock/UVC remain explicitly labelled DEMO; vendor SDK hardware remains unverified.

## Confirmation boundary

Upload composite → complete/confirm checks that the composite is current, all source slots exist, no active/uncertain capture is pending, final file exists and its SHA256 matches. One SQLite transaction marks the session completed, inserts `session_finals` (session primary key), and journals temporary deletion candidates. **No working file is deleted before that commit.**

After confirmation, photo upload/delete/retake/new composite/camera connection or new shutter requests are rejected (409). Repeat complete/finalize reuses the official composite and stable share; a new image requires a new guest/session. A SQLite trigger also prevents inserting another new share for the same session. The kiosk locks customization/navigation to capture, preserves the chosen composite, and releases individual photo canvases/thumbnails only after the successful confirmation ACK. Lost/failed ACK keeps local working data for retry of the same request; ambiguous confirmation does not allow editing a different snapshot.

QR or print-ready generation may follow confirmation. Missing PUBLIC_BASE_URL or QR failure does not reopen the final, delete the final, or manufacture a new token. QR retry works from the retained composite even after originals were cleaned. Guest download continues to return the print-ready version matching the printer when available.

## Safe cleanup / recovery

`TemporaryAssets` removes all temporary photo revisions, received native JPGs and known per-capture spool files, plus unshared draft composites. It preserves the official composite, every published legacy composite, QR assets, print-ready files, print receipts, DB metadata and operation ACKs. Photo/capture rows may remain as private audit/idempotency metadata; they are not publicly accessible photo assets.

Cleanup runs after a successful confirmation commit and through a durable background retry worker (including startup recovery without blocking backend startup). Pending jobs take priority over previously blocked jobs. Every pending path is allowlisted, owned by the session, resolved within storage, and rejected if it aliases a symlink/junction or protected final. It never recursively deletes a directory or scans unrelated sessions. The official composite and hash are checked again before deleting each file. Missing files are idempotent; interrupted deletion is replayable after restart.

If upload, confirmation commit, transfer or final integrity validation fails, working files remain for recovery and retake. After a confirmation error, the kiosk checks backend state: an explicitly unsealed session can be edited/retaken again, while an unknown/already committed outcome stays locked to the same request until its ACK is recovered. If deletion fails, the final/QR remain usable; cleanup_status becomes blocked, pending deletion records remain, and the worker retries. If the final is missing/corrupt before cleanup, remaining working files are kept until the final is restored. There is no automatic cleanup of an unconfirmed/failed session merely because it is old.

## Files / migration

Added `backend/app/migrations/006_storage_lifecycle.sql`, `backend/app/services/temporary_assets.py`, `backend/tests/test_storage_lifecycle.py` and this document. Updated repository/confirmation, camera final-state guards, Host gallery/media/counts, startup worker lifecycle, frontend confirmation/editor/navigation/QR retry and working-canvas release, backend/E2E expectations, README/API/security/Phase 5 report/migration/acceptance docs. Original HTML and legacy remain unchanged; no commit/push.

Endpoints: owning-session normalized photos and native original downloads return 410 after confirmation, even if a file could not yet be deleted. Host individual-photo routes return 404; Host composite/print-ready routes only serve the official final. The guest token always grants only its corresponding final photo. Host status counts official photos rather than 4/6 individual working captures.

## Existing data

Migration 006 seals already-completed sessions and schedules safe cleanup. Historical sessions that had already published a final and then returned to editing are pinned to the last published final but marked retained_legacy: their ambiguous working drafts are kept for manual review. Previously issued legacy share URLs are preserved rather than silently invalidated; no new additional share may be created. New sessions follow the one-final/one-token lifecycle strictly. Existing old published derivatives are not treated as temporary files.

## Verification

Final localhost QR smoke: **3/3 PASS**, including automatic QR generation, retry without originals and download checksum verification. `git diff --check` PASS; original HTML/legacy unchanged.

Backend **79/79 PASS**, Node **9/9 PASS**, full browser suite **21/21 PASS**, demo/production/host builds **PASS**. Backend tests cover 4/6 layouts, pre-confirmation retake, final-only Host gallery, one final/share, rejected post-confirmation mutations, cleanup of all original revisions, failed upload/DB commit, locked deletion retry, restart/final hash recovery, path traversal/other-session protection and camera original cleanup. E2E verifies retake before confirmation, released working canvases/files after confirmation, locked editing and stable QR with repeated confirmation, plus recovery after a known failed final commit. A previously timing-dependent delete test was fixed to wait for its backend ACK. No actual camera hardware was tested and no SDK behavior was replaced with preview capture.

Re-run: backend `.venv/Scripts/python.exe -m pytest -q --tb=short`; frontend `npm.cmd test`, `npm.cmd run build`, `npm.cmd run build:production -- --outDir dist-production`, `npm.cmd run build:host`, then Playwright with `--config playwright.isolated.config.js` and (sequentially) `--config playwright.qr-confirm.config.js`. Set CHROME_PATH if using installed Chrome. No commit/push or Phase 6.
