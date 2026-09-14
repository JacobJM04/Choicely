"""Each test gets its own empty SQLite file so state never leaks between them."""
import tempfile
from pathlib import Path

import pytest

from app import models


@pytest.fixture(autouse=True)
def no_live_llm(monkeypatch):
    """Keep the suite hermetic: force every Claude seam onto its heuristic
    fallback even when a real ANTHROPIC_API_KEY is configured (e.g. in
    backend/.env). Each module caches the key at import as a constant, so
    clearing os.environ isn't enough -- patch the constants directly."""
    from app import classifier, gametheory, llm, reflection, safety

    monkeypatch.setattr(llm, "_API_KEY", None, raising=False)
    monkeypatch.setattr(llm, "_DISABLED", True, raising=False)
    for mod in (classifier, gametheory, safety, reflection):
        monkeypatch.setattr(mod, "_ANTHROPIC_API_KEY", None, raising=False)


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    monkeypatch.setattr(models, "_DB_PATH", tmp)
    models.init_db()  # also seeds the community starter pool
    yield tmp
    try:
        tmp.unlink()
    except OSError:
        pass


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def profile():
    """A saved planner profile, so prior-adjustment paths are exercised."""
    from app import personality
    from app import profile as profile_mod

    score, label = profile_mod.score_survey([1, 1, 1, 0.5, 1])
    pers = personality.score_personality(
        {
            "risk_financial": 0.5,
            "risk_social": 1,
            "regret_orientation_1": "inaction-averse",
            "regret_orientation_2": "inaction-averse",
            "social_energy_leaning": "extrovert",
            "social_energy_stability": "fluctuating",
            "decisiveness_1": 1,
            "decisiveness_2": 1,
            "conflict_style": "avoidant",
            "stakes_sensitivity": "high",
        }
    )
    models.save_profile("Test", score, label, pers)
    return models.get_profile()
