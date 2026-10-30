"""Passkeys (WebAuthn) on top of py_webauthn: relying-party settings, one-time challenges and the two ceremonies.

The relying party is the host of `public_base_url`: browsers only offer passkeys on HTTPS origins (or
http://localhost while developing), and the RP ID must be a domain name, never an IP address.
Challenges live in memory, are bound to their purpose (and user), and are taken exactly once.
"""
import base64
import ipaddress
import json
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

CHALLENGE_TTL = 300  # seconds a ceremony may take
CHALLENGE_LIMIT = 1000  # pending challenges kept at most (anyone can ask for sign-in options)
TIMEOUT_MS = CHALLENGE_TTL * 1000
TRANSPORTS = {t.value for t in AuthenticatorTransport}


class PasskeyError(Exception):
    """The browser's response doesn't verify (bad signature, wrong origin, stale challenge, ...)."""


@dataclass(frozen=True)
class RelyingParty:
    id: str  # e.g. speaker.example.com
    origin: str  # e.g. https://speaker.example.com
    name: str


def relying_party(public_base_url, name):
    """The relying party for this base URL, or None when browsers wouldn't offer passkeys there."""
    if not public_base_url:
        return None
    parts = urllib.parse.urlsplit(public_base_url)
    host = (parts.hostname or "").lower()
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
        return None  # WebAuthn RP IDs are domains
    except ValueError:
        pass
    if parts.scheme != "https" and host != "localhost":
        return None
    return RelyingParty(host, f"{parts.scheme}://{parts.netloc.lower()}", name or host)


def b64url_decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def challenge_of(credential):
    """The challenge the browser signed, read from clientDataJSON (verified again by the library)."""
    try:
        client_data = json.loads(b64url_decode(credential["response"]["clientDataJSON"]))
        return b64url_decode(client_data["challenge"])
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise PasskeyError("Malformed passkey response") from e


class Challenges:
    """Single-use challenges with a short expiry, bound to a purpose and (for registration) a user.

    Each may carry a little data for the second step (the user handle a registration was offered with).
    """

    def __init__(self, ttl=CHALLENGE_TTL, limit=CHALLENGE_LIMIT):
        self.ttl, self.limit = ttl, limit
        self._pending = {}  # challenge -> (purpose, user_id, expires, data)
        self._lock = threading.Lock()

    def issue(self, purpose, user_id=None, data=None):
        challenge = secrets.token_bytes(32)
        now = time.time()
        with self._lock:
            for key, entry in list(self._pending.items()):
                if entry[2] < now:
                    del self._pending[key]
            while len(self._pending) >= self.limit:  # oldest first (dicts keep insertion order)
                del self._pending[next(iter(self._pending))]
            self._pending[challenge] = (purpose, user_id, now + self.ttl, data)
        return challenge

    def take(self, challenge, purpose, user_id=None):
        """Consume the challenge and return its data; raises PasskeyError unless it was issued for this
        purpose and user and hasn't expired."""
        with self._lock:
            entry = self._pending.pop(challenge, None)
        if entry is None or entry[2] < time.time() or entry[:2] != (purpose, user_id):
            raise PasskeyError("This passkey request expired or was already used; try again")
        return entry[3]


def descriptor(credential_id, transports=None):
    kinds = [AuthenticatorTransport(t) for t in transports or () if t in TRANSPORTS]
    return PublicKeyCredentialDescriptor(id=b64url_decode(credential_id), transports=kinds or None)


def registration_options(rp, challenge, user_handle, username, display_name, existing):
    """Options for navigator.credentials.create(), as a JSON-ready dict."""
    options = generate_registration_options(
        rp_id=rp.id, rp_name=rp.name, user_id=b64url_decode(user_handle), user_name=username,
        user_display_name=display_name, challenge=challenge, timeout=TIMEOUT_MS,
        # Discoverable credentials let the sign-in screen skip the username.
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=[descriptor(p["credential_id"], p["transports"]) for p in existing],
    )
    return json.loads(options_to_json(options))


def authentication_options(rp, challenge):
    """Options for navigator.credentials.get(): any passkey of this site (the browser lists them)."""
    options = generate_authentication_options(
        rp_id=rp.id, challenge=challenge, timeout=TIMEOUT_MS, user_verification=UserVerificationRequirement.PREFERRED,
    )
    return json.loads(options_to_json(options))


def verify_registration(rp, credential, challenge):
    """{credential_id, public_key, sign_count, backed_up, transports} of a new passkey."""
    try:
        verified = verify_registration_response(
            credential=credential, expected_challenge=challenge, expected_rp_id=rp.id, expected_origin=rp.origin,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as e:
        raise PasskeyError(f"Couldn't verify the new passkey: {e}") from e
    transports = credential.get("response", {}).get("transports") or []
    return {
        "credential_id": bytes_to_base64url(verified.credential_id),
        "public_key": verified.credential_public_key,
        "sign_count": verified.sign_count,
        "backed_up": verified.credential_backed_up,
        "transports": [t for t in transports if t in TRANSPORTS],
    }


def verify_authentication(rp, credential, challenge, passkey):
    """The new sign counter; raises PasskeyError (also when the counter went backwards: a cloned key)."""
    try:
        verified = verify_authentication_response(
            credential=credential, expected_challenge=challenge, expected_rp_id=rp.id, expected_origin=rp.origin,
            credential_public_key=passkey["public_key"], credential_current_sign_count=passkey["sign_count"],
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as e:
        raise PasskeyError(f"Couldn't verify the passkey: {e}") from e
    return verified.new_sign_count


def new_user_handle():
    return bytes_to_base64url(secrets.token_bytes(32))
