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
import json
from pathlib import Path

from . import models

_DATA = Path(__file__).resolve().parent.parent / "data"
_PRIVATE_PEM = _DATA / "vapid_private.pem"
_PUBLIC_TXT = _DATA / "vapid_appserverkey.txt"

# mailto: contact required by the Web Push spec for VAPID claims.
_VAPID_SUBJECT = "mailto:hello@choicely.app"

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
    _ensure_keys()
    return _PUBLIC_TXT.read_text().strip()


def config() -> dict:
    return {"enabled": _AVAILABLE, "public_key": public_key()}


def add_subscription(sub: dict) -> None:
    endpoint = sub.get("endpoint")
    if not endpoint:
        raise ValueError("subscription is missing an endpoint")
    models.save_push_subscription(endpoint, json.dumps(sub))


def remove_subscription(endpoint: str) -> None:
    models.delete_push_subscription(endpoint)


def _send(sub_row: dict, payload: dict) -> bool:
    """Push to one subscription. Returns False (and prunes it) if the
    endpoint is gone; raises for transient errors."""
    try:
        webpush(
            subscription_info=json.loads(sub_row["sub_json"]),
            data=json.dumps(payload),
            vapid_private_key=str(_PRIVATE_PEM),
            vapid_claims={"sub": _VAPID_SUBJECT},
            timeout=10,
        )
        return True
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):  # gone -- drop it
            models.delete_push_subscription(sub_row["endpoint"])
            return False
        raise


def broadcast(payload: dict) -> int:
    """Send `payload` to every stored subscription. Returns delivered count."""
    if not _AVAILABLE:
        return 0
    _ensure_keys()
    delivered = 0
    for row in models.list_push_subscriptions():
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
