"""End-to-end browser tests (Playwright). Off by default: set E2E=1 and have playwright installed.

The suite starts its own server (app.py) in a throwaway folder with an unreachable speaker (192.0.2.10, TEST-NET),
so nothing ever plays on a real device. See tests/e2e/README.md.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

try:
    import httpx
    from playwright.sync_api import sync_playwright

    from .e2ekit import API_TOKEN, BASE, OPERATOR, OWNER, PORT, ROLES, VIEWER, VIEWPORTS, Api, App, port_busy
    HAVE_PW = True
except ImportError:  # normal `pytest -q` / CI: no browser toolkit
    HAVE_PW = False

if not (HAVE_PW and os.environ.get("E2E") == "1"):
    collect_ignore_glob = ["test_*.py"]

ROOT = Path(__file__).resolve().parents[2]
PREFS_JS = """(() => { const p = PREFS; for (const [k, v] of Object.entries(p)) {
  try { if (localStorage.getItem(k) === null) localStorage.setItem(k, v); } catch (e) { /* private mode */ } } })();"""


# ------------------------------------------------------------------ server
@pytest.fixture(scope="session")
def workdir():
    base = os.environ.get("E2E_DIR")
    path = Path(base) if base else Path(tempfile.mkdtemp(prefix="speaker-e2e-"))
    if path.exists() and not os.environ.get("E2E_KEEP_DATA"):
        for name in ("config.json", "data.db", "data.db-wal", "data.db-shm"):
            (path / name).unlink(missing_ok=True)
        for name in ("cache", "media"):
            shutil.rmtree(path / name, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    (path / "artifacts").mkdir(exist_ok=True)
    return path


@pytest.fixture(scope="session")
def server(workdir):
    if port_busy(PORT):
        pytest.exit(f"port {PORT} is already in use; set E2E_PORT to a free port", returncode=3)
    config = {
        "transport": "cast", "speaker_ip": "192.0.2.10", "speaker_name": "Test speaker", "port": PORT,
        "public_base_url": BASE, "api_token": API_TOKEN, "tts_lang": "en", "passkey_signin": True,
    }
    (workdir / "config.json").write_text(json.dumps(config, indent=2))
    env = {
        **os.environ,
        "CONFIG_PATH": str(workdir / "config.json"), "DATA_PATH": str(workdir / "data.db"),
        "CACHE_DIR": str(workdir / "cache"), "MEDIA_DIR": str(workdir / "media"),
        "UPLOAD_MAX_MB": "1",  # so the "file too big" path is cheap to reach
        "PATH": os.pathsep.join([os.environ.get("PATH", ""), "/opt/homebrew/bin", "/usr/local/bin"]),
    }
    for k in ("PUBLIC_BASE_URL", "SPEAKER_TRANSPORT", "MQTT_HOST"):
        env.pop(k, None)
    python = os.environ.get("E2E_SERVER_PYTHON", sys.executable)
    log = open(workdir / "server.log", "w")  # noqa: SIM115 - closed at teardown
    proc = subprocess.Popen(["nice", "-n", "10", python, "app.py"], cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            pytest.exit(f"server exited early, see {workdir / 'server.log'}", returncode=3)
        try:
            if httpx.get(f"{BASE}/auth/state", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    else:
        proc.terminate()
        pytest.exit("server did not start", returncode=3)
    yield BASE
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


@pytest.fixture(scope="session")
def api(server):
    return Api(server)


@pytest.fixture(scope="session")
def owner_ready(api):
    """The owner account exists (test_01 creates it through the UI; otherwise it is made here)."""
    if httpx.get(f"{BASE}/auth/state").json()["needs_setup"]:
        r = httpx.post(f"{BASE}/auth/setup", headers={"X-Requested-With": "speaker-web"},
                       json={"api_token": API_TOKEN, **{k: OWNER[k] for k in ("username", "display_name", "password")}})
        r.raise_for_status()
    return OWNER


@pytest.fixture
def drained(api):
    """Wait until the server has worked through queued speaker calls. With the speaker offline every /status
    holds the server's speaker lock for its ~10 s timeout, and calls from closed test pages still run, so
    speaker-error tests first let that queue empty (a /status from here returns once it is its turn)."""
    t0 = time.time()
    try:
        api.c.get("/status", timeout=600)
    except httpx.HTTPError:
        pass
    print(f"[e2e] speaker queue drained in {time.time() - t0:.0f}s")


@pytest.fixture(scope="session")
def seeded(api, owner_ready):
    api.ensure_user(OPERATOR)
    api.ensure_user(VIEWER)
    return api


# ------------------------------------------------------------------ browser
@pytest.fixture(scope="session")
def pw():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(pw):
    b = pw.chromium.launch(headless=True, args=[
        "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--disable-gpu",
    ])
    yield b
    b.close()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture
def make_app(browser, server, request, workdir):
    """make_app(role='owner'|'operator'|'viewer'|None, device='phone'|'ipad'|'desktop', lang, theme, motion, offer)."""
    os.environ.setdefault("E2E_DIR", str(workdir))
    apps = []

    def factory(role="owner", device="desktop", lang="en", theme="light", motion=None, offer=False, route="", go=True,
                reduced_media=False):
        opts = dict(VIEWPORTS[device])
        if reduced_media:
            opts["reduced_motion"] = "reduce"
        ctx = browser.new_context(base_url=BASE, locale="en-GB", timezone_id="Asia/Bangkok", **opts)
        ctx.grant_permissions(["microphone"], origin=BASE)
        prefs = {"spk.lang": lang, "spk.theme": theme}
        if motion:
            prefs["spk.motion"] = motion
        if not offer:
            prefs["spk.pkOffer"] = "never"
        # only fills keys that are not set yet, so settings changed in the UI survive reloads
        ctx.add_init_script(PREFS_JS.replace("PREFS", json.dumps(prefs)))
        page = ctx.new_page()
        page.set_default_timeout(10_000)
        app = App(ctx, page, f"{request.node.name}-{len(apps)}")
        apps.append(app)
        if role:
            app.login_api(ROLES[role])
        if go:
            app.go(route, wait_header=bool(role))
        return app

    yield factory
    failed = getattr(request.node, "rep_call", None) is not None and request.node.rep_call.failed
    for a in apps:
        if failed:
            safe = re.sub(r"[^\w.-]+", "_", a.name)[:120]
            try:
                print(f"\n[e2e] screenshot: {a.shot('FAIL-' + safe)}")
            except Exception as e:  # noqa: BLE001 - best effort
                print(f"[e2e] screenshot failed: {e}")
        a.ctx.close()


@pytest.fixture
def owner_app(make_app, seeded):
    return make_app("owner")


