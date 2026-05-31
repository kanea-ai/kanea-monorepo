"""Format + hashing primitives for agent API keys.

The key format is ``kna_<env>_<43-char base64url body>``. The body is
HMAC-SHA-256'd with a server-side pepper (``settings.agent_api_key_pepper``)
to derive the row's ``secret_hash`` — bare SHA-256 would let anyone with
DB-only access verify guessed/leaked bodies; HMAC requires also stealing
the app secret.

The prefix (``kna_<env>_``) and the last 4 chars of the body are stored
unhashed in their own columns so the UI can surface a fingerprint and
ops can grep logs. They are never used for auth.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from hashlib import sha256

# Stable, recognisable family prefix. Distinguishable from any future
# token surface (e.g. `knm_` for a hypothetical machine token).
KEY_FAMILY_PREFIX = "kna"

# Body entropy — 32 bytes of CSPRNG output, base64url-encoded to 43
# chars. ~256 bits of entropy, base64url alphabet so the whole key is
# safe to ship in headers, URL params, env vars, …
_BODY_BYTES = 32


@dataclass(frozen=True, slots=True)
class MintedKey:
    """In-memory bundle returned by ``mint``. Plaintext is in
    ``plaintext`` (shown to the operator exactly once) and never
    persisted; only the hash + the unhashed prefix/last4 reach the DB.
    """

    plaintext: str
    prefix: str
    last4: str
    secret_hash: str


def mint(*, env_tag: str, pepper: str) -> MintedKey:
    """Generate a fresh key bundle. ``env_tag`` becomes the literal
    middle segment (``live`` / ``dev``); ``pepper`` is the
    HMAC-SHA-256 key."""
    body = secrets.token_urlsafe(_BODY_BYTES)
    prefix = f"{KEY_FAMILY_PREFIX}_{env_tag}_"
    plaintext = prefix + body
    return MintedKey(
        plaintext=plaintext,
        prefix=prefix,
        last4=body[-4:],
        secret_hash=_hmac_hex(body, pepper),
    )


def parse_and_hash(
    plaintext: str,
    *,
    expected_env_tag: str,
    pepper: str,
) -> str | None:
    """Validate the prefix + env-tag and return the HMAC of the body.

    Returns ``None`` if the input doesn't match ``kna_<env>_<body>`` or
    the env-tag doesn't match the API's configuration — both surface
    as a 401 at the route, with no DB round-trip wasted on an obvious
    cross-env / malformed key.
    """
    parts = plaintext.split("_", 2)
    if len(parts) != 3:
        return None
    family, env, body = parts
    if family != KEY_FAMILY_PREFIX or env != expected_env_tag or not body:
        return None
    return _hmac_hex(body, pepper)


def _hmac_hex(body: str, pepper: str) -> str:
    return hmac.new(
        pepper.encode("utf-8"),
        body.encode("utf-8"),
        sha256,
    ).hexdigest()
