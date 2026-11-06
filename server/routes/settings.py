"""Settings, speaker discovery and the activity log (admins)."""
import asyncio
import os

import pychromecast.discovery
from fastapi import BackgroundTasks, HTTPException, Query
from pydantic import ValidationError

from server import config, core, speaker
from server.access import Who, admin_api, record
from server.config import describe_changes, merge_settings, public_settings, readable_errors, save_settings
from server.passkeys import relying_party
from server.speaker import reset_reachability
from server.transport import SPEAKER_ERRORS, make_transport

# --- Settings / speakers ---

@admin_api.get("/settings")
async def get_settings():
    return public_settings(config.settings)


async def close_transport(old):
    async with core.cast_lock:
        try:
            await asyncio.to_thread(old.close)
        except SPEAKER_ERRORS as e:
            print(f"closing the old transport failed: {e!r}")


@admin_api.post("/settings")
async def update_settings(changes: dict, background: BackgroundTasks, who: Who):
    """Partial update. Changing the port restarts the process; launchd brings it back up."""
    if "api_token" in changes:
        raise HTTPException(400, "api_token can't be changed over the API; rotate it with ./speakerctl token --rotate")
    try:
        new = merge_settings(config.settings, changes)
    except ValidationError as e:
        raise HTTPException(422, readable_errors(e.errors())) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if new.passkey_required_for_admins and not config.settings.passkey_required_for_admins:
        if not new.passkey_signin or relying_party(new.public_base_url, new.speaker_name) is None:
            raise HTTPException(409, "Passkeys aren't available; they need passkey_signin and an https:// "
                                     "public_base_url")
        missing = core.db.admins_without_passkey()
        if missing:
            raise HTTPException(409, f"Every admin needs a passkey first; missing: {', '.join(missing)}")
    old, config.settings = config.settings, new
    save_settings(new)
    record(who, "settings change", describe_changes(changes))
    if (new.transport, new.speaker_ip, new.speaker_name, new.mqtt) != (
        old.transport, old.speaker_ip, old.speaker_name, old.mqtt
    ):
        # Swap at once: a call still waiting on an offline old speaker (up to ~10 s) mustn't hold up the save.
        # The old transport closes behind that call, and _transport_gen keeps its result out of the new state.
        old_transport, core.transport = core.transport, make_transport(new)
        speaker._transport_gen += 1
        reset_reachability()  # a new target starts with a clean slate
        core.transport.start()
        core.spawn(close_transport(old_transport))
    restart = new.port != old.port
    if restart:
        background.add_task(lambda: os._exit(0))
    return {"ok": True, "restart": restart, "settings": public_settings(new)}


@admin_api.get("/speakers")
async def speakers():
    def discover():
        found, browser = pychromecast.discovery.discover_chromecasts(timeout=4)
        browser.stop_discovery()
        return [{"name": c.friendly_name, "ip": c.host, "model": c.model_name} for c in found]

    return await asyncio.to_thread(discover)


@admin_api.get("/activity")
async def activity(limit: int = Query(50, ge=1, le=500), before_id: int | None = Query(None, ge=1)):
    return core.db.activity(limit, before_id)
