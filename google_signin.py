"""Verify the ID tokens that Google Identity Services ("Sign in with Google") hands the browser.

The browser posts the token (`credential`) to us; we check its RS256 signature against Google's published
keys (cached), then `aud` = our client id, `iss`, `exp`/`iat` and `email_verified`. A token is accepted once:
its `jti` is remembered until it expires, so a copied token can't be replayed for another session.
"""
import threading
import time

import jwt

JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
JWKS_CACHE = 3600  # Google rotates its keys every few days and publishes new ones well ahead
LEEWAY = 60  # seconds of clock skew allowed on exp/iat
REQUIRED_CLAIMS = ["iss", "aud", "sub", "exp", "iat"]


class InvalidToken(Exception):
    """The credential is not a valid, fresh Google ID token for this client."""


class KeysUnavailable(Exception):
    """Google's signing keys couldn't be fetched."""


class GoogleVerifier:
    def __init__(self, jwks_url=JWKS_URL, cache_seconds=JWKS_CACHE):
        # Refetches on its own when a token names a key id it hasn't seen (key rotation).
        self.jwks = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=cache_seconds, timeout=10)
        self._used = {}  # jti -> exp of tokens already accepted
        self._lock = threading.Lock()

    def verify(self, credential, client_id):
        """The token's claims; raises InvalidToken or KeysUnavailable. Blocking (may fetch the keys)."""
        if not client_id:
            raise InvalidToken("Google sign-in has no client id")
        try:
            key = self.jwks.get_signing_key_from_jwt(credential)
            claims = jwt.decode(
                credential, key.key, algorithms=["RS256"], audience=client_id, issuer=ISSUERS, leeway=LEEWAY,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.PyJWKClientConnectionError as e:
            raise KeysUnavailable(str(e)) from e
        except jwt.PyJWTError as e:
            raise InvalidToken(str(e)) from e
        if claims.get("email_verified") is not True or not claims.get("email"):
            raise InvalidToken("The Google account's email address is not verified")
        self._use_once(claims)
        return claims

    def _use_once(self, claims):
        jti = claims.get("jti")
        if not jti:
            return
        now = time.time()
        with self._lock:
            for old, exp in list(self._used.items()):
                if exp + LEEWAY < now:
                    del self._used[old]
            if jti in self._used:
                raise InvalidToken("This Google sign-in was already used")
            self._used[jti] = claims["exp"]
