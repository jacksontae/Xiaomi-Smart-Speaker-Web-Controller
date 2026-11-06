"""Members: the owner's member list, and resetting a member's sign-in methods."""
import asyncio

from fastapi import HTTPException

from server import core
from server.access import Who, admin_api, record
from server.accounts import check_password, check_username, remove_member, sign_in_methods
from server.auth import hash_password
from server.schemas import NewUserBody, UserPatch, clean_text
from server.store import Conflict

# --- Members ---

@admin_api.get("/users")
async def list_users():
    return core.db.list_users()


@admin_api.post("/users")
async def create_user(body: NewUserBody, who: Who):
    username = check_username(body.username)
    display_name = clean_text(body.display_name or username, "display_name", 64)
    check_password(body.password)
    try:
        password_hash = await asyncio.to_thread(hash_password, body.password)
        user = core.db.create_user(username, display_name, body.role, password_hash)
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    record(who, "member create", f"{username} ({body.role})")
    return user


@admin_api.patch("/users/{user_id}")
async def update_user(user_id: int, body: UserPatch, who: Who):
    changes = body.model_dump(exclude_none=True)
    target = core.db.get_user(user_id)
    if target is None:
        raise HTTPException(404, "No such member")
    myself = who.user is not None and who.user["id"] == user_id
    if myself and (changes.get("disabled") or changes.get("role", who.user["role"]) != who.user["role"]):
        raise HTTPException(409, "You can't disable or demote yourself")
    if "display_name" in changes:
        changes["display_name"] = clean_text(changes["display_name"], "display_name", 64)
    if "password" in changes:
        check_password(changes["password"])
        changes["password_hash"] = await asyncio.to_thread(hash_password, changes.pop("password"))
    try:
        user = core.db.update_user(user_id, changes)
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    if "password_hash" in changes or changes.get("disabled"):
        core.db.delete_sessions(user_id, keep=who.session if myself else None)
    fields = [f"{k}={changes[k]}" for k in ("display_name", "role", "disabled") if k in changes]
    if "password_hash" in changes:
        fields.append("password")
    record(who, "member update", f"{target['username']}: {', '.join(fields) or 'no changes'}")
    return user


@admin_api.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, who: Who):
    if who.user is not None and who.user["id"] == user_id:
        raise HTTPException(409, "You can't delete yourself")
    target = core.db.get_user(user_id)
    try:
        gone = target is not None and remove_member(user_id)
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    if not gone:
        raise HTTPException(404, "No such member")
    record(who, "member delete", target["username"])


# Owner reset: take back a lost phone's passkey or a Google account that isn't the member's any more.
# Members add these themselves in Account (/me/...); each removal signs the member out of every device.

def reset_target(user_id, who):
    if who.user is not None and who.user["id"] == user_id:
        raise HTTPException(409, "Use Account to change your own sign-in methods")
    target = core.db.get_user(user_id)
    if target is None:
        raise HTTPException(404, "No such member")
    return target


@admin_api.get("/users/{user_id}/passkeys")
async def member_passkeys(user_id: int):
    if core.db.get_user(user_id) is None:
        raise HTTPException(404, "No such member")
    return core.db.list_passkeys(user_id)


@admin_api.delete("/users/{user_id}/passkeys/{passkey_id}", status_code=204)
async def remove_member_passkey(user_id: int, passkey_id: int, who: Who):
    target = reset_target(user_id, who)
    names = {p["id"]: p["name"] for p in core.db.list_passkeys(user_id)}
    try:  # never leave them with no way in: set a new password for them first
        gone = core.db.delete_passkey(user_id, passkey_id, keep_one=not sign_in_methods(target) - {"passkey"})
    except Conflict as e:
        raise HTTPException(409, "This is their only way to sign in; set a new password for them first") from e
    if not gone:
        raise HTTPException(404, "No such passkey")
    core.db.delete_sessions(user_id)
    record(who, "member update", f"{target['username']}: removed passkey {names.get(passkey_id)}")


@admin_api.delete("/users/{user_id}/google")
async def unlink_member_google(user_id: int, who: Who):
    target = reset_target(user_id, who)
    if not target["google_email"]:
        raise HTTPException(404, "No Google account is linked")
    if not sign_in_methods(target) - {"google"}:
        raise HTTPException(409, "This is their only way to sign in; set a new password for them first")
    user = core.db.unlink_google(user_id)
    core.db.delete_sessions(user_id)
    record(who, "member update", f"{target['username']}: unlinked Google {target['google_email']}")
    return user
