def _make_profile(client):
    client.post("/profile", json={"name": "T", "answers": [0.5] * 5, "personality_answers": {}})


def test_first_decision_is_cold_start(client):
    _make_profile(client)
    d = client.post("/decisions", json={"text": "should I skip lunch today"}).json()
    assert d["source"] == "cold_start"
    assert d["safety"] is None


def test_record_outcome_is_one_time(client):
    _make_profile(client)
    d = client.post("/decisions", json={"text": "should I skip lunch"}).json()
    assert client.post(f"/decisions/{d['id']}/outcome", json={"outcome": "good"}).status_code == 200
    assert client.post(f"/decisions/{d['id']}/outcome", json={"outcome": "regret"}).status_code == 409


def test_invalid_outcome_rejected(client):
    _make_profile(client)
    d = client.post("/decisions", json={"text": "x"}).json()
    assert client.post(f"/decisions/{d['id']}/outcome", json={"outcome": "meh"}).status_code == 400


def test_crisis_decision_carries_no_estimate(client):
    _make_profile(client)
    d = client.post("/decisions", json={"text": "i keep thinking about ending my life"}).json()
    assert d["source"] == "flagged_crisis"
    assert d["blended_regret_estimate"] is None
    assert d["outcome_due_at"] is None
    assert d["safety"]["tier"] == "crisis"


def test_compare_options_flow(client):
    _make_profile(client)
    d = client.post(
        "/decisions", json={"text": "weekend", "options": ["go all weekend", "just saturday", "skip it"]}
    ).json()
    assert d["source"] == "options"
    assert len(d["options"]["items"]) == 3
    # outcome without chosen_option is rejected
    assert client.post(f"/decisions/{d['id']}/outcome", json={"outcome": "good"}).status_code == 400
    ok = client.post(f"/decisions/{d['id']}/outcome", json={"outcome": "good", "chosen_option": 1})
    assert ok.status_code == 200
    assert ok.json()["chosen_option_idx"] == 1


def test_crisis_decision_excluded_from_mental_load(client):
    _make_profile(client)
    client.post("/decisions", json={"text": "i want to hurt myself"})
    load = client.get("/load").json()
    assert load["all_time"]["logged"] == 0


def test_community_stats_endpoint(client):
    stats = client.get("/community/stats").json()
    assert stats["total"] > 0


def test_contribute_grows_the_pool(client):
    _make_profile(client)
    before = client.get("/community/stats").json()["total"]
    d = client.post("/decisions", json={"text": "should I skip breakfast"}).json()
    client.post(f"/decisions/{d['id']}/outcome", json={"outcome": "regret", "contribute": True})
    after = client.get("/community/stats").json()
    assert after["total"] == before + 1
    assert after["contributed"] == 1
