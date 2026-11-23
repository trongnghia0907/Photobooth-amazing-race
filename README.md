# AMAZING RACE 2026 Photobooth

The Windows laptop runs Booth, controls the Sony over USB, saves the final composite and handles printing. Google Drive can back up finalized PNGs privately.

| Mode | Where photos are served |
| --- | --- |
| **Local Mode** | The laptop Host serves Booth, Gallery and Event Display. An optional photo-only HTTPS gateway lets phones scan QR links while the Host is online. Vercel credentials are optional. |
| **Vercel Cloud Publishing** | The laptop also queues new approved composites for publication. Vercel serves its own public Gallery, Event Display and QR photo pages from a shared cloud catalog. Camera, Confirm, Drive backup and printing stay on the laptop. |

## 1. Build & Installation

### Install once

Use **Windows 11 and PowerShell** for the primary hardware test. Windows 11 is not enforced, but Windows 10 requires separate validation. The current Sony USB transport requires Windows WIA; it does not run on macOS/Linux. For other project components, see [macOS setup](docs/MACOS_SETUP.md).

Install Git, **Python 3.12** and **Node.js 22.12 or newer with npm**. Camera hardware, a printer and Internet access are optional for Mock testing.

1. Clone and open the project:

   ```powershell
   git clone https://github.com/trongnghia0907/Photobooth-amazing-race.git
   Set-Location Photobooth-amazing-race
   ```

   Run the following commands from this root folder, which contains `backend`, `frontend` and `scripts`.

2. Create the Python environment and install backend dependencies:

   ```powershell
   py -3.12 -m venv backend/.venv
   & ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.lock.txt
   & ./backend/.venv/Scripts/python.exe -m pip check
   ```

   Activation is unnecessary: the commands use the virtual environment directly.

3. Install frontend dependencies, then build the Host UI:

   ```powershell
   Push-Location frontend
   npm.cmd ci
   npm.cmd run build:host
   Pop-Location
   Test-Path frontend/dist-host/index.html
   ```

   The final command should print `True`. Installation downloads dependencies; building creates the frontend served by the Host. Repeat installation when lockfiles change and rebuild after frontend changes.

4. Prepare storage and enable the All-Photos Gallery in this terminal:

   ```powershell
   New-Item -ItemType Directory -Path runtime -Force | Out-Null
   $env:PUBLIC_GALLERY_ENABLED="true"
   ```

   The Host creates SQLite, photo folders and logs automatically inside `runtime`. Keep this directory private and backed up; do not delete it to fix startup errors. Each laptop needs its own installation and authorization.

5. Check that the launcher is available:

   ```powershell
   & ./backend/.venv/Scripts/python.exe scripts/run_host.py --help
   ```

No `.env` file is required for the basic setup. The launcher asks for a Host username and a password of at least **12 characters**. There are no default credentials. Save and reuse your chosen credentials; do not put secrets in Git or command arguments.

Environment variables apply to the current PowerShell terminal. Configuration files are loaded only when explicitly passed with `--env-file`; existing environment variables override file values. Do not copy the production settings in `backend/.env.example` unchanged into a local/LAN setup. Google Drive and Cloudflare setup is optional and described in section 3.

## 2. Camera Connection

### Current camera support

- **Mock (`mock`):** working synthetic preview and saved test images. No physical shutter or camera JPEG.
- **Webcam (`uvc_demo`):** optional OpenCV video-frame capture in development mode. It is DEMO, not a replacement for original photographs from a mirrorless camera.
- **Sony ZV-E10 (`sony_zve10`):** Real Live View, shutter and original JPEG transfer have been observed with the first-generation ZV-E10. The Host has recorded completed Sony sessions for both 4- and 6-photo layouts. Six retained 6000 × 4000 originals matched their recorded SHA-256 and decoded successfully. The adapter still reports `hardware_verified=false`. Recheck consecutive captures on the event hardware.

The current code includes Windows device discovery/transport (`sony_wia.py`), Sony PTP commands (`sony_ptp.py`), adapter validation (`sony_zve10.py`) and a diagnostic script. Live View, remote shutter and original JPEG transfer have implementation paths. Protocol/adapter tests use simulated transport; they do **not** prove physical compatibility or stability. A failed Sony connection never silently switches to DEMO capture.

The transport uses Windows' built-in WIA/PTP interfaces through Python's standard library; the code does not require an additional Sony pip package or SDK installer. Check camera detection in Device Manager. Do not replace USB drivers blindly.

### Prepare the original Sony ZV-E10

The primary setup connects **Sony ZV-E10 → USB data cable → Windows laptop running Booth**. An optional LAN client uses the laptop Host's camera.

1. Use the first-generation **ZV-E10**, a charged/powered camera and a USB data cable. A charge-only cable is insufficient.
2. On the camera, set **Network > Smartphone Connect > Smartphone Connection > Off**.
3. Set **Network > PC Remote Function > PC Remote > On** and **PC Remote Cnct Method > USB**.
4. Set **File Format > JPEG**, **Drive Mode > Single Shooting**, and **PC Save Image Size > Original**. Use **Still Img. Save Dest. > PC Only** for isolated acceptance or recovery, keeping the old SD card out after recovery. The adapter also accepts **PC+Camera** with a writable card. Use PC Remote mode.
5. Connect the camera directly to the Windows laptop. If needed, independently check it with Sony's official [Imaging Edge Desktop](https://support.d-imaging.sony.co.jp/app/imagingedge/en/), then fully close Remote and other camera applications before Photobooth diagnostics. Only one application may own the camera.

These settings follow the [Sony ZV-E10 PC Remote guide](https://helpguide.sony.net/ilc/2070/v1/en/contents/TP0002392805.html). Imaging Edge working is a useful independent check, not proof that this project's driver works on the same hardware.

### Run Sony diagnostics before starting Host

**Stop Host and close other camera software first.** Run these commands from the repository root, in order:

1. Discover Windows camera devices without opening the camera:

   ```powershell
   & ./backend/.venv/Scripts/python.exe scripts/diagnose_sony_camera.py
   ```

   Inspect `pnp.devices` and `original_zv_e10_name_match`. A matching device name does not verify USB/PTP communication. Discovery alone leaves protocol checks `NOT_TESTED` and exits with code **2**, even when a device is listed.

2. Open USB/PTP, identify the model and retrieve a Live View frame without firing the shutter:

   ```powershell
   & ./backend/.venv/Scripts/python.exe scripts/diagnose_sony_camera.py --connect-preview
   ```

   Expect `usb_ptp_session` and `live_view` to report `PASS`. Shutter/JPEG checks remain `NOT_TESTED`.

3. **This command triggers one real shutter operation** and saves the original JPEG:

   ```powershell
   & ./backend/.venv/Scripts/python.exe scripts/diagnose_sony_camera.py --capture --confirm-shutter --output-dir ./sony-test-output
   ```

   Expect all four `protocol_checks` to report `PASS`, plus `jpeg_bytes`, `jpeg_dimensions`, `jpeg_sha256` and `saved_test_image`. Open that saved file and inspect the photograph. The script only marks shutter success after receiving the JPEG.

Diagnostics print JSON to the terminal; they do not automatically create a diagnostic log file. Capture outputs and recovery receipts are under `sony-test-output/camera_originals/sony-recovery/`; `saved_test_image` gives the exact JPEG path. Keep this directory private. Optional `--timeout` accepts **1–60 seconds** (default 15). Preview/capture checks exit **0** on PASS or **2** on FAIL.

A diagnostic PASS covers the requested checks. Event mode still requires the adapter's separate `hardware_verified` flag. Check complete 4- and 6-photo sessions on the event setup.

### Select the Sony adapter

After diagnostics finish, start the Sony Host command in section 3A. Sign in at `/admin` and inspect Camera Settings. Open `/booth` on the laptop and verify fresh Live View frames. Use **development** for Sony acceptance while the adapter reports `hardware_verified=false`.

For software-only testing, replace `--camera sony_zve10` with `--camera mock`. For an optional webcam test, install the following, then use `--camera uvc_demo`:

```powershell
& ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-camera-optional.txt
```

### Camera troubleshooting

- **Not detected or Windows Code 10/43:** check power, a USB data cable, another direct USB port and Device Manager. Resolve active device errors before retrying the Host. `pnp.status=UNAVAILABLE` means Windows could not complete the query.
- **Busy/access/WIA error:** stop Host before using the diagnostic script; close Imaging Edge and other camera apps. Recheck PC Remote/USB settings.
- **USB/PTP/protocol or unsupported-model error:** confirm original ZV-E10, PC Remote settings and the reported error code. A failure after detection may be a transport/protocol compatibility issue, not a broken camera.
- **Live View timeout:** inspect USB/PTP connection and camera state first; a preview timeout alone does not prove disconnection. Reproduce with `--connect-preview` on the laptop before investigating Wi-Fi.
- **No shutter/JPEG or uncertain result:** inspect the diagnostic stage, memory card and save/transfer settings. Do not repeatedly fire the shutter after an uncertain result; preserve recovery files and retry the existing pending transfer through the app.
- **Disconnected during capture:** reconnect and inspect/recover the pending operation before taking another photo. Keep captured photos and storage intact.

Host logs are under `runtime/logs/`. Report the diagnostic JSON, camera model/settings and failing stage, without credentials or private images. Successful mock tests cannot distinguish every hardware problem from a driver compatibility issue; physical testing is required.

**Abandoning a failed Sony shot (Host operator only).** After returning to **New Session**, stop the Host before recording an abandonment. Use the full capture ID from the Host logs:

```powershell
& ./backend/.venv/Scripts/python.exe scripts/cancel_sony_capture.py --capture-id <capture-uuid> --confirm-discard
```

The command locks the Host runtime and opens the camera exclusively. It checks for active captures, JPEG evidence, acknowledged releases and an empty buffer. `abandonment_pending` preserves the operator decision and the original receipt while keeping new shutters blocked. A failed request with no shutter intent can clear its pending Booth state without this command.

To finish abandonment while the Host is stopped, close other camera apps and wait until the camera's access lamp is off. Turn off the camera, unplug USB and any external power, remove the battery, and remove the old SD card if one was installed. Keep that card separate during the new session. With the camera still disconnected and unpowered, record the boundary for the same full capture ID:

```powershell
& ./backend/.venv/Scripts/python.exe scripts/cancel_sony_capture.py --capture-id <capture-uuid> --confirm-discard --record-power-off
```

Reinstall the battery, leave the old SD card out, and turn on the same camera. Set **PC Remote → Still Img. Save Dest. → PC Only**, reconnect USB, and run the following without taking a photo or starting the Host:

```powershell
& ./backend/.venv/Scripts/python.exe scripts/cancel_sony_capture.py --capture-id <capture-uuid> --confirm-discard --verify-reconnect
```

After `abandonment_isolated`, start the Host, select **New Session**, and connect the camera. On that first camera connection, the Host records the cancellation in SQLite and keeps the physical outcome uncertain. If Windows PnP, the fresh Sony PTP connection, or the empty-buffer check fails, leave the receipt and any unclaimed JPEG untouched. A WIA reconnect with an empty buffer by itself leaves the guard in place.

**Preserving an unmatched Sony JPEG.** If the Host reports a buffered JPEG with an unknown capture identity and gives the retired receipt ID, let active work finish and gracefully stop the Host. Run the following only as the Host operator with that full receipt ID:

```powershell
& ./backend/.venv/Scripts/python.exe scripts/cancel_sony_capture.py --capture-id <capture-uuid> --preserve-buffer
```

`preserved` confirms the original JPEG, its checksum and the post-transfer `FILE_INFO=0x0000`. The image and its audit record are under `runtime/camera_originals/sony-recovery/unassigned/`. Preserve them separately from Booth slots. Start the Host and select **New Session**. For an interrupted or invalid transfer, keep the audit and any preserved bytes. The guard stays active and re-running the command does not repeat the uncertain read.

## 3. Running the Complete Photobooth System

1. **Capture and review.** In laptop Booth, choose 2×2 (4 photos) or 2×3 (6 photos). During countdown, the counters sit beside Live View. Review the captured slots in order.
2. **Confirm.** Select **Confirm & Display**. The Host finalizes the session in SQLite and saves the framed PNG at `runtime/composites/<session-id>/<composite-id>.png`. Temporary originals can be cleaned up after finalization.
3. **Back up and display.** Drive backup queues independently when enabled. Publication follows the Host's auto-publish setting and consent recorded at confirmation, or operator approval in Dashboard. Event Display shows approved composites with available local files. Gallery lists eligible approved finals independently of personal QR expiry.
4. **Share and print.** The personal QR opens a preview and download of the clean finalized PNG. Local printing uses a separate print-ready image with a QR footer. Drive sync does not gate Confirm, Event Display or a verified QR backed by a local file.

### A. Terminal 1: start the Host

Connect the laptop to the intended Wi-Fi/hotspot, then run from the repository root:

```powershell
$env:PUBLIC_GALLERY_ENABLED="true"
& ./backend/.venv/Scripts/python.exe scripts/run_host.py --profile lan --lan-ip auto --mode development --camera sony_zve10
```

Enter your Host credentials. If the launcher cannot identify the private subnet, it asks for a kiosk pairing code (at least 16 characters). **Keep this terminal open.** This starts one Host on port **8000**, listening on `0.0.0.0` for localhost and LAN access. The built frontend and backend run together; a separate Vite server is unnecessary.

Finish and close standalone diagnostics before starting this Host. For a test without Sony hardware, use `--camera mock`. For laptop-only testing, replace `--profile lan --lan-ip auto` with `--profile local`. Add `--build` when the frontend needs rebuilding.

Open `http://localhost:8000/api/health` on the laptop and check for `"status":"ok"`. If startup fails, read the actual exception printed by the launcher. Do not kill unrelated processes or delete runtime/lock files.

### B. Open the five websites

`LAPTOP_IP` below means the current Wi-Fi IPv4 printed by the launcher. `{token}` is a route placeholder: open the real generated QR/share link instead of typing it.

| Website | Purpose | URL / route | Requirements |
| --- | --- | --- | --- |
| Booth | Capture and customize on laptop | `http://localhost:8000/booth` | A LAN client can use the printed Booth URL and pair if required |
| Host Dashboard | Manage equipment and sessions | `http://localhost:8000/admin` | Host login; laptop localhost only |
| Event Live Display | Four-corner projector presentation | `http://LAPTOP_IP:8000/event-display` | Same LAN, no code by default |
| All-Photos Gallery | Browse published final composites | `http://LAPTOP_IP:8000/gallery`; public HTTPS origin + `/gallery` when enabled | `PUBLIC_GALLERY_ENABLED=true`; approved, non-hidden, non-revoked final |
| QR Guest Photo Page | View/download one confirmed photo | `/p/{token}` on the generated share origin | Valid share token; verified public HTTPS for phones on other networks |

Localhost refers to the device opening the page. Use the laptop's LAN address on the iPad, never the iPad's localhost. Cloudflare forwards selected requests to the laptop; it is not a cloud-server deployment.

### C. Optional LAN access

Put the Host and the viewing device on the same trusted Wi-Fi or hotspot. Use the Wi-Fi IPv4 address printed by the launcher. To check the address:

   ```powershell
   Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } | Select-Object InterfaceAlias,IPAddress
   ```

If automatic detection chooses a VPN or another interface, restart Host with `--lan-ip LAPTOP_IP` using the current Wi-Fi address. Reopen the URL if DHCP changes it.

For a separate Live View test over Wi-Fi, open `/booth?previewStats=1` on a second device and keep only one Booth viewer active. Move an object in view and note frame age, FPS and any freezes. Remove the query parameter for normal use.

On a trusted hotspot, use a Windows **Private** network profile. If needed, an administrator can add a Private-network-only rule; replace `Wi-Fi` with the actual interface alias:

```powershell
New-NetFirewallRule -DisplayName "Amazing Race Hotspot 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private -InterfaceAlias "Wi-Fi" -RemoteAddress LocalSubnet
```

Do not disable the firewall. Some hotspots isolate connected devices; if the correct IP and firewall rule still fail, use a network that allows device-to-device connections.

### D. Open Event Live Display

On a computer **on the same LAN**, open the printed `/event-display` URL. A display code is only required if the Host starts with `EVENT_DISPLAY_PIN_REQUIRED=true`. Connect its projector/LED by HDMI/USB-C and press F11 for presentation. Newly published final composites appear automatically; Host can hide them.

The local Event Display feed skips missing historical files and returns an empty list when no approved local files are available. Use the same LAN or connect the projector directly to the Host. A remotely hosted Event Display is part of the optional Vercel app in [section 4](#4-vercel-cloud-publishing).

### E. Optional Google Drive upload

Drive backup is optional in Local Mode. Each Windows installation needs its own Google authorization.

1. Install the optional dependencies:

   ```powershell
   & ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-drive-optional.txt
   ```

2. Enable Drive and Picker APIs in your Google Cloud project, configure a Desktop OAuth client and authorize a test user if required. Store the client JSON privately at `.tools/google-drive/client_secret.json`. Use the approved Restricted folder and account permissions described in [Drive setup](docs/PRIVATE_GOOGLE_DRIVE.md).
3. Grant that exact folder through the existing Picker and run the privacy check:

   ```powershell
   & ./backend/.venv/Scripts/python.exe -X utf8 scripts/connect_google_drive.py --storage-root runtime --client-file .tools/google-drive/client_secret.json --pick-folder
   & ./backend/.venv/Scripts/python.exe -X utf8 scripts/connect_google_drive.py --storage-root runtime --check --audit
   ```

4. After authorization/privacy pass, set `$env:GOOGLE_DRIVE_ENABLED="true"` in **Terminal 1 before starting/restarting Host**. Confirm startup says `Google Drive: enabled (background upload)`.

Final composites upload privately in the background. Failed uploads remain queued locally. Keep pending files and the folder's Restricted permissions.

### F. Terminal 2: optional public HTTPS QR and Gallery

Keep Host running first. Internet and `cloudflared` are required. The script checks the executable and can install the official `Cloudflare.cloudflared` winget package on Windows if missing. In another PowerShell at the repository root:

```powershell
$env:PUBLIC_GALLERY_ENABLED="true"
& ./backend/.venv/Scripts/python.exe scripts/mobile_qr_demo.py start --attach-host --host-port 8000 --public-port 8011 --storage-root runtime
```

If Drive is configured and required for the test, append `--require-drive` to this command. It attaches to the existing Host and starts/reuses an isolated photo gateway on **8011** plus a temporary Quick Tunnel. Do not start a standalone demo or another Host.

Wait for the **actual HTTPS URL** and successful isolation checks. Open that origin plus `/gallery` for public browsing. Confirm a new composite and wait for the Result UI to display a verified HTTPS QR before scanning it over 4G/5G. Test both the correct image and Download.

The gateway can serve the checksum-verified local PNG. QR readiness requires a reachable HTTPS origin that can verify the specific photo.

If the tunnel disconnects, public sharing becomes unavailable; the saved composite and upload queue remain intact. Reconnect the tunnel and use **Retry sharing** if automatic retries have stopped. For `getaddrinfo failed (11001)`, check DNS/network connectivity; try another network or configure a working DNS resolver. Do not bypass isolation checks or advertise a localhost/LAN QR as public.

The public gateway serves Guest Photo resources and the enabled Gallery. Local personal QR links expire 24 hours after first successful public verification, while Gallery eligibility follows publication approval and revocation. Restarting the tunnel does not extend a personal QR's lifetime.

Keep the laptop, Internet and tunnel running. Quick Tunnel domains are temporary; replacing a tunnel can invalidate old printed QR URLs. No permanent cloud server is deployed by these commands.

### G. Optional physical printing

Connect the physical printer, install its Windows driver and check it in **Settings → Printers & scanners**. For a real print test, append `--printer windows --enable-physical-printing` to the Host command.

In **/admin → Hàng đợi in**, select the physical printer and save a paper size and orientation offered by its driver. Open the completed session in **Kho ảnh**, use **Xem trước trên giấy**, then select the copy count and submit the print job. The QR print workflow uses the existing local public HTTPS share configuration. **Submitted** means the Windows spooler accepted the job. Check both layouts on the actual printer for margins, scale and QR readability.

### H. Basic end-to-end check

1. Verify fresh Live View, then complete a 4-photo session and a 6-photo session. Check that each JPEG reaches the right slot and Live View returns after capture. Stop if a shutter outcome is uncertain.
2. In a test session, check Pause, Resume, Capture Now, Complete and an individual retake. Inspect any originals needed for acceptance before Confirm.
3. Confirm an approved test composite. Check the local PNG, Gallery and Event Display. If configured, verify the Drive job reaches `SYNCED` and scan the active HTTPS QR from a phone to download the clean PNG.
4. If testing printing, check a copy from each layout on the event printer. Verify the printed QR and paper positioning.

### I. Stop safely

Stop Host with **Ctrl+C** in Terminal 1, or use:

```powershell
& ./backend/.venv/Scripts/python.exe scripts/stop_host.py
```

If you started mobile HTTPS testing, stop those owned services separately:

```powershell
& ./backend/.venv/Scripts/python.exe scripts/mobile_qr_demo.py stop
```

Restart with the same credentials and runtime. These stop commands preserve photos; do not delete storage or stop unrelated processes.

## 4. Vercel Cloud Publishing

The public-only project lives in [cloud/](cloud/). Set Vercel's Root Directory to `cloud`, use Node.js 22.x, and enable **Include source files outside of the Root Directory in the Build Step** for the shared UI and theme assets. The build uses `npm ci` and `npm run build`, with output in `public` as configured in [vercel.json](cloud/vercel.json). Use a dedicated **private Vercel Blob** store and **Neon Free** database, then apply [the catalog schema](cloud/schema.sql). Check Hobby eligibility and limits before provisioning. [Vercel project setup](https://vercel.com/docs/monorepos/monorepo-faq) · [Vercel terms](https://vercel.com/legal/terms)

| Where | Required environment variables |
| --- | --- |
| Vercel server | `DATABASE_URL`, `BLOB_READ_WRITE_TOKEN`, `PHOTO_CLOUD_PUBLISH_SECRET`, `PHOTO_CLOUD_QR_SECRET` |
| Windows Host | `PHOTO_CLOUD_ORIGIN` (stable Vercel HTTPS origin), `PHOTO_CLOUD_PUBLISH_SECRET` (same value as Vercel), `PHOTO_CLOUD_BLOB_TOKEN` (same private store) |

Keep credentials server-side and use separate publishing and QR secrets of at least 32 characters. On the laptop, run `npm.cmd --prefix cloud ci` before enabling the worker. Keep the local public share origin or gateway when using the existing local QR or print-ready workflow. The Host keeps running locally with the cloud variables unset.

To connect the local Sony Host to Vercel, put the Windows Host variables listed above in the Git-ignored `.env.cloud-local` file at the repository root. From that directory, run this PowerShell command in Terminal 1 in place of the Local Mode command in section 3A:

```powershell
& .\backend\.venv\Scripts\python.exe scripts/run_host.py --env-file .env.cloud-local --profile lan --lan-ip auto --mode development --camera sony_zve10
```

The worker publishes only new, confirmed and approved composites. It uploads the clean PNG and a thumbnail directly to Blob, verifies the bytes before registering the image, and retries from SQLite after restart. Historical photos are excluded. All three Vercel pages share the catalog. Booth can show a verified local QR while cloud publication is pending. [Detailed P2 setup, quotas and acceptance checks](docs/VERCEL_P2_DEPLOYMENT_READINESS.md)

## 5. Verification status

| Capability | Evidence and remaining checks |
| --- | --- |
| **Sony hardware** | Successful original JPEGs and completed 4- and 6-photo sessions are recorded. Recheck the event camera, cable and laptop against the local checklist. Event mode still enforces the separate `hardware_verified` flag. |
| **Local Booth and Event Display** | Mock-camera browser tests covered both layouts without cloud credentials. An isolated five-minute LAN run verified feed polling, empty state, recovery and automatic display of a newly approved photo. |
| **Drive and HTTPS QR** | The operational database records Drive jobs as `SYNCED`. P2 verified queue independence and clean downloads in controlled tests. Recheck live OAuth and scan the active HTTPS QR from a phone on the intended network. |
| **Local printing** | Software tests covered queue, paper size, orientation and preview. The event printer, paper alignment and printed QR still need physical verification. |
| **Vercel Cloud Publishing** | The public build passed locally. Upload retry and access rules passed with simulated services. Real deployment, private Blob, Neon and delivery of a PNG over 4.5 MB still need live verification. |
