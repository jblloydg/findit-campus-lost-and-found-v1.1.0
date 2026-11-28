# Find-IT test tools (v1.1.1, extended in v1.1.2)

Scripts used for the bug hunts and performance tests in `docs/TEST_REPORT_v1.1.1.md`.
Demo passwords come from `demo-logins.txt` (v1.1.2). `crawl.py` also uses a local Developer account named `dev.test` if one exists on the PC (skipped otherwise).
They are **local testing tools only** — never run them against an online site.

Run them from the **project folder** (where `manage.py` is), after `python manage.py migrate`
and `python manage.py seed_demo`, with `DJANGO_DEBUG=1`.

| Script | What it does | Needs |
| --- | --- | --- |
| `crawl.py` | Opens every reachable page as each demo role and lists crashes (5xx). | — |
| `form_fuzz.py` | Sends empty and hostile form data to every route as each role. | — |
| `address_fuzz.py` | Opens pages with broken / hostile address values (`?page=abc`, SQL text, impossible dates…). | — |
| `page_timing.py` | Times key pages (server time, size, number of database queries). | demo data (+ a big chat for a real test) |
| `load_test.py` | Many people chatting at once + notification connections + page loaders + timer runner. `PAIRS=10 LOADERS=5` = realistic, default = heavy. | `pip install websockets aiohttp`, server running on 127.0.0.1:8765 |
| `phone_fps.py CONVERSATION_ID` | Slowed-down phone (4× CPU): opens a chat and measures smoothness during a 200-message burst. | Playwright + Chrome |
| `browser_queue.py` | Stops the server while messages are typed, restarts it, checks each message is saved once. | Playwright + Chrome |
| `browser_notice.py` | Live notices, missed notices and chat catch-up across a server restart. | Playwright + Chrome |
| `media_browser.py` | Photo/video sending: size refusal, 4 MB photo, 20 MB / 59 s video, upload while the server is down. Put `phone_photo.jpg` (> 5 MB), `phone_photo_4mb.jpg` and `phone_video_59s.mp4` in `tools/testing/media/` first. | Playwright + Chrome |
| `page_load.py` (v1.1.2) | Real browser: phone (4× slower CPU, 1.5 Mbit/s) and desktop page load times, data downloaded, and whether the design (CSS) was applied. | Playwright + Chrome |
| `media_open.py CONVERSATION_ID` | Slow phone + slow network: data downloaded when opening a chat full of media, scroll smoothness. | Playwright + Chrome |

Setup for the browser scripts:

```powershell
pip install playwright websockets aiohttp
python -m playwright install chromium     # or set CHROME_PATH to an installed Chrome
```

The scripts start their own server on port 8765 (`manage.py runserver 127.0.0.1:8765 --noreload`)
where needed. Numbers depend on the computer: video re-encoding in particular is slower on a
laptop than on the test machine used for the report.
