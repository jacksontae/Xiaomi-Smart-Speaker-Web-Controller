"""Password hashing, session tokens and login throttling for web accounts."""
import base64
import hashlib
import math
import re
import secrets
import time

ROLES = ("viewer", "operator", "admin")
ROLE_RANK = {role: rank for rank, role in enumerate(ROLES)}
USERNAME_RE = re.compile(r"[a-z0-9._-]{3,32}")
PASSWORD_MIN = 8
PASSWORD_MAX = 256
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2**14, 8, 1, 32


def _b64(raw):
    return base64.b64encode(raw).decode()


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, AttributeError):
        return False
    return secrets.compare_digest(actual, expected)


# Checked against when the username doesn't exist, so a miss costs the same time as a wrong password.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def new_session_token():
    return secrets.token_urlsafe(32)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_username(username):
    """Lowercased username, or None if it isn't 3-32 chars of [a-z0-9._-]."""
    username = username.strip().lower()
    return username if USERNAME_RE.fullmatch(username) else None


class Throttle:
    """At most `limit` failures per key within `window` seconds.

    Callers reserve a failure *before* the slow password check and clear it on success, so
    concurrent attempts can't all slip past the limit while the hash is being computed.
    """

    def __init__(self, limit=5, window=300):
        self.limit, self.window = limit, window
        self.failures = {}

    def _recent(self, key, now):
        recent = [t for t in self.failures.get(key, ()) if now - t < self.window]
        if recent:
            self.failures[key] = recent
        else:
            self.failures.pop(key, None)
        return recent

    def retry_after(self, key):
        """Seconds until another attempt is allowed, or 0."""
        now = time.time()
        recent = self._recent(key, now)
        if len(recent) < self.limit:
            return 0
        return max(1, math.ceil(recent[-self.limit] + self.window - now))

    def fail(self, key):
        now = time.time()
        if len(self.failures) > 10_000:  # drop stale keys so the dict can't grow without bound
            for k in list(self.failures):
                self._recent(k, now)
        self.failures.setdefault(key, []).append(now)

    def clear(self, key):
        self.failures.pop(key, None)
