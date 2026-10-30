# Camera capability matrix — Phase 5

| Adapter | Host Live View | Capture source | Physical shutter | Camera-original file | Verification |
|---|---|---|---|---|---|
| Host Mock | Generated JPEG frames | Deterministic synthetic JPEG, separate from preview | No | No (synthetic bytes are retained) | Automated backend + browser |
| Host UVC DEMO | OpenCV VideoCapture frames | Explicit webcam/video-frame JPEG | No | No | Fake-driver contract tested; physical webcam NOT TESTED |
| Browser demo (legacy) | iPad/laptop browser webcam or animated canvas | Explicit demo canvas/video frame | No | No | Existing regression tests |
| Vendor SDK placeholder | Unsupported until confirmed | Never substitutes preview/screenshot | Unsupported | Unsupported | BLOCKED BY HARDWARE/model/SDK |
| Fake vendor used only in tests | Synthetic contract fixture | Native-file contract with source=camera_original | Simulated only | Simulated only | Software contract, NOT real device |

No adapter is marked HARDWARE READY. No actual camera/USB/Wi-Fi device, physical shutter, native camera transfer, physical QR scanning or printer paper was tested. Camera name/model cannot be inferred from a healthy backend. Optional UVC is explicitly DEMO, including when a DSLR is exposed as a webcam; it does not gain physical shutter/original JPG capabilities.

Research sources: [Microsoft MediaCapture](https://learn.microsoft.com/en-us/windows/apps/develop/camera/basic-photo-capture) supports Windows photo capture APIs but requires an actual supported device/application integration. [Canon official SDK](https://www.usa.canon.com/support/sdk) and [Canon developer package](https://asia.canon/en/campaign/developerresources/cap) describe model-dependent remote integration; no model/SDK package/license has been provided, so no SDK calls are invented. [OpenCV VideoCapture](https://docs.opencv.org/3.4.20/d8/dfe/classcv_1_1VideoCapture.html) reads video frames; the optional adapter labels that limitation explicitly.

Before a real adapter: supply exact brand/model/firmware, supported OS/architecture, connection type confirmed by manufacturer, official SDK/version/license/redistribution permissions and compatibility list. Verify independently live-view start/stop/format, physical capture receipt, file retrieval/reference persistence/timeouts, original JPG/RAW handling, EXIF orientation, reconnect/resource release, exclusive access and whether live view can run during capture. Prefer SDK calls in a bounded worker process for drivers that may hang; never release capture ownership while an unknown shutter command is still running.

Windows 11 UVC DEMO: install optional requirements into backend/.venv, set APP_ENV=development and CAMERA_ADAPTER=uvc_demo and CAMERA_DEVICE_INDEX matching the connected webcam, enable guest control in Host Dashboard, then explicitly connect from booth. Close competing camera applications and enable Windows Privacy & security → Camera access for desktop apps. Do not assume all devices expose UVC or support the same backend. This path was not opened on physical hardware. Some DirectShow drivers may block inside read; the demo checks deadlines around SDK calls but cannot forcibly cancel a hung native driver. Restart host after verifying the device; do not treat this adapter as event-ready.
