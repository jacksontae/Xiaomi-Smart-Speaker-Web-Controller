"""Accounts: setup, sign-in (password, Google, passkeys) and each member's own account."""
import asyncio
import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from server import config, core
from server.access import Caller, SignedIn, clear_session_cookie, public_api, record
from server.accounts import (
    account_of,
    check_password,
    check_username,
    client_ip,
    current_rp,
    google_claims,
    google_enabled,
    passkey_policy_applies,
    passkey_rp,
    refuse_without_passkey,
    remove_member,
    sign_in_methods,
    start_session,
    throttled,
)
from server.auth import DUMMY_HASH, hash_password, verify_password
from server.config import VOLUME_COALESCE, utc_iso
from server.passkeys import (
    PasskeyError,
    authentication_options,
    b64url_decode,
    challenge_of,
    new_user_handle,
    registration_options,
    verify_authentication,
    verify_registration,
)
from server.schemas import (
    DeleteMeBody,
    GoogleBody,
    LoginBody,
    MeBody,
    PasskeyBody,
    PasskeyName,
    PasswordBody,
    SetupBody,
    clean_text,
)
from server.store import Conflict
from server.version import __version__
from server.webui import static_build

# --- Accounts ---

@public_api.get("/auth/state")
async def auth_state(who: Caller):
    user = who.user if who else None
    state = {
        "needs_setup": core.db.user_count() == 0, "user": user,
        "methods": {"password": True, "google": google_enabled(), "passkey": current_rp() is not None},
    }
    if google_enabled():
        state["google_client_id"] = config.settings.google_client_id
    if user and passkey_policy_applies(user) and not user["has_passkey"]:
        state["passkey_required"] = True  # signed in with a password; the UI should ask for a passkey now
    return state


@public_api.get("/about")
async def about(who: Caller):
    """The About page: version and build for anyone (it opens from the sign-in page too); this server's speaker,
    connection and owner contact only for signed-in members."""
    build = await asyncio.to_thread(static_build.refresh)
    info = {"version": __version__, "build": build.id}
    if who is not None:
        info["server"] = {"speaker": config.settings.speaker_name, "transport": config.settings.transport,
                          "owner_contact": config.settings.owner_contact}
    return info


@public_api.post("/auth/setup")
async def auth_setup(body: SetupBody, request: Request, response: Response):
    if core.db.user_count():
        raise HTTPException(409, "Setup is already done; sign in instead")
    key = (client_ip(request), "#setup")
    throttled(key)
    if not secrets.compare_digest(body.api_token.encode(), config.settings.api_token.encode()):
        raise HTTPException(401, "Wrong API token")
    core.login_throttle.clear(key)
    username = check_username(body.username)
    display_name = clean_text(body.display_name or username, "display_name", 64)
    check_password(body.password)
    user = core.db.create_first_admin(username, display_name, await asyncio.to_thread(hash_password, body.password))
    if user is None:
        raise HTTPException(409, "Setup is already done; sign in instead")
    user = start_session(request, response, user["id"])
    core.db.log(user["display_name"], "login ok", "first-run setup")
    return {"user": user}


@public_api.post("/auth/login")
async def login(body: LoginBody, request: Request, response: Response):
    username, ip = body.username.strip().lower()[:64], client_ip(request)
    key = (ip, username)
    throttled(key)
    user, stored = core.db.credentials(username)
    ok = await asyncio.to_thread(verify_password, body.password, stored or DUMMY_HASH)
    if user is None:
        # Unknown names are coalesced so a flood of guesses can't push real history out of the log.
        core.db.log("system", "login failed", f"{username} from {ip}", coalesce=VOLUME_COALESCE)
        raise HTTPException(401, "Wrong username or password")
    if not ok or user["disabled"]:
        core.db.log("system", "login failed", f"{username} from {ip}")
        raise HTTPException(401, "This account is disabled" if ok else "Wrong username or password")
    core.login_throttle.clear(key)
    refuse_without_passkey(user, ip, "password")
    user = start_session(request, response, user["id"])
    core.db.log(user["display_name"], "login ok", f"from {ip}")
    return {"user": user}


@public_api.post("/auth/google")
async def login_google(body: GoogleBody, request: Request, response: Response):
    """Sign in with a linked Google account; there is no sign-up, so an unknown account is refused."""
    ip = client_ip(request)
    claims = await google_claims(body.credential, ip)
    user = core.db.user_by_google(claims["sub"])
    if user is None:
        core.db.log("system", "login failed", f"Google account {claims['email']} is not linked, from {ip}"[:300])
        raise HTTPException(401, "This Google account isn't linked to a member; sign in with your password and "
                                 "link it under Account first")
    if user["disabled"]:
        core.db.log("system", "login failed", f"{user['username']} (Google) from {ip}")
        raise HTTPException(401, "This account is disabled")
    refuse_without_passkey(user, ip, "Google")
    core.db.link_google(user["id"], claims["sub"], claims["email"])  # keep the shown email current
    user = start_session(request, response, user["id"])
    core.db.log(user["display_name"], "login ok", f"with Google from {ip}")
    return {"user": user}


@public_api.post("/auth/passkey/options")
async def passkey_login_options():
    """Options for navigator.credentials.get(); any passkey registered here may answer."""
    rp = passkey_rp()
    return {"publicKey": authentication_options(rp, core.passkey_challenges.issue("login"))}


@public_api.post("/auth/passkey/verify")
async def passkey_login(body: PasskeyBody, request: Request, response: Response):
    rp, ip = passkey_rp(), client_ip(request)
    key = (ip, "#passkey")
    throttled(key)
    credential = body.credential
    try:
        challenge = challenge_of(credential)
        core.passkey_challenges.take(challenge, "login")
        passkey = core.db.passkey_by_credential(str(credential.get("id", "")))
        if passkey is None:
            raise PasskeyError("This passkey isn't registered here")
        handle = (credential.get("response") or {}).get("userHandle")
        if handle and b64url_decode(str(handle)) != b64url_decode(passkey["user_handle"]):
            raise PasskeyError("This passkey belongs to another account")
        sign_count = await asyncio.to_thread(verify_authentication, rp, credential, challenge, passkey)
    except (PasskeyError, ValueError) as e:  # ValueError: a userHandle that isn't base64url
        core.db.log("system", "login failed", f"passkey: {e} from {ip}"[:300], coalesce=VOLUME_COALESCE)
        raise HTTPException(401, str(e)[:200]) from e
    user = core.db.get_user(passkey["user_id"])
    if user["disabled"]:
        core.db.log("system", "login failed", f"{user['username']} (passkey) from {ip}")
        raise HTTPException(401, "This account is disabled")
    core.login_throttle.clear(key)
    core.db.use_passkey(passkey["id"], sign_count)
    user = start_session(request, response, user["id"])
    core.db.log(user["display_name"], "login ok", f"with a passkey from {ip}")
    return {"user": user}


@public_api.post("/auth/logout")
async def logout(who: SignedIn, request: Request, response: Response):
    if who.session:
        core.db.delete_session(who.session)
    clear_session_cookie(request, response)
    record(who, "logout")
    return {"ok": True}


@public_api.post("/auth/logout-all")
async def logout_all(who: SignedIn, request: Request, response: Response):
    core.db.delete_sessions(account_of(who)["id"])
    clear_session_cookie(request, response)
    record(who, "logout", "all sessions")
    return {"ok": True}


@public_api.post("/auth/password")
async def change_password(body: PasswordBody, who: SignedIn, request: Request):
    user = account_of(who)
    key = (client_ip(request), user["username"])
    throttled(key)
    if not await asyncio.to_thread(verify_password, body.current, core.db.password_hash(user["id"]) or DUMMY_HASH):
        raise HTTPException(401, "Current password is wrong")
    core.login_throttle.clear(key)
    check_password(body.new)
    core.db.update_user(user["id"], {"password_hash": await asyncio.to_thread(hash_password, body.new)})
    core.db.delete_sessions(user["id"], keep=who.session)
    record(who, "password change")
    return {"ok": True}


@public_api.patch("/me")
async def update_me(body: MeBody, who: SignedIn):
    """Any member renames themselves (role, disabled and password stay with owners and /auth/password)."""
    user = account_of(who)
    name = clean_text(body.display_name, "display_name", 64)
    if name == user["display_name"]:
        return user
    updated = core.db.update_user(user["id"], {"display_name": name})
    record(who, "member update", f"{user['username']}: display_name={name}")
    return updated


@public_api.post("/me/google")
async def link_google(body: GoogleBody, who: SignedIn, request: Request):
    user = account_of(who)
    claims = await google_claims(body.credential, client_ip(request))
    try:
        user = core.db.link_google(user["id"], claims["sub"], claims["email"])
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    record(who, "google link", claims["email"])
    return user


@public_api.delete("/me/google")
async def unlink_google(who: SignedIn):
    user = account_of(who)
    if not user["google_email"]:
        raise HTTPException(404, "No Google account is linked")
    if not sign_in_methods(user) - {"google"}:
        raise HTTPException(409, "This is your only way to sign in; set a password or add another method first")
    email = user["google_email"]
    user = core.db.unlink_google(user["id"])
    record(who, "google unlink", email)
    return user


@public_api.post("/me/passkeys/options")
async def passkey_register_options(who: SignedIn):
    """Options for navigator.credentials.create(); the member's existing passkeys are excluded."""
    user, rp = account_of(who), passkey_rp()
    handle, existing = core.db.passkey_handles(user["id"])
    handle = handle or new_user_handle()
    challenge = core.passkey_challenges.issue("register", user["id"], handle)
    return {"publicKey": registration_options(rp, challenge, handle, user["username"], user["display_name"], existing)}


@public_api.post("/me/passkeys")
async def add_passkey(body: PasskeyBody, who: SignedIn):
    user, rp = account_of(who), passkey_rp()
    name = clean_text(body.name or "Passkey", "name", 64)
    try:
        challenge = challenge_of(body.credential)
        handle = core.passkey_challenges.take(challenge, "register", user["id"])
        cred = await asyncio.to_thread(verify_registration, rp, body.credential, challenge)
    except PasskeyError as e:
        raise HTTPException(400, str(e)[:200]) from e
    try:
        passkey = core.db.add_passkey(user["id"], handle, name, cred)
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    record(who, "passkey add", name)
    return passkey


@public_api.get("/me/passkeys")
async def list_passkeys(who: SignedIn):
    return core.db.list_passkeys(account_of(who)["id"])


@public_api.patch("/me/passkeys/{passkey_id}")
async def rename_passkey(passkey_id: int, body: PasskeyName, who: SignedIn):
    name = clean_text(body.name, "name", 64)
    passkey = core.db.rename_passkey(account_of(who)["id"], passkey_id, name)
    if passkey is None:
        raise HTTPException(404, "No such passkey")
    record(who, "passkey rename", name)
    return passkey


@public_api.delete("/me/passkeys/{passkey_id}", status_code=204)
async def delete_passkey(passkey_id: int, who: SignedIn):
    user = account_of(who)
    names = {p["id"]: p["name"] for p in core.db.list_passkeys(user["id"])}
    if passkey_policy_applies(user):
        reason = "Owners must keep at least one passkey"
    elif not sign_in_methods(user) - {"passkey"}:
        reason = "This is your only way to sign in; set a password or add another method first"
    else:
        reason = None
    try:
        gone = core.db.delete_passkey(user["id"], passkey_id, keep_one=reason is not None)
    except Conflict as e:
        raise HTTPException(409, reason) from e
    if not gone:
        raise HTTPException(404, "No such passkey")
    record(who, "passkey remove", names.get(passkey_id))


@public_api.get("/me/export")
async def export_me(who: SignedIn):
    """The member's own data as a JSON download. Device preferences aren't included: they live only in the
    browser (localStorage), never on the server."""
    user = account_of(who)
    data = core.db.export_user(user["id"], who.session)
    record(who, "data export")
    body = {"exported_at": utc_iso(datetime.now(UTC)), "server_version": __version__} | data
    filename = f"speaker-my-data-{datetime.now(config.ZONE).date().isoformat()}.json"
    return JSONResponse(body, headers={"Content-Disposition": f'attachment; filename="{filename}"',
                                       "Cache-Control": "no-store"})


@public_api.delete("/me", status_code=204)
async def delete_me(body: DeleteMeBody, who: SignedIn, request: Request, response: Response):
    """A member deletes their own account, typing their username to confirm (every member has one, whatever
    their sign-in methods). Same cascade as an owner deleting them; the last owner can't leave the server orphaned."""
    user = account_of(who)
    if body.confirm.strip().lower() != user["username"]:
        raise HTTPException(400, "Type your username to confirm")
    try:
        gone = remove_member(user["id"])
    except Conflict as e:
        raise HTTPException(409, "You're the only owner; make another member an owner first") from e
    if not gone:
        raise HTTPException(404, "No such member")
    clear_session_cookie(request, response)
    record(who, "member delete", f"{user['username']} (own account)")
