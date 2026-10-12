"""Authentication and signing-key validation."""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from backend.config import Settings


def validate_auth_configuration(settings: Settings) -> bytes:
    """Validate shared-session cookies, signing keys, and verification authority."""

    if not settings.jwt_secret:
        raise RuntimeError("PWC_JWT_SECRET is required")
    if settings.session_cookie_domain:
        raise RuntimeError("deployed session cookies must be host-only")
    expected_cookie = {
        "production": "pwc_session",
        "staging": "pwc_staging_session",
    }[settings.environment]
    if settings.session_cookie_name != expected_cookie:
        raise RuntimeError(
            f"PWC_SESSION_COOKIE_NAME must be {expected_cookie!r} for "
            f"{settings.environment}"
        )
    if settings.shared_session_cookie_name != "pwc_shared_session":
        raise RuntimeError(
            "PWC_SHARED_SESSION_COOKIE_NAME must be 'pwc_shared_session'"
        )
    if settings.shared_session_cookie_domain != ".paperswithcode.co":
        raise RuntimeError(
            "PWC_SHARED_SESSION_COOKIE_DOMAIN must be '.paperswithcode.co'"
        )
    if not settings.session_verification_public_key:
        raise RuntimeError("PWC_SESSION_VERIFICATION_PUBLIC_KEY is required")
    try:
        public_bytes = base64.urlsafe_b64decode(
            settings.session_verification_public_key
            + "=" * (-len(settings.session_verification_public_key) % 4)
        )
        Ed25519PublicKey.from_public_bytes(public_bytes)
    except (ValueError, TypeError) as error:
        raise RuntimeError(
            "PWC_SESSION_VERIFICATION_PUBLIC_KEY must be a base64url Ed25519 key"
        ) from error
    if settings.auth_authority_origin != "https://paperswithcode.co":
        raise RuntimeError(
            "PWC_AUTH_AUTHORITY_ORIGIN must be 'https://paperswithcode.co'"
        )
    required_return_origins = {
        "https://paperswithcode.co",
        "https://staging.paperswithcode.co",
    }
    if settings.auth_return_origin_set != required_return_origins:
        raise RuntimeError(
            "PWC_AUTH_RETURN_ORIGINS must contain production and staging origins"
        )
    if settings.environment == "production":
        if not settings.session_signing_private_key:
            raise RuntimeError("production requires PWC_SESSION_SIGNING_PRIVATE_KEY")
        try:
            private_bytes = base64.urlsafe_b64decode(
                settings.session_signing_private_key
                + "=" * (-len(settings.session_signing_private_key) % 4)
            )
            private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
            derived_public = private_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        except (ValueError, TypeError) as error:
            raise RuntimeError(
                "PWC_SESSION_SIGNING_PRIVATE_KEY must be a base64url Ed25519 key"
            ) from error
        if derived_public != public_bytes:
            raise RuntimeError("shared-session signing and verification keys differ")
    elif settings.session_signing_private_key:
        raise RuntimeError("staging must not have the session signing private key")
    return public_bytes
