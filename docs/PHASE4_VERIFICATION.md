# Phase 4 gate before Phase 5

Source audited: session/storage transactions and migrations 001–004, immutable share/QR/print-ready, owner print API, FIFO worker/OS lease, printer contract/GDI, Host authentication/CSRF/gallery/queue, frontend Result/capture/retake and tests.

Fresh execution before camera changes: backend **59 PASS**, Node **8 PASS**, Playwright **15 PASS**, demo/production builds **PASS**. Tests verify exact Guest/Mock image hash, embedded QR decode, pixel preservation/no overlap, three layouts, retake/edit/share immutability, lost ACK idempotency, auth/IDOR/logout, queue restart/ambiguity. Original HTML/legacy unchanged.

Audit fixes: reject expired/revoked share again at dispatch (it could change while queued); backend root redirects to login shell instead of confusing 404. Focused test verifies no dispatch after revocation and redirect. No unauthenticated gallery/data is added.

PASS: Phase 1–4 core software after the above fixes. FAIL: no unresolved core software blocker. NOT TESTED: physical paper/driver/paper margins/DPI, QR scan by phone, public DNS/TLS/Internet, actual iPad Safari. NOT IMPLEMENTED: CUPS, camera SDK, public deployment (outside Phase 4 gate).

Dimension policy: print-ready width=max(original width,640), proportional composite height; separate white footer QR+2 margins, QR uses integer module scaling, margin=max(24,width/40). Original aspect retained in content region, whole-sheet aspect grows with footer; GDI contain-fits whole sheet. This is software-verified, not calibrated to an actual printer/paper. No physical QR scan claimed.

Focused printing/auth audit regression: **18 passed** after fixes. Phase 4 core software gate passed; proceeded to Phase 5. No commit/push.
