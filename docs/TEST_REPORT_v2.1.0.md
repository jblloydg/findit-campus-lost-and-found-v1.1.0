# Find-IT v2.1.0 (in progress) — Test report

Branch `release/2.1.0`. Chrome (Playwright), Python 3.13, Django 5.2, fresh demo data. Grows with each change.

## DES-006 (Report an item layout), 2026-11-28
- `python manage.py test core`: **277 tests, all pass** (5 new tests in `core/tests/test_v210.py`: two
  columns on PC / one on phones, create / edit / walk-in pages keep every field name and id, posting a
  LOST item still works). `makemigrations --check`: no changes.
- `tools/testing/responsive_check.py` (Master Instruction): 1,182 page views at 360, 390, 430, 768,
  1280 and 1920 px, every role: **no Find-IT problems** (the only findings are Django's yellow debug
  404 page for a made-up address, shown only in debug mode).
- Real-browser checks (1920, 1280, 390 px): switching Found → Lost → Found without reloading hides /
  shows the questions and moves Photos to the right column and back; edit page with locked questions
  and existing photos; walk-in page; no sideways scrolling; no console errors.
- Scrolling to reach Publish: PC 1920 2.2 → 1.3 screens (Found) / 0.8 (Lost); PC 1280 2.5 → 1.6 / 0.9;
  phone 390 2.6 → 1.7, with Cancel / Publish always visible at the bottom.
- Measured with the v2.0.0 page as "before".
- Speed: no new files or requests; the stylesheet grew by about 3 KB (under 1 KB compressed).
- Not tested: real phones (Safari / Android); submitting with 11+ photos (captcha) in the new layout
  (unchanged markup, covered by existing tests).
