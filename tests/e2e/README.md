# End-to-end browser tests

A Playwright + pytest suite that drives the web app the way people use it, at phone (390×844), iPad (820×1180)
and desktop (1440×900), as the owner, an operator and a viewer, in English and Thai, light and dark.

It is **off by default**: normal `pytest -q` and CI skip it. It runs only when `E2E=1` is set and Playwright
is installed.

## What it does

- Starts its own server (`app.py`) on `E2E_PORT` (default 8130) in a throwaway folder: its own config, database,
  cache and media. The speaker address is `192.0.2.10` (TEST-NET), so nothing ever plays on a real device. Every
  "play" ends in the app's "can't reach the speaker" path. The suite refuses to start if the port is busy.
- Seeds the accounts through the API with a placeholder token written only into that throwaway config.
- Uses Chrome's fake microphone (`--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`) for a real
  Talk live session (WebSocket → ffmpeg → speaker error), and a CDP virtual authenticator for passkeys.
- Music searches (YouTube, radio, podcasts) hit the internet once per source. The other cases mock search
  results with `page.route` so the run repeats the same way every time. Adding a YouTube item makes the server
  look the video up on YouTube.
- Checks every page for JS errors (`pageerror`, `console.error`, missing i18n keys) and sideways scrolling.
- "Soft" checks (`app.soft(...)`) record known problems without stopping the test. The test fails at the end
  with a list of what failed.
- When a test fails, it saves a screenshot to `<E2E_DIR>/artifacts/FAIL-<test>.png`.

| File | Covers |
|---|---|
| `test_01_setup_login.py` | first-account setup, sign-in errors, lockout + countdown, disabled account, passkey offer, passkey add/rename/sign-in/remove |
| `test_02_account_prefs.py` | Account page, language/theme/reduce motion persistence, display name, change password, sign out everywhere, account menu |
| `test_03_members.py` | members add/edit/role/password/disable/delete, self guards, phone sheet, iPad dialog |
| `test_04_methods_settings.py` | sign-in methods switches (Google, passkeys, require passkey), speaker settings save/validation, LAN scan (mocked) |
| `test_05_activity.py` | filters and paging |
| `test_06_announce.py` | announce, quick phrases + Undo, viewer view, Talk live |
| `test_07_music.py` | YouTube/radio/podcasts, favourites, add to playlist, My files upload/rename/delete, 413/415 |
| `test_08_playlists.py` | playlist CRUD + Undo, all six item kinds, reorder (buttons, keyboard, drag, menu), viewer |
| `test_09_schedule.py` | schedule CRUD, switch, once/days, Test it now, desktop panel, viewer |
| `test_10_help.py` | search, deep links, Try it per role |
| `test_11_roles_matrix.py` | every page × role × device, forbidden pages, API role gating |
| `test_12_network.py` | aborted requests: list load, write, boot, blocked page script, status, inline save |
| `test_13_phone_app.py` | phone feels like an app: no zoom (viewport, 16 px fields, iOS gestures), no sideways scroll under stress (320/390 px, long text, toasts, sheets, animations), toasts always go away, touch tooltips open on tap only, same Announce mode switch on Announce and Schedule, no blank frame on page change |

## Run it

You need two Python environments, or one that has everything:

- one for the **server**, with `requirements.txt` installed (set `E2E_SERVER_PYTHON` to its python);
- one for the **tests**, with `pytest`, `httpx` and `playwright` installed (`pip install pytest httpx playwright`,
  then `python -m playwright install chromium`). The unknown-passkey test also needs `cryptography`; without it,
  that test is skipped.

`ffmpeg` on `PATH` turns on the Talk live tests. Without it, they check that Talk live is hidden and skip.

```sh
E2E=1 E2E_SERVER_PYTHON=/path/to/app-venv/bin/python \
  /path/to/test-venv/bin/python -m pytest tests/e2e --confcutdir=tests/e2e -p no:cacheprovider -q
```

`--confcutdir=tests/e2e` keeps the unit-test `tests/conftest.py` (which imports the app) out of the browser run.
On a shared machine, run it at low priority and one browser at a time, e.g. through a slot wrapper like `nice -n 10`.

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `E2E` | unset | `1` turns the suite on |
| `E2E_PORT` | `8130` | port for the test server (never the live service's port) |
| `E2E_DIR` | a new temp folder | server data + `artifacts/` screenshots + `server.log`. It is wiped at the start of a run unless `E2E_KEEP_DATA=1` |
| `E2E_SERVER_PYTHON` | the test python | interpreter that runs `app.py` |

The whole run takes about 10–15 minutes. Most of that time is the offline speaker's 10-second timeouts. Run one
file or one test with `pytest tests/e2e/test_08_playlists.py -k desktop ...`. Test 01 checks first-time setup
only on a fresh `E2E_DIR`. Every other file creates the owner itself when needed.
