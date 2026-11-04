# AMAZING RACE 2026 Photobooth

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

No `.env` file is required for the basic setup. The launcher asks for a Host username, a password of at least **12 characters**, and a kiosk pairing code of at least **16 characters**. There are no default credentials. Save and reuse your chosen credentials; do not put secrets in Git or command arguments.

Environment variables apply to the current PowerShell terminal. Configuration files are loaded only when explicitly passed with `--env-file`; existing environment variables override file values. Do not copy the production settings in `backend/.env.example` unchanged into a local/LAN setup. Google Drive and Cloudflare setup is optional and described in section 3.

## 2. Camera Connection

### Current camera support

- **Mock (`mock`):** working synthetic preview and saved test images. No physical shutter or camera JPEG.
- **Webcam (`uvc_demo`):** optional OpenCV video-frame capture in development mode. It is DEMO, not a replacement for original photographs from a mirrorless camera.
- **Sony ZV-E10 (`sony_zve10`): implemented and automated-tested; physical Sony ZV-E10 validation pending.** This adapter targets the first-generation ZV-E10, not ZV-E10 II.

The current code includes Windows device discovery/transport (`sony_wia.py`), Sony PTP commands (`sony_ptp.py`), adapter validation (`sony_zve10.py`) and a diagnostic script. Live View, remote shutter and original JPEG transfer have implementation paths. Protocol/adapter tests use simulated transport; they do **not** prove physical compatibility or stability. A failed Sony connection never silently switches to DEMO capture.

The transport uses Windows' built-in WIA/PTP interfaces through Python's standard library; the code does not require an additional Sony pip package or SDK installer. Check camera detection in Device Manager. Do not replace USB drivers blindly.

### Prepare the original Sony ZV-E10

The intended connection is:

**Sony ZV-E10 -> USB data cable -> Windows Host -> Wi-Fi/phone hotspot -> iPad.**

The iPad does not connect to the camera by USB or use its own camera in Host mode.

1. Use the first-generation **ZV-E10**, a charged/powered camera and a USB data cable. A charge-only cable is insufficient.
2. On the camera, set **Network > Smartphone Connect > Smartphone Connection > Off**.
3. Set **Network > PC Remote Function > PC Remote > On** and **PC Remote Cnct Method > USB**.
4. For original-file testing, choose **Still Img. Save Dest. > PC+Camera**, insert a writable memory card, and select **PC Save Image Size > Original**. If shooting RAW & JPEG, choose **RAW+J PC Save Img > JPEG Only**.
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

A diagnostic PASS covers only the requested checks. It does not mark the adapter `hardware_verified` or unlock Event mode. Full 4/6-photo and stability testing remains pending.

### Select the Sony adapter

After diagnostics finish, start the Sony Host command in section 3A. On the laptop, open `/admin`, sign in and inspect Camera Settings. Open `/booth` and verify Live Preview, then repeat from the paired iPad. Use **development** for initial hardware validation: Event mode requires verified physical hardware, and the current Sony adapter still reports `hardware_verified=false`. Do not bypass that restriction.

For software-only testing, replace `--camera sony_zve10` with `--camera mock`. For an optional webcam test, install the following, then use `--camera uvc_demo`:

```powershell
& ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-camera-optional.txt
```

### Camera troubleshooting

- **Not detected:** check power, a USB data cable, another USB port and Device Manager. `pnp.status=UNAVAILABLE` means Windows could not complete the query; it does not prove the camera is absent.
- **Busy/access/WIA error:** stop Host before using the diagnostic script; close Imaging Edge and other camera apps. Recheck PC Remote/USB settings.
- **USB/PTP/protocol or unsupported-model error:** confirm original ZV-E10, PC Remote settings and the reported error code. A failure after detection may be a transport/protocol compatibility issue, not a broken camera.
- **Live View timeout:** inspect USB/PTP connection and camera state first; a preview timeout alone does not prove disconnection. Reproduce with `--connect-preview` on the laptop before investigating Wi-Fi.
- **No shutter/JPEG or uncertain result:** inspect the diagnostic stage, memory card and save/transfer settings. Do not repeatedly fire the shutter after an uncertain result; preserve recovery files and retry the existing pending transfer through the app.
- **Disconnected during capture:** reconnect and inspect/recover the pending operation before taking another photo. Keep captured photos and storage intact.

Host logs are under `runtime/logs/`. Report the diagnostic JSON, camera model/settings and failing stage, without credentials or private images. Successful mock tests cannot distinguish every hardware problem from a driver compatibility issue; physical testing is required.

## 3. Running the Complete Photobooth System

### A. Terminal 1: start the Host

Connect the laptop to the intended Wi-Fi/hotspot, then run from the repository root:

```powershell
$env:PUBLIC_GALLERY_ENABLED="true"
& ./backend/.venv/Scripts/python.exe scripts/run_host.py --profile lan --lan-ip auto --mode development --camera sony_zve10
```

Enter your Host credentials and pairing code. **Keep this terminal open.** This starts one Host on port **8000**, listening on `0.0.0.0` for localhost and LAN access. The built frontend and backend run together; a separate Vite server is unnecessary.

Finish and close standalone diagnostics before starting this Host. For a test without Sony hardware, use `--camera mock`. For laptop-only testing, replace `--profile lan --lan-ip auto` with `--profile local`. Add `--build` when the frontend needs rebuilding.

Open `http://localhost:8000/api/health` on the laptop and check for `"status":"ok"`. If startup fails, read the actual exception printed by the launcher. Do not kill unrelated processes or delete runtime/lock files.

### B. Open the five websites

`LAPTOP_IP` below means the current Wi-Fi IPv4 printed by the launcher. `{token}` is a route placeholder: open the real generated QR/share link instead of typing it.

| Website | Purpose | URL / route | Requirements |
| --- | --- | --- | --- |
| Guest UI | Capture and customize on iPad | `http://LAPTOP_IP:8000/booth`; laptop: `http://localhost:8000/booth` | Same LAN and kiosk pairing code |
| Host Dashboard | Manage equipment and sessions | `http://localhost:8000/admin` | Host login; laptop localhost only |
| Event Live Display | Four-corner projector presentation | `http://LAPTOP_IP:8000/event-display` | Same LAN and separate Host-issued display code |
| All-Photos Gallery | Browse published final composites | `http://LAPTOP_IP:8000/gallery`; public HTTPS origin + `/gallery` when enabled | Gallery flag; published, non-revoked photo with an unexpired issued QR |
| QR Guest Photo Page | View/download one confirmed photo | `/p/{token}` on the generated share origin | Valid share token; verified public HTTPS for phones on other networks |

Localhost refers to the device opening the page. Use the laptop's LAN address on the iPad, never the iPad's localhost. Cloudflare forwards selected requests to the laptop; it is not a cloud-server deployment.

### C. Connect the iPad over a phone hotspot

1. Enable the phone's 4G/5G Wi-Fi hotspot.
2. Connect both the Windows laptop and iPad to that hotspot.
3. Run the LAN Host command above. Find the current IPv4 if needed:

   ```powershell
   Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } | Select-Object InterfaceAlias,IPAddress
   ```

4. Use the active Wi-Fi address, not a VPN address. Open the printed `/booth` URL in Safari and enter the pairing code.
5. If automatic detection chooses another interface, stop Host and replace `--lan-ip auto` with `--lan-ip LAPTOP_IP`, using the actual current address. Reopen the URL after DHCP changes; no fixed IP is required.

On a trusted hotspot, use a Windows **Private** network profile. If needed, an administrator can add a Private-network-only rule; replace `Wi-Fi` with the actual interface alias:

```powershell
New-NetFirewallRule -DisplayName "Amazing Race Hotspot 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private -InterfaceAlias "Wi-Fi" -RemoteAddress LocalSubnet
```

Do not disable the firewall. Some hotspots isolate connected devices; if the correct IP and firewall rule still fail, use a network that allows device-to-device connections.

### D. Open Event Live Display

On the Host Dashboard, enable display access and create a display code. On a computer **on the same LAN**, open the printed `/event-display` URL and enter that code. Connect its projector/LED by HDMI/USB-C and press F11 for presentation. Newly published final composites appear automatically; Host can hide them.

**A computer on a different auditorium network cannot currently use Event Display through the photo-only Cloudflare gateway.** The public gateway does not serve `/event-display`. Use the same LAN or connect the projector directly to the Host. Cross-network Event Display needs a separately approved private connection or future deployment; it is not currently provided. Never expose Host port 8000 publicly to work around this restriction.

### E. Optional Google Drive upload

Skip this for a local-only test. A new Windows installation needs its own Google authorization; do not copy another user's encrypted credentials.

1. Install the optional dependencies:

   ```powershell
   & ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-drive-optional.txt
   ```

2. In your Google Cloud project, enable Drive and Picker APIs, configure a Desktop OAuth client and authorize a test user if required. Store its client JSON privately at `.tools/google-drive/client_secret.json`. The account needs Editor/Owner access to the existing target folder `1ixmork-KFJ8xdtQCFJIpUTQm-SnJqeez`; this checkout does not support substituting another folder.
3. Grant that exact folder through the existing Picker and run the privacy check:

   ```powershell
   & ./backend/.venv/Scripts/python.exe -X utf8 scripts/connect_google_drive.py --storage-root runtime --client-file .tools/google-drive/client_secret.json --pick-folder
   & ./backend/.venv/Scripts/python.exe -X utf8 scripts/connect_google_drive.py --storage-root runtime --check --audit
   ```

4. After authorization/privacy pass, set `$env:GOOGLE_DRIVE_ENABLED="true"` in **Terminal 1 before starting/restarting Host**. Confirm startup says `Google Drive: enabled (background upload)`.

Final composites upload privately in the background. Failed uploads remain queued locally. Do not delete pending files or change folder permissions to bypass a privacy error. See [Drive setup](docs/PRIVATE_GOOGLE_DRIVE.md) for authorization problems.

### F. Terminal 2: optional public HTTPS QR and Gallery

Keep Host running first. Internet and `cloudflared` are required. The script checks the executable and can install the official `Cloudflare.cloudflared` winget package on Windows if missing. In another PowerShell at the repository root:

```powershell
$env:PUBLIC_GALLERY_ENABLED="true"
& ./backend/.venv/Scripts/python.exe scripts/mobile_qr_demo.py start --attach-host --host-port 8000 --public-port 8011 --storage-root runtime
```

If Drive is configured and required for the test, append `--require-drive` to this command. It attaches to the existing Host and starts/reuses an isolated photo gateway on **8011** plus a temporary Quick Tunnel. Do not start a standalone demo or another Host.

Wait for the **actual HTTPS URL** and successful isolation checks. Open that origin plus `/gallery` for public browsing. Confirm a new composite and wait for the Result UI to display a verified HTTPS QR before scanning it over 4G/5G. Test both the correct image and Download.

Confirmation durably saves one final composite on Host and creates/reuses its stable share token. The authorized gateway can serve the checksum-verified local staging image while private Drive upload runs asynchronously. QR readiness does **not** wait for Drive `SYNCED`; it requires a reachable, verified HTTPS origin and verification of that session's available photo. Print-ready preparation is separate.

If the tunnel disconnects, public sharing becomes unavailable; the saved composite and upload queue remain intact. Reconnect the tunnel and use **Retry sharing** if automatic retries have stopped. For `getaddrinfo failed (11001)`, check DNS/network connectivity; try another network or configure a working DNS resolver. Do not bypass isolation checks or advertise a localhost/LAN QR as public.

The public gateway serves only Guest Photo resources and the enabled public Gallery. It does not expose Booth, Host login, camera/printing controls or Event Display. Gallery can be empty even when Event Display has photos: public Gallery also requires an issued, unexpired QR. QR links expire 24 hours after first successful public verification; restarting a tunnel does not extend them.

Keep the laptop, Internet and tunnel running. Quick Tunnel domains are temporary; replacing a tunnel can invalidate old printed QR URLs. No permanent cloud server is deployed by these commands.

### G. Optional physical printing

Mock printing is the safe default and sends nothing to a physical printer. For Windows printing, install the printer's manufacturer driver and verify it prints from Windows. Stop Host, add `--printer windows --enable-physical-printing` to the same Host command, then select the installed queue in `/admin`. A print-ready image with QR requires a verified public photo URL. Check paper size, orientation and one real print before event use; Mock tests do not verify a printer.

### H. Basic end-to-end check

1. Complete installation and verify `frontend/dist-host/index.html` exists.
2. **Sony hardware:** before Host startup, run discovery, connection/Live View and the explicitly confirmed one-shutter diagnostic. Open the transferred original JPEG; record each result separately.
3. **Sony hardware:** start Host with `--camera sony_zve10`; check `/api/health` reports `ok` and verify laptop Live Preview. Physical compatibility/stability is still **PENDING** until the tester performs these checks.
4. **iPad/LAN:** pair the iPad and verify Live Preview in Safari.
5. **Sony hardware:** complete a four-photo session and inspect all captured slots.
6. **Sony hardware:** repeat with a six-photo session.
7. Test Pause, Resume, Capture Now, Complete, individual Retake and Start Over. In Pause mode, manually fill all slots and use Complete to open Review without finalizing.
8. Review/customize and select **Confirm, Display Photo & Get QR** to save one official composite and authorize event publication. Temporary originals may be cleaned up after durable finalization; inspect them before confirmation if needed.
9. Check local Event Display publication. With optional public HTTPS configured, check Gallery after the photo has a valid issued QR; verify Host hide/revoke removes it.
10. **Optional public HTTPS/phone:** scan the real QR using 4G/5G; verify the correct photo and Download. This requires a running, verified tunnel, not just a localhost URL.
11. **Optional Drive:** verify upload reaches `SYNCED`. QR and local Event Display must not wait for an otherwise safely staged photo's upload.
12. **Optional printer hardware:** verify the actual printed image and embedded QR, including paper size/orientation.

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
