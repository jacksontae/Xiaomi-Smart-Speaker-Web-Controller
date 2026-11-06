"""Who is calling: authentication, the role-guarded routers, the activity log and signed media links."""
import hashlib
import hmac
import secrets
import socket
import time
import urllib.parse
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from server import config, core
from server.auth import ROLE_RANK, token_hash
from server.config import MEDIA_URL_TTL, SESSION_COOKIE, SESSION_REFRESH
from server.store import SESSION_TTL

bearer = HTTPBearer(auto_error=False, description="The api_token from config.json (`scripts/speaker token`)")


# --- Who is calling ---

@dataclass
class Principal:
    role: str
    actor: str  # name recorded in the activity log
    user: dict | None = None  # None for the API token
    session: str | None = None  # sha256 of the sid cookie


def unauthorized(detail):
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def cookie_secure(request):
    """The sid cookie's Secure flag (settings.cookie_secure)."""
    if config.settings.cookie_secure != "auto":
        return config.settings.cookie_secure
    if request.url.scheme == "https":
        return True
    base = urllib.parse.urlsplit(config.settings.public_base_url or "")
    return base.scheme == "https" and request.headers.get("host", "").lower() == base.netloc.lower()


def set_session_cookie(request, response, sid):
    response.set_cookie(
        SESSION_COOKIE, sid, max_age=SESSION_TTL, path="/", httponly=True, samesite="strict",
        secure=cookie_secure(request),
    )


def clear_session_cookie(request, response):
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, samesite="strict", secure=cookie_secure(request)
    )


def authenticate(
    request: Request, response: Response, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    """The API token (admin), a web session, or None."""
    if creds is not None:
        if not secrets.compare_digest(creds.credentials.encode(), config.settings.api_token.encode()):
            raise unauthorized("Missing or invalid API token")
        return Principal("admin", "api-token")
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return None
    digest = token_hash(sid)
    user, expires_at = core.db.session_user(digest)
    if user is None:
        return None
    # SameSite=Strict plus a header a cross-site form can't send.
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "speaker-web":
        raise HTTPException(403, "Missing header X-Requested-With: speaker-web")
    if expires_at - time.time() < SESSION_TTL - SESSION_REFRESH:
        core.db.touch_session(digest)
        set_session_cookie(request, response, sid)
    return Principal(user["role"], user["display_name"], user, digest)


Caller = Annotated[Principal | None, Depends(authenticate)]


def require(role):
    def check(who: Caller):
        if who is None:
            raise unauthorized("Not signed in")
        if ROLE_RANK[who.role] < ROLE_RANK[role]:
            raise HTTPException(403, f"This needs the {role} role")
        return who

    check.role = role  # read by the role-matrix test
    return check


require_viewer, require_operator, require_admin = require("viewer"), require("operator"), require("admin")
SignedIn = Annotated[Principal, Depends(require_viewer)]
Who = Annotated[Principal, Depends(authenticate)]  # inside a role-guarded router, never None

viewer_api = APIRouter(dependencies=[Depends(require_viewer)])
operator_api = APIRouter(dependencies=[Depends(require_operator)])
admin_api = APIRouter(dependencies=[Depends(require_admin)])
public_api = APIRouter()  # no role guard: each endpoint checks the caller itself, or takes a signed link


def record(who, action, detail=None, coalesce=0):
    core.db.log(who.actor if who else "system", action, detail, coalesce)


# --- Signed media links ---

def _media_sig(path, params):
    payload = path + "?" + urllib.parse.urlencode(sorted(params.items()))
    return hmac.new(config.settings.api_token.encode(), payload.encode(), hashlib.sha256).hexdigest()


def media_path(path, **params):
    """Signed, time-limited path + query of a media link, relative to this server (a browser plays it as is)."""
    params = {k: str(v) for k, v in params.items()}
    params["exp"] = str(int(time.time()) + MEDIA_URL_TTL)
    params["sig"] = _media_sig(path, params)
    return f"{path}?{urllib.parse.urlencode(params)}"


def media_url(path, **params):
    """A URL the speaker can fetch without a header: signed with the API token and time-limited."""
    return f"{base_url()}{media_path(path, **params)}"


def verify_media(request: Request):
    params = dict(request.query_params)
    sig, exp = params.pop("sig", ""), params.get("exp", "")
    expired = not exp.isdigit() or int(exp) < time.time()
    if expired or not hmac.compare_digest(sig, _media_sig(request.url.path, params)):
        raise HTTPException(403, "Invalid or expired media link")


def content_type_for(path):
    return {".webm": "audio/webm", ".mp3": "audio/mpeg"}.get(path.suffix, "audio/mp4")


def host_ip():
    """The LAN address the speaker can use to reach this machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((config.settings.speaker_ip, 8009))
        return s.getsockname()[0]


def base_url():
    return config.settings.public_base_url or f"http://{host_ip()}:{config.settings.port}"
