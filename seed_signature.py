"""Connection to the Seed Signature authority, the service that signs everything.

SeedReflections is an approved partner platform. Its server holds the platform key and asks the authority for a
short-lived signing session; the browser only ever receives that session token and the authority's own widget
address. The platform key never reaches a browser, and nothing here can create or hold a signing key.

Settings (environment): SEED_SIGNATURE_API_URL (the authority, https unless loopback) and
SEED_SIGNATURE_PLATFORM_API_KEY (issued by a Seed Signature administrator through the partner process).
"""
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

_CONTENT_TYPE = re.compile(r"^[a-z_]{2,24}$")
_SIGNATURE_ID = re.compile(r"^[A-Za-z0-9_.:-]{6,120}$")


class SignatureError(ValueError):
    """A reason, safe to show the person. Never contains the platform key."""


def _setting_url():
    return os.environ.get("SEED_SIGNATURE_API_URL", "").strip().rstrip("/")


def _key():
    return (os.environ.get("SEED_SIGNATURE_PLATFORM_API_KEY") or os.environ.get("SEED_SIGNATURE_API_KEY") or "").strip()


def origin_of(url):
    parts = urllib.parse.urlsplit(url or "")
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def configured():
    return bool(_setting_url() and _key())


def authority_origin():
    url = _setting_url()
    parts = urllib.parse.urlsplit(url)
    local = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        raise SignatureError("The Seed Signature address must use https.")
    return origin_of(url)


def create_session(external_user_id, content_type="text", title=""):
    """Ask the authority for a signing session for one SeedReflections user. Returns what the browser widget needs."""
    if not configured():
        raise SignatureError("Seed Signature is not connected on this deployment.")
    origin = authority_origin()
    content_type = str(content_type or "text").strip().lower()
    if not _CONTENT_TYPE.match(content_type):
        raise SignatureError("That content type is not valid.")
    body = json.dumps({"external_user_id": str(external_user_id), "content_type": content_type, "title": str(title or "")[:200]}).encode()
    request = urllib.request.Request(_setting_url() + "/api/v1/embed/sessions", data=body, method="POST", headers={
        "Content-Type": "application/json", "X-Platform-API-Key": _key(), "User-Agent": "SeedReflections-Partner/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.loads(response.read(65536))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise SignatureError("Seed Signature did not accept this platform's key. A Seed Signature administrator needs to check or rotate it.") from None
        if exc.code == 429:
            raise SignatureError("Seed Signature is busy. Try again in a minute.") from None
        raise SignatureError(f"Seed Signature answered with an error ({exc.code}).") from None
    except (urllib.error.URLError, OSError, ValueError):
        raise SignatureError("Seed Signature could not be reached. Try again shortly.") from None
    token, widget = data.get("sessionToken"), data.get("widgetUrl")
    if not isinstance(token, str) or not token or not isinstance(widget, str) or origin_of(widget) != origin:
        raise SignatureError("Seed Signature returned an unexpected answer, so nothing was opened.")
    return {"sessionToken": token, "widgetUrl": widget, "sdkUrl": origin + "/sdk/seed-signature-widget.js", "origin": origin}


def validate_result(signature_id, certificate_url):
    """Check what the widget reported before it is stored with a work artifact."""
    signature_id = str(signature_id or "").strip()
    if not _SIGNATURE_ID.match(signature_id):
        raise SignatureError("The signature id is not valid.")
    certificate_url = str(certificate_url or "").strip()
    if certificate_url and (origin_of(certificate_url) != authority_origin() or len(certificate_url) > 500):
        raise SignatureError("The certificate address does not belong to Seed Signature.")
    return signature_id, certificate_url


def content_digest(text):
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()
