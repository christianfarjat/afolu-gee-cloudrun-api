"""Google / Cloud IAP authentication helpers for a ForestScan tier.

Defense-in-depth on top of Cloud IAP: the tier reads the identity that IAP
injects and enforces the Google Workspace domain at the application layer.

Identity resolution order:
  1. If IAP_AUDIENCE is set, the signed IAP JWT (header
     `X-Goog-IAP-JWT-Assertion`) is cryptographically verified — signature,
     issuer (`https://cloud.google.com/iap`) and audience.
  2. Otherwise it falls back to the `X-Goog-Authenticated-User-Email` header
     set by IAP (trustworthy only when traffic actually flows through IAP).

Environment variables:
  WORKSPACE_DOMAIN  Allowed Google Workspace domain (default: mjmenergia.com).
  IAP_AUDIENCE      Expected audience of the IAP JWT (enables signature check).
  AUTH_REQUIRED     "false" disables enforcement for local development.
"""

import os
from functools import wraps

from flask import request, jsonify, g

IAP_JWT_HEADER = "X-Goog-IAP-JWT-Assertion"
IAP_EMAIL_HEADER = "X-Goog-Authenticated-User-Email"
IAP_ISSUER = "https://cloud.google.com/iap"
IAP_PUBLIC_KEYS_URL = "https://www.gstatic.com/iap/verify/public_key"

ALLOWED_DOMAIN = os.environ.get("WORKSPACE_DOMAIN", "mjmenergia.com")
IAP_AUDIENCE = os.environ.get("IAP_AUDIENCE")
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "true").lower() != "false"


class AuthError(Exception):
    """Authentication/authorization failure with an HTTP status."""

    def __init__(self, message, status):
        super().__init__(message)
        self.message = message
        self.status = status


def _email_from_header():
    """Email from the IAP-injected header `accounts.google.com:user@domain`."""
    raw = request.headers.get(IAP_EMAIL_HEADER, "")
    if not raw:
        return None
    return raw.split(":")[-1].strip().lower() or None


def _email_from_jwt():
    """Verified email from the signed IAP JWT (only when IAP_AUDIENCE is set)."""
    jwt_assertion = request.headers.get(IAP_JWT_HEADER)
    if not jwt_assertion or not IAP_AUDIENCE:
        return None
    from google.oauth2 import id_token
    from google.auth.transport import requests as ga_requests

    payload = id_token.verify_token(
        jwt_assertion,
        ga_requests.Request(),
        audience=IAP_AUDIENCE,
        certs_url=IAP_PUBLIC_KEYS_URL,
    )
    if payload.get("iss") != IAP_ISSUER:
        raise AuthError("Invalid IAP token issuer", 401)
    return (payload.get("email") or "").lower() or None


def authenticate():
    """Resolve and authorize the caller; return their email or raise AuthError."""
    try:
        email = _email_from_jwt()
    except AuthError:
        raise
    except Exception as e:  # verification/library error -> unauthorized
        raise AuthError(f"IAP token verification failed: {e}", 401)

    if not email:
        email = _email_from_header()
    if not email:
        raise AuthError("Missing IAP authentication", 401)
    if ALLOWED_DOMAIN and not email.endswith("@" + ALLOWED_DOMAIN):
        raise AuthError(
            f"User {email} is not in the allowed domain {ALLOWED_DOMAIN}", 403
        )
    return email


def require_google_auth(fn):
    """Decorator: enforce Google (IAP) auth + Workspace domain on a route."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not AUTH_REQUIRED:
            g.user_email = _email_from_header() or "local-dev"
            return fn(*args, **kwargs)
        try:
            g.user_email = authenticate()
        except AuthError as e:
            return jsonify({"error": e.message}), e.status
        return fn(*args, **kwargs)

    return wrapper


def get_current_user():
    """Email of the authenticated caller for the current request, if any."""
    return getattr(g, "user_email", None)
