# macOS host setup (alternative platform; NOT TESTED on a Mac)

The shared FastAPI/SQLite/frontend/QR/gallery logic, POSIX locks and shell wrappers are intended to work on macOS. CUPS has fake-process contract tests on Windows. No macOS startup, real camera SDK or physical printing has been executed in this workspace; this is not a full-support claim. Linux can follow the shared commands on a best-effort basis, but is also NOT TESTED.

## Install and prepare

Use Python 3.12 and a Node version satisfying `frontend/package.json` (`>=22.12.0`). Verify `python3 --version`, `node --version` and `npm --version` first. Install from the respective official distributions using the event organization's approved method. The locked requirements include a Windows-only marker for pywin32; it is not required by the shared core on macOS.

From the repository root:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock.txt
cd frontend
npm ci
npm run build:host
cd ..
```

Do not reuse a Windows `.venv` or `node_modules` directory on macOS. Restore runtime data separately. If a locked package has no compatible wheel for your OS/architecture, report that dependency limitation; do not claim the platform passed.

For a local mock rehearsal:

```sh
sh scripts/start_event.sh --mode rehearsal --allow-mock-hardware
```

Enter the Host username, password and kiosk pairing key when prompted. Open `http://localhost:8000/booth`, `/admin` and `/event-display` on the Mac; the display requires its own Host-issued code. Local QR links only work on that computer.

Stop with Ctrl+C in that terminal or:

```sh
sh scripts/stop_event.sh
```

For LAN rehearsal, reserve the Mac's Wi-Fi address in the router and use:

```sh
sh scripts/start_event.sh --mode rehearsal --allow-mock-hardware --profile lan --lan-ip <MAC_LAN_IP>
```

Replace the placeholder before running. Open the printed LAN `/booth` URL on iPad and the display device. Admin remains local to the Mac. Allow the configured Python listener through the macOS application firewall/local-network controls only on the intended private network; do not disable the firewall or expose admin ports to the Internet. Safari/iPad touch, permissions, sleep behavior and real Wi-Fi remain manual acceptance items.

## Camera and printing

A real camera needs its actual vendor SDK, supported model, macOS version and CPU architecture. The repository's vendor adapter is deliberately blocked; no generic Mac camera support is invented. Confirm original camera-generated JPG transfer, shutter command idempotency and SDK recovery on the actual device. macOS camera/privacy permissions and vendor licensing must be checked by the operator.

Optional webcam-frame rehearsal uses `backend/requirements-camera-optional.txt` and `--camera uvc_demo`. Grant camera permission to the actual Python/terminal application in System Settings. This is explicitly video-frame DEMO, not a physical-shutter/original-JPG replacement.

When CUPS and a compatible printer driver are available, inspect queues without printing:

```sh
command -v lp
command -v lpstat
lpstat -p
lpstat -a
```

Add the printer/driver in macOS Printers & Scanners, select the intended paper size/orientation and configure `PRINTER_MODE=cups`, `PRINTER_NAME=<actual-queue-name>`. The adapter lists enabled queues accepting jobs. Configure `CUPS_LP_COMMAND` / `CUPS_LPSTAT_COMMAND` with absolute paths if discovery on PATH is unavailable.

Enable `ENABLE_PHYSICAL_PRINTING=true` only after operator authorization. Perform one controlled print through the application, inspect margins, all 4/6 photos, copy count and QR readability, then record evidence. CUPS receiving a job is not proof that paper printed. A timed-out submission is uncertain: inspect the queue/paper before any retry.

The CUPS adapter uses documented [`lp`](https://openprinting.github.io/cups/doc/man-lp.html) destination/copy/job options and [`lpstat`](https://openprinting.github.io/cups/doc/man-lpstat.html) queue queries. No commands are run through a shell. Driver/filter support for PNG and event paper still requires physical validation.

## Event configuration, projection and handover

Use [EVENT_CONFIGURATION.md](EVENT_CONFIGURATION.md) and copy `deployment/event.env.example` to `deployment/event.env`. Set `PRINTER_MODE=cups`, actual credentials/paths, stable public hostname and private TLS/proxy configuration. Validate using `backend/.venv/bin/python scripts/run_host.py --env-file deployment/event.env --check --no-prompt`. For Event mode, the physical camera/SDK blocker must be resolved and accepted before opening to guests.

Connect the projector/LED with a suitable display adapter. In System Settings > Displays, choose an extended display, place a separate browser window at `/event-display` there, unlock with its display code and select wall/slideshow. Use the browser/system fullscreen control (commonly Control+Command+F). Test actual 16:9 output, HDMI/USB-C, image orientation and code revocation.

Keep the Mac on power and configure sleep/screensaver/automatic updates for the event according to the organization's policy. Watch disk capacity, private logs, printer queue and public QR connectivity. Do not install launch agents automatically. Follow the offline backup/migration procedure before moving data between Windows and macOS; rerun startup, camera and printing acceptance on the new laptop.
