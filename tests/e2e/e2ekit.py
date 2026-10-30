"""Shared helpers for the end-to-end suite: constants, the API client, the App page wrapper."""
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect

RUN = secrets.token_hex(6)  # test passwords and the token are made per run, never written in the source


def pw(tag):
    """A throwaway password for this test run."""
    return f"{tag}-{RUN}"

ROOT = Path(__file__).resolve().parents[2]
PORT = int(os.environ.get("E2E_PORT", "8130"))
BASE = f"http://localhost:{PORT}"  # "localhost" (not 127.0.0.1): passkeys and the mic need a secure context
API_TOKEN = "e2e-" + RUN  # placeholder written into the throwaway config only
OWNER = {"username": "owner", "display_name": "Olivia Owner", "password": pw("owner-pass-123"), "role": "admin"}
OPERATOR = {"username": "oscar", "display_name": "Oscar Operator", "password": pw("operator-pass-123"),
            "role": "operator"}
VIEWER = {"username": "vera", "display_name": "Vera Viewer", "password": pw("viewer-pass-123"), "role": "viewer"}
ROLES = {"owner": OWNER, "operator": OPERATOR, "viewer": VIEWER}
VIEWPORTS = {
    "phone": {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True},
    "ipad": {"viewport": {"width": 820, "height": 1180}, "has_touch": True},
    "desktop": {"viewport": {"width": 1440, "height": 900}},
}
SPEAKER_WAIT = 90_000  # ms: the unreachable speaker answers 503 after its ~10 s connect timeout
# console noise that is expected with an offline speaker (the browser logs every non-2xx fetch)
IGNORED_CONSOLE = re.compile(r"Failed to load resource|status of (4\d\d|50\d)")


def port_busy(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


class Api:
    """Direct API access with the Bearer token (acts as the owner) for seeding and checking state."""

    def __init__(self, base):
        self.c = httpx.Client(base_url=base, timeout=60,
                              headers={"Authorization": f"Bearer {API_TOKEN}", "X-Requested-With": "speaker-web"})

    def get(self, path):
        r = self.c.get(path)
        r.raise_for_status()
        return r.json()

    def post(self, path, body=None, ok=True):
        r = self.c.post(path, json=body if body is not None else {})
        if ok:
            r.raise_for_status()
        return r

    def patch(self, path, body):
        r = self.c.patch(path, json=body)
        r.raise_for_status()
        return r.json()

    def delete(self, path):
        return self.c.delete(path)

    def user(self, username):
        return next((u for u in self.get("/users") if u["username"] == username), None)

    def ensure_user(self, spec, **extra):
        u = self.user(spec["username"])
        if u is None:
            body = {k: spec[k] for k in ("username", "display_name", "password", "role")}
            u = self.post("/users", body).json()
        if u["disabled"] or u["role"] != spec["role"]:
            u = self.patch(f"/users/{u['id']}", {"disabled": False, "role": spec["role"]})
        return u


class App:
    """One browser context + page with helpers for this app."""

    def __init__(self, ctx, page, name):
        self.ctx, self.page, self.name = ctx, page, name
        self.errors = []
        self.issues = []  # soft checks: the test goes on, clean() fails at the end
        page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        page.on("console", self._console)

    def _console(self, msg):
        text = msg.text
        if msg.type == "error" and not IGNORED_CONSOLE.search(text):
            self.errors.append(f"console.error: {text}")
        elif msg.type == "warning" and "i18n: missing" in text:
            self.errors.append(f"console.warn: {text}")

    # --- navigation
    def go(self, route="", wait_header=True):
        self.page.goto(f"{BASE}/#/{route}")
        if wait_header:
            self.header()
        return self

    def header(self, text=None):
        h1 = self.page.locator("#view h1.pt").first
        expect(h1).to_be_attached(timeout=15_000)
        if text is not None:
            expect(h1).to_have_text(text)
        return h1

    def hash(self):
        return self.page.evaluate("location.hash")

    # --- checks
    def toast(self, pattern, timeout=8000):
        loc = self.page.locator("#toasts .toast", has_text=re.compile(pattern) if isinstance(pattern, str) else pattern)
        expect(loc.last).to_be_visible(timeout=timeout)
        return loc.last

    def no_hscroll(self, where=""):
        # what a person can actually scroll sideways (body may overflow its own box while html clips it)
        over = self.page.evaluate("""() => { const y = scrollY; scrollTo(400, y); const x = scrollX; scrollTo(0, y);
          return Math.max(x, document.documentElement.scrollWidth - document.documentElement.clientWidth); }""")
        if over > 1:
            culprits = self.page.evaluate("""() => [...document.querySelectorAll('body *')].filter((e) => {
              const r = e.getBoundingClientRect(); return r.width && r.right > innerWidth + 1; }).slice(-4)
              .map((e) => `${e.tagName.toLowerCase()}.${[...e.classList].join('.')}`
                + ` right=${Math.round(e.getBoundingClientRect().right)}`)""")
            raise AssertionError(f"horizontal scroll of {over}px {where} at {self.page.viewport_size} "
                                 f"on {self.hash()}; widest: {culprits}")

    def soft(self, check, what):
        """Run an assertion without stopping the test; clean() reports every soft failure."""
        try:
            check()
        except AssertionError as e:
            self.issues.append(f"{what}: {str(e).splitlines()[0]}")

    def clean(self, where=""):
        self.no_hscroll(where)
        assert not self.errors, f"JS errors {where}: {self.errors}"
        assert not self.issues, f"soft checks failed {where}: {self.issues}"

    def sheet(self):
        """The open sheet/dialog (bottom sheet on phones, dialog on larger screens)."""
        d = self.page.locator("dialog.ov[open]").last
        expect(d).to_be_visible()
        return d

    def no_sheet(self):
        """Wait until every sheet/dialog has finished closing (the page behind is inert until then)."""
        expect(self.page.locator("dialog.ov")).to_have_count(0)

    def shot(self, name):
        path = Path(os.environ.get("E2E_DIR") or tempfile.gettempdir()) / "artifacts" / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), full_page=False)
        return path

    # --- auth
    def login_api(self, spec):
        r = self.ctx.request.post(f"{BASE}/auth/login", headers={"X-Requested-With": "speaker-web"},
                                  data={"username": spec["username"], "password": spec["password"]})
        assert r.ok, f"login {spec['username']}: {r.status} {r.text()}"

    def login_ui(self, spec):
        p = self.page
        p.locator("input[name=username]").fill(spec["username"])
        p.locator("input[name=password]").fill(spec["password"])
        p.locator("form.auth-form button[type=submit]").click()
        expect(p.locator(".shell")).to_be_attached(timeout=15_000)


def wait_for(fn, timeout=10, step=0.25, what="condition"):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = fn()
        if last:
            return last
        time.sleep(step)
    raise AssertionError(f"timed out waiting for {what} (last={last!r})")


FFMPEG_PATHS = ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg")


def mp3_bytes(seconds=1):
    """A small real MP3 (ffmpeg when available, else a stub that starts like one: the server sniffs the header)."""
    ff = shutil.which("ffmpeg") or next((p for p in FFMPEG_PATHS if Path(p).exists()), None)
    if ff:
        r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                            "-i", f"sine=frequency=440:duration={seconds}", "-q:a", "9", "-f", "mp3", "-"],
                           capture_output=True, check=False)
        if r.returncode == 0 and r.stdout:
            return r.stdout
    return b"ID3\x03\x00\x00\x00\x00\x00\x0a" + b"\x00" * 10 + b"\xff\xfb\x90\x64" + b"\x00" * 4000
