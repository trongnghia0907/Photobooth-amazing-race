# AMAZING RACE 2026 PHOTOBOOTH
# FINAL EVENT READINESS, PRODUCTION CONFIGURATION & STABILITY AUDIT

You are working on the existing AMAZING RACE 2026 Photobooth project.

This task combines:
1. Event Deployment Readiness Audit.
2. Production/Event UI Cleanup.
3. Hardware and Network Configuration.
4. End-to-End Reliability and Stability Testing.
5. Event-Day Operational Preparation.

PRIMARY GOAL:

Make the existing Photobooth system ready to be configured and operated at a real event WITHOUT modifying source code on event day.

Do not rebuild the application from scratch.

Preserve all previously implemented functionality.

---

## PART 1 — AUDIT CURRENT IMPLEMENTATION

Before editing, inspect:

- Existing frontend and backend.
- All Phase 0–6 implementations.
- README and technical documentation.
- Environment configuration.
- CameraAdapter.
- PrinterAdapter.
- QR and Guest Photo Page.
- Host Dashboard.
- Event Live Gallery.
- Existing automated tests.
- Windows startup scripts.

Identify:
- Features already implemented.
- Missing production configurations.
- Remaining hardcoded development settings.
- Incomplete hardware integrations.
- UI elements unsuitable for event usage.
- Reliability and security issues.

Do not assume a feature works merely because code exists.

Make minimal targeted modifications.

---

## PART 2 — ENVIRONMENT CONFIGURATION

Implement a clear separation between:

1. DEVELOPMENT MODE
2. EVENT / PRODUCTION MODE

Use environment variables or configuration files.

Do not hardcode environment-specific values.

Configuration should support:

- Application environment.
- Camera adapter.
- Camera device/model selection.
- Printer adapter.
- Printer name.
- Number of print copies allowed.
- Database location.
- Photo storage directory.
- Public HTTPS base URL.
- Event Live Gallery configuration.
- Host Dashboard configuration.
- Logging configuration.
- Mock hardware permissions.
- Session timeout.
- Network settings.

Create an example event configuration file.

Never commit real credentials, tokens or passwords.

Use the existing variable names where possible.

Do not create conflicting configuration systems.

Ensure production behavior does not accidentally fall back to development mode.

---

## PART 3 — CLEAN EVENT USER INTERFACE

Audit all Guest UI text, including:

- DEMO
- MOCK
- DEBUG
- Backend information
- Technical camera details
- Camera adapter names
- Internal API information
- Development-only warnings
- Old branding

The official branding is:

AMAZING RACE 2026

No OSA branding should appear.

### Development Mode

Keep useful technical diagnostics.

Clearly identify Mock Camera, webcam video-frame capture and other simulated functionality.

### Event Mode

Display a clean, professional, touch-friendly interface.

The Guest UI should only show information necessary for the guest's experience.

For example:
- AMAZING RACE 2026
- Photobooth
- Chọn khung ảnh
- Chọn thời gian
- Bắt đầu chụp
- Camera sẵn sàng
- Xem lại
- Chụp lại
- Xác nhận ảnh
- Tải ảnh
- In ảnh
- Phiên mới

Remove verbose developer/debug descriptions.

IMPORTANT:

Do not simply hide DEMO labels while MockCamera is still active.

If Event Mode is configured to require a real camera, verify actual camera capabilities before enabling capture.

If the physical camera is unavailable, display a concise guest-facing error and useful diagnostics in Host Dashboard.

Allow a clearly marked rehearsal/demo mode only when explicitly enabled by the operator.

Apply equivalent behavior to printers.

Do not silently claim physical printing was completed when MockPrinter was used.

Keep detailed technical information in Host Dashboard.

---

## PART 4 — VERIFY FINAL iPAD UI

Preserve the agreed interface.

### Setup Mode

- AMAZING RACE 2026 centered at the top.
- Approximately 75% main Photobooth workspace.
- Approximately 25% right sidebar.
- Main workspace includes Live Preview, frame selection, timer, layout and Start Capture.
- Right sidebar displays recent finalized composite photos from previous guests, not individual source captures.
- Only display photos approved for event display.
- Newest approved composites appear first.
- Automatically update the sidebar.
- Do not reset the gallery when a new session starts.

### Capture Mode

When Start Capture is pressed:

- Enter fullscreen capture interface.
- Hide setup controls and sidebar.
- Show Live Preview.
- Show a large countdown.
- Automatically capture 4 or 6 photos.
- Display shot progress.
- Handle temporary camera errors.
- Transition automatically to Review Mode.

### Review Mode

- Allow retake.
- Apply supported filters, stickers and frames.
- Generate exactly one final composite per session.
- Require confirmation before finalization.
- Display QR only after successful finalization.
- Allow download and printing.
- Allow starting the next session.

Do not restore the old 1/2/3 step navigation.

Avoid major visual redesigns.

---

## PART 5 — CAMERA & PRINTER READINESS

### Camera

Verify the current CameraAdapter architecture.

The intended real camera workflow is:

iPad → Backend → CameraAdapter → Physical Camera → Original JPG → Backend Storage.

Live Preview must be distinguished from actual photo capture.

Real Camera Mode must not use a screenshot or video frame as a substitute for an original camera-generated image.

Verify:
- Connection detection.
- Camera capabilities.
- Live Preview.
- Shutter commands.
- Original photo transfer.
- Capture timeout.
- Disconnect/reconnect.
- Retake.
- Resource cleanup.

If the actual camera model is not available, use MockCamera for automated tests and clearly report real hardware testing as NOT TESTED.

Do not invent camera SDK support.

### Printer

Verify:
- Printer selection.
- Print-ready composite.
- QR positioning.
- Print queue.
- Copy count.
- Job persistence.
- Retry behavior.
- Duplicate print prevention.
- Failure recovery.

Use MockPrinter for automated tests.

Physical printing must require an explicitly configured printer.

Never automatically send uncontrolled test print jobs.

If a printer disconnects, preserve the photo and print job information.

Avoid automatically reprinting jobs when previous physical print status is uncertain.

---

## PART 6 — NETWORK & DEPLOYMENT

The Windows 11 laptop will act as the main Photobooth server.

Other devices:

- iPad: Guest UI.
- Camera: connected to the host laptop using a supported interface.
- Printer: connected to the host laptop.
- Projector/LED screen: Event Live Gallery.
- Customer phones: Guest Photo Page through QR.

Prepare the application to work in this architecture.

### Production Frontend

- Use a production frontend build.
- Do not rely on Vite development server for actual event operation.
- Ensure correct frontend/backend routing.
- Ensure the Guest Photo Page supports direct navigation and browser refresh.
- Prevent frontend requests from using incorrect localhost addresses.

### Local Network

Provide configuration for:
- Laptop LAN IP.
- iPad access.
- Projector access.
- Windows Firewall.
- Router/Wi-Fi connection.

Support a local event demo.

### Public HTTPS

Prepare secure Cloudflare Tunnel integration.

Requirements:
- Configurable public HTTPS origin.
- Stable share URLs.
- Guest Photo Page accessible from customer mobile networks.
- Correct QR generation.
- Photos remain stored on the laptop.
- No mixed-content requests.
- No public exposure of private database or storage directories.

Do not automatically create or activate public tunnels without authorization.

If a temporary tunnel URL is used, clearly explain that it can change.

For production, document the need for a stable hostname and persistent tunnel configuration.

### Security

Protect:
- Host Dashboard.
- Admin APIs.
- Camera control APIs.
- Print management.
- Private storage.
- Database.
- Credentials.

Keep Guest Photo Page restricted to its own share token.

Keep Event Live Gallery restricted to approved photos.

Do not expose internal diagnostics publicly.

---

## PART 7 — EVENT LIVE GALLERY

Verify the separate page used on the projector/LED screen.

Requirements:
- AMAZING RACE 2026 branding.
- 16:9 layout.
- Display finalized, approved composites only.
- Automatically detect newly completed eligible photos.
- Grid and/or slideshow presentation.
- No need to manually refresh.
- Recover after network interruption.
- Do not expose private Host Gallery.
- Host can hide an image from public display.

The iPad's right sidebar may reuse the same approved-photo feed.

Do not duplicate gallery data unnecessarily.

---

## PART 8 — STABILITY & FAILURE RECOVERY

This is a critical part of event readiness.

Audit behavior under:

1. Laptop application restart.
2. Backend restart.
3. Frontend reload.
4. Temporary Wi-Fi disconnection.
5. Temporary Internet disconnection.
6. Cloudflare Tunnel disconnection.
7. Camera disconnection.
8. Printer disconnection.
9. Duplicate button presses.
10. Interrupted image transfer.
11. Failed composite finalization.
12. Failed QR generation.
13. Failed print job.
14. Multiple consecutive guest sessions.
15. Insufficient disk space.

Required behavior:

- Never silently lose finalized photos.
- Preserve completed sessions in SQLite.
- Prevent accidental duplicate capture commands.
- Prevent accidental duplicate print jobs.
- Recover from temporary disconnections when safe.
- Display clear guest-facing errors.
- Provide detailed diagnostics to the operator.
- Avoid blocking the whole application because printing is temporarily unavailable.
- Never delete temporary captures before the composite is successfully finalized.
- Avoid generating unusable QR links when the public URL is unavailable.
- Do not claim online photo downloading is available during an Internet outage.

If a fault cannot be recovered automatically, provide a safe manual recovery procedure.

---

## PART 9 — PERFORMANCE & LONG-RUN TESTING

Run existing automated tests first.

Then implement realistic stability testing using MockCamera and MockPrinter.

Test at least:

- 4-photo sessions.
- 6-photo sessions.
- Retake.
- Composite generation.
- QR.
- Download.
- Printing.
- Host Dashboard.
- Event Live Gallery.
- New Session reset.

Run a sequential simulation of at least 30 complete guest sessions if practical.

Verify:
- Exactly one official composite per completed session.
- Unique stable share token per session.
- No accidental duplicate print jobs.
- Gallery updates correctly.
- No significant memory/resource growth across sessions.
- Temporary source files are cleaned up safely.
- The system remains responsive.
- Completed images survive application restart.

Measure actual results where possible.

Do not fabricate performance numbers.

Record failures and fix reproducible critical issues.

If full testing is blocked by environment limitations, report exactly what was not tested.

---

## PART 10 — CROSS-PLATFORM EVENT DEPLOYMENT

Prepare a straightforward way to configure, start, operate and safely stop the existing system across supported host platforms.

Target platforms:

- Windows 11: Primary development, validation and event deployment platform. Prioritize Windows 11 first.
- macOS: Supported alternative host platform, subject to validation of the selected camera SDK, printer and operating-system version.
- Linux: Optional, best-effort host platform. Report limitations explicitly.

Do not restrict the application to Windows 11. Windows-specific references elsewhere in this prompt describe the primary deployment example; they do not exclude macOS or best-effort Linux deployment.

### Shared Core and Configuration

Keep the frontend, FastAPI backend, SQLite metadata, QR generation, Guest Photo Page, Host Dashboard and Event Live Gallery platform-independent.

Reuse current architecture, adapters, scripts and configuration. Do not rewrite working application code unnecessarily.

Use cross-platform paths and filesystem operations, including path joining, directory creation, file replacement, locking, cleanup and subprocess handling. Resolve platform-specific executables and virtual-environment locations appropriately.

Use environment configuration for storage, database location, adapter selection, devices, printer names, public origin and executable overrides. Do not hardcode a developer's operating-system paths into core application logic. Keep operating-system details behind adapters or small platform helpers.

Changing the host laptop or operating system must require configuration and compatible dependencies, not rewriting core application logic. Preserve existing environment variable names and API compatibility where possible.

### Startup and Safe Shutdown

Prefer existing shared Python launchers. Add or update thin platform-appropriate wrappers only where useful:

- Windows 11: PowerShell startup and shutdown scripts.
- macOS: Shell startup and shutdown scripts.
- Linux: Reuse compatible shell/Python scripts where practical; document best-effort limitations.

The operator should be able to:

1. Configure environment variables or the existing configuration file.
2. Select a compatible camera adapter, device and printer.
3. Start the production frontend build and backend.
4. Check backend, storage and hardware readiness.
5. Open Guest UI on iPad.
6. Open Host Dashboard on the host laptop.
7. Open Event Live Gallery on the projector/LED display.
8. Verify the public HTTPS QR URL and photo download.
9. Stop services safely and restart using the same runtime and configuration.

Avoid duplicate servers, camera controllers and print workers. Preserve process ownership checks and runtime locking on each platform. Shutdown must release resources safely and preserve pending or uncertain print-job information without automatically duplicating physical output.

Make missing dependencies, invalid configuration, unsupported adapters and occupied ports easy to diagnose. Do not create Windows scheduled tasks, macOS launch agents or Linux services without explicit authorization.

### Platform-Specific Printing and Camera Support

Keep the PrinterAdapter interface shared:

- Windows: Support Windows Print Spooler using the existing adapter where available.
- macOS/Linux: Support CUPS when installed, accessible and compatible with the selected printer/driver. Detect its availability before enabling physical printing.

Keep printer discovery, queue submission and status handling behind the appropriate adapter. Require explicit printer configuration and physical-print authorization. Do not substitute MockPrinter silently or equate successful queue submission with a verified physical print.

Keep CameraAdapter implementations platform-specific when required by the vendor SDK. Verify the SDK's actual operating-system, CPU architecture and camera-model support. Preserve the real capture requirement: retrieve the original camera-generated JPG rather than taking a screenshot or video frame from Live Preview.

Detect unsupported hardware configurations before enabling the affected operation. Show a concise guest-facing error and detailed Host diagnostics identifying the missing SDK, driver, device or operating-system support. Do not invent compatibility or silently fall back to mock hardware.

### Setup and Event Operations Documentation

Provide separate Windows 11 and macOS setup instructions with exact commands for:

- Installing dependencies and any required camera SDK/printer driver.
- Creating the virtual environment and building the frontend.
- Configuring environment variables, storage and devices.
- Starting, checking and safely stopping the application.
- Connecting iPad and projector/LED devices over the event network.
- Configuring the applicable firewall and network permissions.
- Diagnosing camera, printer and public QR connectivity failures.

Provide Linux guidance only to the extent implemented and verified; label best-effort and untested steps clearly.

Document platform-appropriate sleep settings, power connection, storage capacity, log locations, network requirements, restart procedures, camera/printer recovery and consistent backup/restore procedures.

Document host migration using a consistent backup of SQLite, completed composites and required private configuration/secrets. Preserve the stable share-token behavior and public origin where applicable. Do not expose credentials or require source edits during migration.

### Validation and Support Claims

Record a platform validation matrix in EVENT_READINESS_REPORT.md, including:

- Operating-system version and CPU architecture.
- Startup, shutdown, restart and data persistence.
- Shared frontend/backend, QR, Guest Photo Page, Host Dashboard and Event Live Gallery tests.
- Camera adapter, camera model, Live Preview, physical shutter and original JPG transfer.
- Printer adapter, printer/driver, queue behavior and actual physical printing.
- Results marked TESTED, PARTIALLY TESTED, NOT TESTED or BLOCKED BY HARDWARE, with evidence and remaining limitations.

Do not claim a platform is fully supported until its startup, camera and printing workflows have been tested on that platform with the intended hardware. Windows tests do not establish macOS or Linux support. MockCamera and MockPrinter tests do not establish physical hardware readiness.

Preserve macOS compatibility while prioritizing Windows 11 delivery. Report untested hardware or platform combinations honestly rather than disabling otherwise portable core functionality.

---

## PART 11 — EVENT OPERATOR CHECKLIST

Create a practical EVENT_DAY_CHECKLIST.md.

Include:

### Before Opening

- Laptop and power.
- Router and Internet.
- iPad connection.
- Camera connection.
- Live Preview.
- Physical shutter test.
- Original photo transfer.
- Printer readiness.
- Physical test print.
- QR scan over 4G/5G.
- Guest Photo Page download.
- Host Dashboard access.
- Event Live Gallery.
- Storage capacity.
- Backup readiness.

### During the Event

- Monitor camera connection.
- Monitor print queue.
- Monitor storage capacity.
- Check public QR accessibility.
- Check Live Gallery updates.
- Restart services only through safe procedures.

### After the Event

- Stop accepting new sessions.
- Finish pending print jobs.
- Back up completed composite files.
- Back up SQLite consistently.
- Verify backup integrity.
- Shut down services safely.

---

## PART 12 — FINAL VERIFICATION & REPORT

Run:

- Backend unit/integration tests.
- Frontend production build.
- Playwright E2E tests.
- Security regression tests.
- Mock hardware tests.
- Consecutive-session stability tests.

Produce EVENT_READINESS_REPORT.md.

The report must contain:

1. Current deployment architecture.
2. Files changed.
3. Environment variables required.
4. Development vs Event Mode differences.
5. Camera readiness.
6. Printer readiness.
7. QR/network readiness.
8. iPad UI readiness.
9. Event Live Gallery readiness.
10. Security findings.
11. Stability test results.
12. Remaining issues.
13. Exact startup commands.
14. Manual hardware acceptance tests.
15. Final Go/No-Go assessment.

Use the following readiness levels:

- READY FOR LOCAL DEMO
- READY FOR LAN DEMO
- READY FOR HTTPS DEMO
- READY FOR PHYSICAL EVENT

Only mark READY FOR PHYSICAL EVENT if actual hardware and network requirements have been verified.

A successful MockCamera/MockPrinter test is NOT proof of physical event readiness.

---

## EXECUTION RULES

- Inspect first, then make changes.
- Prioritize reliability over appearance.
- Make minimal targeted modifications.
- Reuse current architecture and existing configuration.
- Do not rewrite the application from scratch.
- Do not break completed Phase 0–6 features.
- Do not restore OSA branding.
- Do not restore the old step navigation.
- Preserve one-final-composite-per-session behavior.
- Preserve private storage and event gallery consent rules.
- Do not delete existing completed photos.
- Do not modify Git history.
- Do not commit, push or merge.
- Do not publicly deploy without permission.
- Do not claim untested hardware is functional.
- Do not hide MockCamera/MockPrinter limitations.
- Continue automatically through normal software fixes.
- Stop and report genuinely hardware-dependent blockers.

FINAL GOAL:

The Photobooth should be configurable and operable at AMAZING RACE 2026 without requiring source-code edits on event day.

Provide a clear final report and STOP.