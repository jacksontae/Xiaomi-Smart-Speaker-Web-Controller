"""The web UI's static build: its content hash for cache-busting URLs, and the static file server."""
import hashlib
import os
import re
from pathlib import Path

from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from server import config

# The web app is ES modules under fixed names. index.html (never cached) loads them from /static/<build>/..., where
# <build> is a hash of everything under static/, so those files may be cached for good: switching pages costs no
# revalidation round trips, and an update changes every URL at once (old and new modules never mix). Relative
# imports and CSS url()s follow the versioned path by themselves. Plain /static/... keeps working, revalidated on
# every load (browsers, and proxies such as Cloudflare, which add a long max-age when none is set, must check back),
# for what is referenced absolutely: manifest icons, the apple-touch icon.
NO_CACHE = {"Cache-Control": "no-cache"}
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}
BUILD_ID = re.compile(r"[0-9a-f]{12}")


class StaticBuild:
    """The current build id of a static folder and its index.html pointed at /static/<build>/."""

    def __init__(self, root):
        self.root = Path(root)
        self.id = ""
        self.index = ""
        self._signature = None

    def refresh(self):
        """Rehash when any file was added, removed or changed (cheap stat walk; edits while developing)."""
        files = sorted(p for p in self.root.rglob("*") if p.is_file())
        signature = [(str(p), st.st_mtime_ns, st.st_size) for p in files for st in (p.stat(),)]
        if signature != self._signature:
            digest = hashlib.sha256()
            for p in files:
                digest.update(p.relative_to(self.root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
            self.id = digest.hexdigest()[:12]
            index = self.root / "index.html"
            html_text = index.read_text(encoding="utf-8") if index.is_file() else ""
            self.index = html_text.replace('"/static/', f'"/static/{self.id}/')
            self._signature = signature
        return self


static_build = StaticBuild(config.STATIC_DIR)


class AppStatic(StaticFiles):
    """/static/<current build>/x: immutable; /static/<other build>/x: gone (a tab from before an update reloads);
    /static/x: revalidated."""

    async def get_response(self, path, scope):
        head, _, rest = path.replace(os.sep, "/").partition("/")
        if BUILD_ID.fullmatch(head):
            if head != (static_build.id or static_build.refresh().id) or not rest:
                return PlainTextResponse("Not found", 404, headers={"Cache-Control": "no-store"})
            response = await super().get_response(rest, scope)
            response.headers.update(IMMUTABLE)
            return response
        response = await super().get_response(path, scope)
        response.headers.update(NO_CACHE)
        return response
