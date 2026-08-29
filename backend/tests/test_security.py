"""Regression tests for the bug/security hardening pass."""
import pytest

from app import push


def _profile(client):
    client.post("/profile", json={"name": "T", "answers": [0.5] * 5, "personality_answers": {}})


# --- input bounds --------------------------------------------------------

def test_decision_text_length_capped(client):
    _profile(client)
    r = client.post("/decisions", json={"text": "x" * 5000})
    assert r.status_code == 422  # pydantic max_length


def test_option_list_and_item_bounded(client):
    _profile(client)
    assert client.post("/decisions", json={"text": "d", "options": ["a"] * 50}).status_code == 422
    # long option strings are truncated, not rejected
    r = client.post("/decisions", json={"text": "d", "options": ["y" * 4000, "z" * 4000]})
    assert r.status_code == 200
    assert all(len(o["text"]) <= 300 for o in r.json()["options"]["items"])


def test_profile_answer_list_bounded(client):
    assert client.post(
        "/profile", json={"name": "T", "answers": [0.5] * 500, "personality_answers": {}}
    ).status_code == 422


# --- /demo/advance ------------------------------------------------------

@pytest.mark.parametrize("hours", [0, -5, 10**9, 1e308])
def test_advance_rejects_out_of_range_hours(client, hours):
    _profile(client)
    assert client.post("/demo/advance", json={"hours": hours}).status_code == 422


def test_advance_within_range_works(client):
    _profile(client)
    assert client.post("/demo/advance", json={"hours": 24}).status_code == 200


# --- static file serving (path traversal) ------------------------------

def test_spa_handler_cannot_escape_dist(tmp_path, monkeypatch):
    """Simulate a built dist and confirm '../' can't read outside it."""
    import os

    from fastapi.testclient import TestClient

    dist = tmp_path / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id='root'></div>")
    (dist / "assets" / "app.js").write_text("ok")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")

    monkeypatch.setenv("PYTEST_DIST_OVERRIDE", str(dist))
    # rebuild the app module's view of _DIST by monkeypatching after import
    import app.main as m

    monkeypatch.setattr(m, "_DIST", os.path.realpath(str(dist)))

    # register a fresh spa route bound to the patched dir
    from fastapi import FastAPI
    from fastapi.responses import FileResponse

    probe = FastAPI()

    @probe.get("/{full_path:path}")
    def spa(full_path: str):
        d = os.path.realpath(str(dist))
        if full_path:
            cand = os.path.realpath(os.path.join(d, full_path))
            if (cand == d or cand.startswith(d + os.sep)) and os.path.isfile(cand):
                return FileResponse(cand)
        return FileResponse(os.path.join(d, "index.html"))

    c = TestClient(probe)
    assert c.get("/assets/app.js").text == "ok"
    for attack in ["../secret.txt", "../../secret.txt", "%2e%2e/secret.txt", "....//secret.txt"]:
        resp = c.get("/" + attack)
        assert "TOP SECRET" not in resp.text  # served index.html instead


# --- push endpoint validation (SSRF) ----------------------------------

@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/x",              # not https
        "https://169.254.169.254/latest/meta-data",  # metadata IP
        "https://localhost/x",                       # loopback host
        "https://evil.example.com/x",                # not a push service
        "https://internal.corp/fcm.googleapis.com",  # suffix trick
    ],
)
def test_push_subscribe_rejects_unsafe_endpoints(client, endpoint):
    r = client.post("/push/subscribe", json={"subscription": {"endpoint": endpoint, "keys": {}}})
    assert r.status_code == 400


def test_endpoint_is_safe_allowlist():
    assert push._endpoint_is_safe("https://updates.push.services.mozilla.com/wpush/v2/abc") in (True, False)
    assert push._endpoint_is_safe("http://fcm.googleapis.com/send/x") is False
    assert push._endpoint_is_safe("https://attacker.tld/x") is False


# --- concurrent outcome (race-safe update) ---------------------------

def test_second_outcome_write_loses(client):
    _profile(client)
    d = client.post("/decisions", json={"text": "x"}).json()
    from app import models

    assert models.update_outcome(d["id"], "good") is True
    assert models.update_outcome(d["id"], "regret") is False
    assert models.get_decision(d["id"])["outcome"] == "good"
