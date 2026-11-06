"""The web UI: index.html and the files iOS looks for at the site root."""
import asyncio

from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from server import config
from server.access import public_api
from server.webui import NO_CACHE, static_build

# --- Web UI (public) ---

@public_api.get("/", response_class=HTMLResponse)
async def index():
    build = await asyncio.to_thread(static_build.refresh)
    if not build.index:
        raise HTTPException(404, "Not found")
    return HTMLResponse(build.index, headers=NO_CACHE)


def static_root_file(name, media_type):
    async def serve():
        path = config.STATIC_DIR / name
        if not path.is_file():
            raise HTTPException(404, "Not found")
        return FileResponse(path, media_type=media_type)

    return serve


# iOS looks for these at the site root.
public_api.get("/manifest.webmanifest", include_in_schema=False)(
    static_root_file("manifest.webmanifest", "application/manifest+json")
)
public_api.get("/apple-touch-icon.png", include_in_schema=False)(static_root_file("apple-touch-icon.png", "image/png"))
