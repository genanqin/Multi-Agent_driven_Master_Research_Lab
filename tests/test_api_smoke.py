import os
from collections import defaultdict

os.environ["ENABLE_AKSHARE"] = "false"
os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient

from app.config import get_settings

get_settings.cache_clear()

from app.main import app


client = TestClient(app)


def test_health_does_not_expose_secrets():
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["llm_enabled"] is False
    assert "llm_api_key" not in payload
    assert "api_key" not in payload


def test_analyze_mock_pipeline_returns_portfolio():
    response = client.post(
        "/api/analyze",
        json={"symbols": ["600519", "000001"], "capital": 1_000_000},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["request"]["symbols"]) == 2
    assert len(payload["master_opinions"]) == 12
    assert len(payload["portfolio"]) == 2
    assert "数据源" in payload["summary"]


def test_maad_debate_uses_at_most_three_masters_per_symbol():
    response = client.post(
        "/api/analyze",
        json={"symbols": ["600519", "000001", "300750"], "capital": 1_000_000},
    )

    assert response.status_code == 200
    payload = response.json()
    speakers_by_symbol = defaultdict(set)
    for item in payload["debate"]:
        speakers_by_symbol[item["target_symbol"]].add(item["speaker"])

    assert speakers_by_symbol
    assert all(len(speakers) <= 3 for speakers in speakers_by_symbol.values())
