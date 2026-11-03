# AMAZING RACE 2026 Photobooth

[Quick Start](#4-quick-start) · [iPad and device connections](#5-device-connections) · [Troubleshooting](#8-troubleshooting)

## 1. Project Overview

Capture four or six photos, review and customize them, then confirm one final composite for display, download and printing. The Host laptop runs FastAPI, SQLite, camera control and the print queue. An iPad can operate the Guest UI over the same Wi-Fi or phone hotspot.

The default camera and printer are **Mock** devices for software testing. Real DSLR/mirrorless capture is not implemented; physical camera, printer and iPad behavior must be tested on the intended hardware.

## 2. Requirements

- **Windows 11 and PowerShell:** primary development/test platform.
- **Python 3.12**, **Node.js 22.12 or newer**, npm and Git.
- **Laptop:** runs the Host; keep it powered on and awake.
- **iPad with Safari:** optional for remote Guest operation; use the laptop browser otherwise.
- **Camera:** Mock needs no hardware; a laptop/USB webcam can use experimental UVC DEMO.
- **Printer:** optional, connected to the Host with its operating-system driver installed.
- **Internet:** needed for optional Google Drive uploads and Cloudflare public access.
- **Chrome/Chromium:** needed for automated browser tests.

macOS has [separate setup instructions](docs/MACOS_SETUP.md); startup, camera and printing have not been verified on a Mac. Linux is best-effort. No Docker or cloud server is required for local operation.

## 3. Installation

1. Clone the repository and enter its root directory:

   ```powershell
   git clone https://github.com/trongnghia0907/Photobooth-amazing-race.git
   Set-Location Photobooth-amazing-race
   ```

   If you already have the repository, open its folder instead. All following commands start from the root containing `backend/`, `frontend/` and `scripts/`.

2. Create the backend environment and install locked dependencies:

   ```powershell
   py -3.12 -m venv backend/.venv
   & ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.lock.txt
   ```

3. Install and build the frontend:

   ```powershell
   Push-Location frontend
   npm.cmd ci
   npm.cmd run build:host
   Pop-Location
   ```

These installation steps are not required on every launch. Reinstall dependencies when their lockfiles change. Rebuild the frontend after UI changes.

## 4. Quick Start

### Terminal 1 — start the Host

For laptop-only testing:

```powershell
$env:PUBLIC_GALLERY_ENABLED="true"
& ./backend/.venv/Scripts/python.exe scripts/run_host.py --profile local
```

For an iPad/display computer on the same Wi-Fi or hotspot, use this **instead**:

```powershell
$env:PUBLIC_GALLERY_ENABLED="true"
& ./backend/.venv/Scripts/python.exe scripts/run_host.py --profile lan --lan-ip auto
```

Run only one Host. Enter a Host username, password of at least **12 characters**, and kiosk pairing code of at least **16 characters**. Password/code entry is hidden. There are no default credentials; keep and reuse your credentials on later launches. **Leave this terminal open.**

The Host serves the built frontend and API together on port **8000**. No separate Vite server is needed. Add `--build` to the Host command when you want to rebuild the UI before starting.

### Open the five interfaces

Use `http://localhost:8000` on the laptop. For LAN devices, use the laptop IP printed by the launcher.

| Interface | Path | Access |
| --- | --- | --- |
| Guest Photobooth | `/booth` | Kiosk pairing code |
| Host Dashboard | `/admin` | Host login, laptop localhost only |
| Event Display | `/event-display` | Separate display code issued by Host |
| All-Photos Gallery | `/gallery` | Requires the Gallery flag; eligible published photos only |
| Guest Photo Page | `/p/{token}` | Open the generated QR/share URL; do not type the placeholder |

`/` also opens the Guest UI. Check `http://localhost:8000/api/health` for `status: "ok"`. API documentation at `/docs` is disabled in the built Host application.

Open Booth, pair it, select a layout/timer and press **Start Capturing**. Review the photos and click **Confirm, Display Photo & Get QR** when ready. Use **New Session** for the next guest.

### Terminal 2 — optional Internet QR and Gallery

Local/LAN startup does **not** start a public tunnel. For smartphone access over 4G/5G, first configure Drive if required (section 7), keep Terminal 1 running, then open another PowerShell at the repository root:

```powershell
$env:PUBLIC_GALLERY_ENABLED="true"
& ./backend/.venv/Scripts/python.exe scripts/mobile_qr_demo.py start --attach-host --host-port 8000 --public-port 8011 --storage-root runtime --require-drive
```

This attaches to the existing Host and starts/reuses a photo gateway on **8011**. Omit `--require-drive` for a local-storage-only test. Do not launch a second Host or a separate standalone demo.

Wait for the actual HTTPS URL, complete a **new** photo session, confirm it and keep the result screen open for public URL verification. Scan only when the UI reports QR ready; test the correct image and Download on your phone. Public Gallery uses that HTTPS origin plus `/gallery`.

A stale `running` status file is not proof of connectivity. The live HTTPS photo URL must work. An existing tunnel with different settings must be stopped before starting a replacement.

### Stop or restart

Stop the Host with **Ctrl+C** in Terminal 1, or from another terminal:

```powershell
& ./backend/.venv/Scripts/python.exe scripts/stop_host.py
```

If you started the tunnel, stop it separately:

```powershell
./scripts/stop_mobile_qr_demo.ps1
```

Do not run stop commands when services are already stopped. For a restart, use the same Host credentials and runtime; add `--build` only when the UI needs rebuilding.

## 5. Device Connections

- **Camera → Host laptop:** connect a supported webcam by USB or use its built-in camera. A USB connection alone does not enable DSLR shutter control.
- **iPad → local network:** connect the iPad and laptop to the same Wi-Fi/phone hotspot. Run the LAN command in section 4 and open the printed Booth URL in Safari.
- **Printer → Host laptop:** connect it and install its driver. Configure/select it through the Host before enabling physical printing.
- **Auditorium display → laptop or another computer:** connect a projector/LED by HDMI/USB-C, or open Event Display on a computer on the same LAN. Create a display code in Host, enter it on the display page and use fullscreen (F11 on Windows).

For LAN access, replace `LAPTOP_IP` with the current Wi-Fi IPv4 from `ipconfig`:

- Booth: `http://LAPTOP_IP:8000/booth`
- Event Display: `http://LAPTOP_IP:8000/event-display`
- Gallery: `http://LAPTOP_IP:8000/gallery`

Do not use `localhost` on the iPad. If automatic detection selects a VPN interface, supply the correct address with `--lan-ip LAPTOP_IP`. When DHCP changes the address, reopen the new URL; an existing browser session does not automatically migrate between origins.

### Camera modes

- **Mock:** implemented synthetic preview/capture for testing; no physical camera required.
- **UVC DEMO:** experimental OpenCV webcam frames; physical device compatibility is not guaranteed.
- **Vendor SDK:** blocked placeholder. DSLR/mirrorless shutter and original-JPG retrieval require model-specific integration and hardware verification.

To try the Host webcam, install the optional dependency, stop the Host, and restart it with UVC:

```powershell
& ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-camera-optional.txt
& ./backend/.venv/Scripts/python.exe scripts/run_host.py --profile local --camera uvc_demo
```

Use `--profile lan --lan-ip auto` instead of `--profile local` for iPad access. Close competing camera apps and allow desktop camera access in Windows. See [hardware compatibility](docs/HARDWARE_COMPATIBILITY.md) for limits and physical-device acceptance.

## 6. Main Features

Implemented software workflows, testable with Mock devices:

- **Layouts:** portrait 2×3 (six photos) and landscape 2×2 (four photos).
- **Capture:** countdown, pause/resume, Capture Now and individual-slot retake. After paused manual capture fills every saved slot, **Complete** opens Review without confirming or publishing.
- **Review:** filters, stickers, frames and text; finalization requires explicit guest confirmation.
- **Storage:** one official composite per session; temporary captures retained until safe cleanup. Optional private Drive upload runs asynchronously.
- **Printing:** persistent queue and Mock adapter; Windows GDI and optional CUPS adapters need configured drivers and physical testing.
- **QR sharing:** session-specific photo page/download, after successful public URL verification. QR expiry starts at the first successful verification and lasts **24 hours**; restarting a tunnel does not renew it.
- **Event Display:** four-corner presentation of published composites; polls automatically, independent of Drive upload completion.
- **All-Photos Gallery:** approved/published finals only, with an already-issued, unexpired QR; hidden/revoked images are excluded.

Confirmation explicitly discloses display publication. Host can hide photos; historical private sessions are not automatically published. Gallery may be empty even when Event Display has photos, because its QR/expiry requirements are stricter.

## 7. Configuration

Environment variables apply to the terminal and its child processes. Set them **before** startup; enable Gallery in both Host and tunnel terminals if both should serve it.

- `PUBLIC_GALLERY_ENABLED=true`: enables the Gallery website.
- `GOOGLE_DRIVE_ENABLED=true`: enables private asynchronous upload after OAuth/privacy checks.
- `EVENT_GALLERY_AUTO_PUBLISH=false`: disables automatic publication of newly consented confirmations.

Launcher options/environment can also come from `--env-file`. Example files are templates and are not loaded automatically. Exported environment overrides file values; CLI options take priority. See [configuration and operation modes](docs/EVENT_CONFIGURATION.md).

Keep `runtime/` private and backed up: it contains SQLite, photos, queue state and secrets needed to preserve existing shares. Never delete it to resolve startup errors or commit it to Git. See [backup and recovery](docs/WINDOWS_EVENT_GUIDE.md).

### Optional Google Drive

Install the optional dependency:

```powershell
& ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-drive-optional.txt
```

A fresh setup needs a Google Cloud project with Drive/Picker APIs, a Desktop OAuth client, an authorized account and a destination folder that passes the privacy guard. Follow the [Drive/OAuth and folder-selection guide](docs/PRIVATE_GOOGLE_DRIVE.md); existing valid authorization should be reused.

Check existing credentials and privacy without starting login:

```powershell
& ./backend/.venv/Scripts/python.exe -X utf8 scripts/connect_google_drive.py --storage-root runtime --check --audit
```

Then set `$env:GOOGLE_DRIVE_ENABLED="true"` in Terminal 1 before starting Host. Confirm its startup output says `Google Drive: enabled (background upload)`. Explicit configuration overrides the runtime's remembered Drive setting. Failed uploads remain queued; do not change folder sharing to bypass a privacy/access error.

### Optional Cloudflare and production deployment

The section 4 tunnel workflow requires `cloudflared`; on Windows it can attempt installation using the official `Cloudflare.cloudflared` winget package if missing. See [Mobile QR setup](docs/MOBILE_QR_DEMO.md) for prerequisites and errors.

Quick Tunnel forwards traffic to the laptop; it does not deploy a cloud server. Its hostname is temporary, so old printed QR URLs may fail after replacement. Keep the laptop, Internet and tunnel running.

Only the isolated Guest Photo Page/media endpoints and enabled public Gallery belong on the public gateway. Never tunnel Host port 8000 directly. Host Dashboard, camera/printing management and Event Display remain private. Permanent cloud deployment is not provided by Quick Tunnel; production HTTPS and hardware readiness require separate configuration and validation.

## 8. Troubleshooting

- **Host will not start:** inspect the actual exception/log printed by the launcher. Check `/api/health`, build the frontend if missing, and stop only an existing owned Host. Do not kill unrelated processes or delete runtime/lock files.
- **iPad cannot connect:** check the LAN profile, current IP, same network and hotspot client isolation. On a trusted hotspot, use a Windows Private network profile; do not disable the firewall.
- **Camera missing or losing signal:** check the selected adapter, USB/power, device index, Windows camera permissions and competing apps. Vendor SDK mode is not implemented.
- **Live Preview unavailable:** check network/frame timeouts and Host camera diagnostics. A transport failure does not prove physical camera disconnection; saved photos should remain intact.
- **QR unavailable:** start Host before the tunnel, verify the live HTTPS origin, confirm a new composite and keep Result open. Localhost URLs cannot serve another phone; expired QRs are not automatically renewed.
- **Gallery disabled/empty:** enable its flag before service startup, then check publication, hide/revoke state and QR expiry.
- **Drive upload fails:** check Drive enabled, OAuth/folder access, privacy audit and queue errors. Keep pending local photos.
- **Admin returns 403:** open `http://localhost:8000/admin` on the Host laptop.

If Windows blocks a trusted Private Wi-Fi network, an administrator can add this restricted inbound rule (replace `Wi-Fi` if the adapter name differs):

```powershell
New-NetFirewallRule -DisplayName "Amazing Race Hotspot 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private -InterfaceAlias "Wi-Fi" -RemoteAddress LocalSubnet
```

For developer test commands, use the [Windows guide](docs/WINDOWS_EVENT_GUIDE.md); for event acceptance, use the [event checklist](docs/EVENT_DAY_CHECKLIST.md). Software/Mock test results do not certify physical cameras, printers, Safari/iPad or venue networks.
