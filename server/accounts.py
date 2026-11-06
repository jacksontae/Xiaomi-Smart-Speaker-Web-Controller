"""Account helpers: credential checks, sign-in methods, removing a member, and who may see personal items."""
import asyncio

from fastapi import HTTPException

from server import config, core
from server.access import set_session_cookie
from server.auth import PASSWORD_MAX, PASSWORD_MIN, new_session_token, normalize_username, token_hash
from server.config import SESSION_COOKIE, VOLUME_COALESCE
from server.google_signin import InvalidToken, KeysUnavailable
from server.passkeys import relying_party

# --- Sign-in checks ---

def check_password(password):
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise HTTPException(400, f"Password must be {PASSWORD_MIN}-{PASSWORD_MAX} characters")


def check_username(username):
    name = normalize_username(username)
    if name is None:
        raise HTTPException(400, "Username must be 3-32 characters of a-z, 0-9, '.', '_' or '-'")
    return name


def client_ip(request):
    return request.client.host if request.client else "unknown"


def throttled(key):
    wait = core.login_throttle.retry_after(key)
    if wait:
        raise HTTPException(429, f"Too many failed attempts; try again in {wait} s", headers={"Retry-After": str(wait)})
    core.login_throttle.fail(key)  # reserved before the slow hash check; cleared on success


def start_session(request, response, user_id):
    old = request.cookies.get(SESSION_COOKIE)
    if old:
        core.db.delete_session(token_hash(old))
    sid = new_session_token()
    core.db.create_session(token_hash(sid), user_id)
    core.db.mark_login(user_id)
    set_session_cookie(request, response, sid)
    return core.db.get_user(user_id)


def google_enabled():
    return config.settings.google_signin and bool(config.settings.google_client_id)


async def google_claims(credential, ip):
    """Verified claims of a Google ID token; failed attempts count against the IP like wrong passwords."""
    if not google_enabled():
        raise HTTPException(409, "Sign in with Google is turned off")
    key = (ip, "#google")
    throttled(key)
    try:
        claims = await asyncio.to_thread(core.google_verifier.verify, credential, config.settings.google_client_id)
    except KeysUnavailable as e:
        core.login_throttle.clear(key)  # not the caller's fault
        raise HTTPException(503, "Couldn't reach Google to check the sign-in; try again") from e
    except InvalidToken as e:
        core.db.log("system", "login failed", f"Google: {e} from {ip}"[:300], coalesce=VOLUME_COALESCE)
        raise HTTPException(401, "Google sign-in failed; try again") from e
    core.login_throttle.clear(key)
    return claims


def current_rp():
    """The passkey relying party, or None while passkeys are switched off or the origin can't use them."""
    s = config.settings
    return relying_party(s.public_base_url, s.speaker_name) if s.passkey_signin else None


def passkey_rp():
    rp = current_rp()
    if rp is None:
        raise HTTPException(409, "Passkeys are off; they need passkey_signin and an https:// public_base_url")
    return rp


def passkey_policy_applies(user):
    return config.settings.passkey_required_for_admins and user["role"] == "admin" and current_rp() is not None


def refuse_without_passkey(user, ip, how):
    """Sign-ins other than a passkey call this: an admin with a passkey must use it while the owner requires it."""
    if passkey_policy_applies(user) and user["has_passkey"]:
        core.db.log("system", "login failed", f"{user['username']} ({how}) needs a passkey, from {ip}")
        raise HTTPException(403, "Owners sign in with a passkey")


def sign_in_methods(user):
    """The ways this member can sign in right now."""
    methods = set()
    if core.db.password_hash(user["id"]):
        methods.add("password")
    if user["google_email"] and google_enabled():
        methods.add("google")
    if user["has_passkey"] and current_rp() is not None:
        methods.add("passkey")
    return methods


# --- Members ---

def account_of(who):
    if who.user is None:
        raise HTTPException(400, "The API token is not a user account")
    return who.user


def remove_member(user_id):
    """Delete the member with everything personal (sessions, passkeys, podcast subscriptions, personal playlists
    and files, Talkie clips) and the files of those on disk; False if there is no such member. Raises Conflict for
    the last enabled admin."""
    clips = core.db.user_clip_files(user_id)
    stored = core.db.delete_user(user_id)
    if stored is None:
        return False
    for name in stored:  # their personal files went with them
        (config.MEDIA_DIR / name).unlink(missing_ok=True)
    for name in clips:  # ... and so did their Talkie clips
        (config.TALKIE_DIR / name).unlink(missing_ok=True)
    return True


# --- Personal items: playlists and files with an owner_id are seen only by that member and admins ---

def owns(row, who):
    return who.user is not None and row["owner_id"] == who.user["id"]


def can_see(row, who):
    """Shared (owner_id NULL), the caller's own, or anything for an admin."""
    return row["owner_id"] is None or who.role == "admin" or owns(row, who)


def personal_owner(who, personal):
    """owner_id for something new: viewers only make personal items, others when they ask for one."""
    if not (personal or who.role == "viewer"):
        return None
    if who.user is None:
        raise HTTPException(400, "The API token can't own personal items")
    return who.user["id"]


def with_rights(row, who, can_edit):
    """The row as sent to this caller: plus `mine` and whether they may change it."""
    return row | {"mine": owns(row, who), "can_edit": can_edit(row, who)}
