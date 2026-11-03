# Asynchronous photo workflow — focused verification 31/10/2026

Before: durable composite → completion/job → **wait for Drive SYNCED** → share/QR → repeated Drive privacy/download on every guest image request.

Now: durable composite + official final + persistent upload job → stable share/QR → bounded HTTPS gateway registration check → usable public QR. Drive upload/verification runs independently in the existing worker. Authorized public image requests prefer checksum-verified local staging; missing local data uses the existing verified Drive recovery path. A missing pending image produces the branded processing page with automatic retry, without exposing Download early. No OAuth scopes or folder permissions changed.

The public `/p/{token}/status` endpoint validates the same token/revocation rules and returns only registration plus the official image fingerprint. The owner-only `/api/sessions/{session_id}/public-status` probes the configured HTTPS gateway directly, verifies that fingerprint and leases the proof for eight seconds. The Guest UI never labels an unverified HTTPS share ready. Existing 5-second polling recovers connectivity. Host/private endpoints remain absent from the gateway.

Local cache is retained for safe offline recovery. The official Drive composite is unchanged. Print-ready derivatives still use a separate QR footer, and the four-corner Gallery still uses consent/approval filtering. The worker keeps its OS lease and now also rejects overlapping calls on the same instance. Reserved IDs, checksum/ACL verification and durable retries are preserved.

## Actual measurements

One disposable six-photo mock-capture session (`a6f7b504-bc20-4c4d-a65c-39680042f0e9`) used the real private Drive worker and real Cloudflare gateway. No historical photos were requeued.

| Stage | Time |
|---|---:|
| Mock composite generation | 24.3 ms |
| Validate and durably save composite | 56.3 ms |
| Complete + durable upload job + cleanup | 88.3 ms |
| Stable share + QR/footer | 93.5 ms |
| Actual HTTPS session registration | 813.6 ms |
| Public page + preview/download + security requests | 2946.5 ms |
| Additional observed wait for Drive SYNCED | 10088.1 ms |

Public QR was verified about **907 ms after durable completion**, while the upload job was still **PENDING**. Verified Drive persistence followed about **13.9 seconds after completion**. This is one observation, not a performance guarantee. The existing already-running Host worker handled that upload, so separate real upload versus remote-verification durations were not available in that run. New lightweight numeric-only logs expose composite durability, completion/job persistence, share finalization, QR raster generation, gateway registration and worker privacy/upload/verification timings after Host restart. No credentials, image contents or full share tokens are logged by these metrics.

Private Drive file ID: `1tcgzB8LuhbeTJlS5MsAYTPfKYv6pTsQW`. SQLite SYNCED, remote size/MD5 verified; stable token, correct HTTPS footer QR, preview/download equality and private-route isolation verified. The real local photo was immediately available before upload completed. The pending → ready and offline/lost-ACK paths were separately tested with FakeDrive and missing temporary test cache, not claimed as real-network failures.

## Tests

- 28 focused backend tests passed: async flow, Drive recovery, footer, consent and gateway isolation. The async Gallery assertion was then strengthened and its three focused cases passed again.
- 4 frontend unit tests passed; two browser journeys (4/6 shots, consent, HTTPS QR, download, mock print, new guest) passed. Browser gateway reachability is mocked; persistence/rendering use an isolated real backend. Actual HTTPS reachability was verified separately above.
- Host production frontend build passed. No full repository suite run. Physical camera, physical printing and smartphone scanning were not tested.

## Files

Backend: `app/services/{sharing,repository,drive_storage}.py`, `app/{routers,guest}.py`.
Frontend: `src/services/{qr-client,print-client}.js`, `src/components/qr-view.js`, `src/features/result/result.js`.
Tests: `backend/tests/{test_async_photo_workflow,test_drive_storage}.py`, `frontend/tests/{qr-monitor,printing}.test.js`, `frontend/tests/preview/layout-preview.spec.js`, `frontend/playwright.preview.config.js`.
Local evidence: `.tools/async-audit-result.json` (timings and non-secret identifiers; no share token).

## Apply to the operator Host

The supervised public gateway has been updated without creating a duplicate Host. The existing Host process must be restarted to load its new owner-only API and async finalization code. Keep its current credentials; do not reset SQLite or OAuth:

```powershell
& .\backend\.venv\Scripts\python.exe scripts\stop_host.py
& .\backend\.venv\Scripts\python.exe scripts\run_host.py --env-file deployment/integration.env
```

Enter the existing Host credentials/pairing key when prompted. The gateway may stay running against the same runtime, preserving its active origin. Refresh the Guest UI to load the newly built frontend. Smartphone testing remains an operator action.
