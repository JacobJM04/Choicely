"""
Web Push for proactive check-ins.

Until now a check-in only surfaced if you happened to have Choicely open
(and, in the demo, advanced the clock). This closes that gap: the browser
registers a Push subscription, and when a decision's check-in comes due
Choicely pushes a notification even with the tab closed.

There is no long-running scheduler in this app, so "check-ins come due" is
driven by the same two triggers that already move time forward:
  - POST /demo/advance  (the demo clock)
  - a real deployment would call notify_due() from a cron / task queue

VAPID keys are generated once on first use and cached in data/vapid_*.pem
(gitignored) so there is zero setup -- the frontend fetches the public key
from GET /push/config.

Degrades cleanly: if pywebpush isn't installed, or the browser doesn't
support push, or the user declines, the in-app check-in banner still works
exactly as before.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

from . import models

_DATA = Path(os.environ.get("CHOICELY_DATA") or (Path(__file__).resolve().parent.parent / "data"))
_PRIVATE_PEM = _DATA / "vapid_private.pem"
_PUBLIC_TXT = _DATA / "vapid_appserverkey.txt"

# mailto: contact required by the Web Push spec for VAPID claims.
_VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:hello@choicely.app")

# A deploy without a persistent volume can pass the keypair in as env vars so
# push subscriptions survive a redeploy. VAPID_PRIVATE_KEY is the PEM contents.
_ENV_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY")
_ENV_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY")

# The server POSTs the (encrypted) push payload to whatever endpoint the
# subscription names, so an unrestricted endpoint is an SSRF hole. Only accept
# the real browser push services; CHOICELY_PUSH_ALLOW_ANY=1 lifts this for
# local testing against a mock.
_ALLOWED_PUSH_HOST_SUFFIXES = (
    "push.services.mozilla.com",
    "fcm.googleapis.com",
    "android.googleapis.com",
    "notify.windows.com",
    "push.apple.com",
    "web.push.apple.com",
)
_PUSH_ALLOW_ANY = os.environ.get("CHOICELY_PUSH_ALLOW_ANY") in ("1", "true", "True")


def _host_allowed(endpoint: str) -> bool:
    """Cheap check: https + host is one of the real push services. No DNS."""
    if _PUSH_ALLOW_ANY:
        return True
    try:
        u = urlparse(endpoint)
    except ValueError:
        return False
    if u.scheme != "https" or not u.hostname:
        return False
    host = u.hostname.lower()
    return any(host == s or host.endswith("." + s) for s in _ALLOWED_PUSH_HOST_SUFFIXES)


def _endpoint_is_safe(endpoint: str) -> bool:
    """Full check, used at subscribe time: allowlisted host AND it doesn't
    resolve to a private / loopback / link-local address (guards against a
    poisoned DNS record on an allowed domain)."""
    if _PUSH_ALLOW_ANY:
        return True
    if not _host_allowed(endpoint):
        return False
    host = urlparse(endpoint).hostname
    try:
        for *_, sa in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(sa[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
    except (socket.gaierror, ValueError, OSError):
        return False
    return True

try:
    from pywebpush import WebPushException, webpush  # type: ignore

    _AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _AVAILABLE = False

    class WebPushException(Exception):
        pass


def available() -> bool:
    return _AVAILABLE


def _ensure_keys() -> None:
    if _ENV_PRIVATE and _ENV_PUBLIC:
        _DATA.mkdir(parents=True, exist_ok=True)
        if not _PRIVATE_PEM.exists():
            _PRIVATE_PEM.write_text(_ENV_PRIVATE)
        return
    if _PRIVATE_PEM.exists() and _PUBLIC_TXT.exists():
        return
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid01

    v = Vapid01()
    v.generate_keys()
    _DATA.mkdir(parents=True, exist_ok=True)
    _PRIVATE_PEM.write_bytes(v.private_pem())
    pub = v.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    _PUBLIC_TXT.write_text(base64.urlsafe_b64encode(pub).rstrip(b"=").decode())


def public_key() -> str | None:
    if not _AVAILABLE:
        return None
    if _ENV_PUBLIC:
        return _ENV_PUBLIC.strip()
    _ensure_keys()
    return _PUBLIC_TXT.read_text().strip()


def config() -> dict:
    return {"enabled": _AVAILABLE, "public_key": public_key()}


def add_subscription(sub: dict) -> None:
    endpoint = sub.get("endpoint")
    if not endpoint or not isinstance(endpoint, str):
        raise ValueError("subscription is missing an endpoint")
    if len(endpoint) > 1000 or len(json.dumps(sub)) > 4000:
        raise ValueError("subscription payload is too large")
    if not _endpoint_is_safe(endpoint):
        raise ValueError("endpoint is not a recognised push service")
    models.save_push_subscription(endpoint, json.dumps(sub))


def remove_subscription(endpoint: str) -> None:
    models.delete_push_subscription(endpoint)


def _send(sub_row: dict, payload: dict) -> bool:
    """Push to one subscription. Returns False (and prunes it) if the
    endpoint is gone; raises for transient errors."""
    if not _host_allowed(sub_row["endpoint"]):  # cheap re-check at send time
        models.delete_push_subscription(sub_row["endpoint"])
        return False
    try:
        webpush(
            subscription_info=json.loads(sub_row["sub_json"]),
            data=json.dumps(payload),
            vapid_private_key=str(_PRIVATE_PEM),
            vapid_claims={"sub": _VAPID_SUBJECT},
            timeout=5,
        )
        return True
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):  # gone -- drop it
            models.delete_push_subscription(sub_row["endpoint"])
            return False
        raise


# Hard cap on how many endpoints one call will contact -- the table is
# already capped, but this bounds the worst-case request latency regardless.
_MAX_FANOUT = 25


def broadcast(payload: dict) -> int:
    """Send `payload` to every stored subscription. Returns delivered count."""
    if not _AVAILABLE:
        return 0
    _ensure_keys()
    delivered = 0
    for row in models.list_push_subscriptions()[:_MAX_FANOUT]:
        try:
            if _send(row, payload):
                delivered += 1
        except Exception:  # noqa: BLE001 - one bad endpoint shouldn't stop the rest
            continue
    return delivered


def _payload_for(decision: dict) -> dict:
    return {
        "title": "Choicely — how did it land?",
        "body": f"You were weighing: “{decision['text']}”",
        "tag": f"checkin-{decision['id']}",
        "url": "/?from=push",
        "decision_id": decision["id"],
    }


def notify_due() -> dict:
    """Push a notification for every check-in that is now due and hasn't
    been pushed yet. Idempotent -- safe to call on every clock advance."""
    if not _AVAILABLE:
        return {"available": False, "notified": 0, "delivered": 0}
    due = [d for d in models.get_due_check_ins() if d.get("notified_at") is None]
    delivered = 0
    for decision in due:
        delivered += broadcast(_payload_for(decision))
        models.mark_checkin_notified(decision["id"])
    return {"available": True, "notified": len(due), "delivered": delivered}


def send_test() -> dict:
    n = broadcast(
        {
            "title": "Choicely notifications are on",
            "body": "This is what a check-in will look like.",
            "tag": "choicely-test",
            "url": "/",
        }
    )
    return {"delivered": n}
