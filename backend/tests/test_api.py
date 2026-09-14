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


def test_logged_decision_carries_friendly_advice(client):
    _make_profile(client)
    client.post("/decisions", json={"text": "should I skip breakfast"})  # not the first
    d = client.post("/decisions", json={"text": "should I text my old roommate"}).json()
    # advice is a Claude call generated in the background so logging never waits
    # on it -- it's null on the creation response itself...
    assert d["advice"] is None
    # ...but the TestClient awaits background tasks as part of the request, so
    # it's already there by the very next fetch.
    again = next(x for x in client.get("/decisions").json() if x["id"] == d["id"])
    assert isinstance(again["advice"], str) and len(again["advice"]) > 20


def test_compare_options_decision_carries_advice(client):
    _make_profile(client)
    d = client.post(
        "/decisions",
        json={"text": "the weekend trip", "options": ["go all weekend", "just saturday", "skip it"]},
    ).json()
    assert d["advice"] is None
    again = next(x for x in client.get("/decisions").json() if x["id"] == d["id"])
    assert isinstance(again["advice"], str) and len(again["advice"]) > 30


def test_recording_an_outcome_returns_a_reaction(client):
    _make_profile(client)
    client.post("/decisions", json={"text": "warm up the model"})  # not the first
    d = client.post("/decisions", json={"text": "should I go to the gym tonight"}).json()
    out = client.post(f"/decisions/{d['id']}/outcome", json={"outcome": "good"}).json()
    # generated in the background -- null on the outcome response itself
    assert out["outcome_reaction"] is None
    # survives a refetch, once the background task has run
    again = next(x for x in client.get("/decisions").json() if x["id"] == d["id"])
    assert isinstance(again["outcome_reaction"], str) and len(again["outcome_reaction"]) > 20
    # an un-resolved decision has none yet
    assert d.get("outcome_reaction") is None


def test_reaction_differs_by_outcome(client):
    _make_profile(client)
    client.post("/decisions", json={"text": "warm up"})
    good = client.post("/decisions", json={"text": "should I call my brother"}).json()
    regret = client.post("/decisions", json={"text": "should I stay up late finishing this"}).json()
    client.post(f"/decisions/{good['id']}/outcome", json={"outcome": "good"})
    client.post(f"/decisions/{regret['id']}/outcome", json={"outcome": "regret"})
    by_id = {x["id"]: x for x in client.get("/decisions").json()}
    assert by_id[good["id"]]["outcome_reaction"] != by_id[regret["id"]]["outcome_reaction"]


def test_auto_resolved_decision_has_no_advice(client):
    _make_profile(client)
    for _ in range(12):
        x = client.post("/decisions", json={"text": "should I skip breakfast"}).json()
        client.post(f"/decisions/{x['id']}/outcome", json={"outcome": "regret"})
    d = client.post("/decisions", json={"text": "should I skip breakfast again"}).json()
    assert d["auto_resolution"]
    assert d["advice"] is None


def test_action_taken_is_recorded_and_validated(client):
    _make_profile(client)
    d = client.post("/decisions", json={"text": "should I text her back"}).json()
    bad = client.post(f"/decisions/{d['id']}/outcome", json={"outcome": "good", "action_taken": "maybe"})
    assert bad.status_code == 400
    ok = client.post(f"/decisions/{d['id']}/outcome", json={"outcome": "good", "action_taken": "did"})
    assert ok.status_code == 200
    assert ok.json()["action_taken"] == "did"


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
