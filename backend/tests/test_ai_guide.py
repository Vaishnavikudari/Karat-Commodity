"""
Tests for KARAT AI Guide endpoint and domain reasoning intelligence.
"""

from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)


def test_ai_chat_overview_purity_math():
    payload = {
        "message": "Why is GOLDM 995 fineness while GOLDTEN is 999?",
        "context": {
            "active_tab": "overview",
            "data_source": "sample",
            "reference_symbol": "GOLDTEN"
        }
    }
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert "mode" in data
    assert data["context_tab"] == "overview"
    assert "995" in data["reply"]
    assert "999" in data["reply"]
    assert "Normalisation" in data["reply"] or "P_normalised" in data["reply"]
    assert len(data["suggested_questions"]) > 0


def test_ai_chat_spread_lab_zscore():
    payload = {
        "message": "What does a Z-Score of 2.0 mean?",
        "context": {
            "active_tab": "spreads",
            "selected_pair": "GOLDM_GOLDTEN"
        }
    }
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "2.0" in data["reply"]
    assert "Z-Score" in data["reply"] or "Mean Reversion" in data["reply"]
    assert data["context_tab"] == "spreads"


def test_ai_chat_cost_hurdle():
    payload = {
        "message": "Why do we use a 4-leg cost model?",
        "context": {
            "active_tab": "backtest",
            "cost_bps": 2.5
        }
    }
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "4-Leg" in data["reply"]
    assert "10.0" in data["reply"]  # 4 * 2.5 bps = 10.0 bps


def test_ai_chat_calendar_tender_rule():
    payload = {
        "message": "Explain the 5-day tender rule",
        "context": {
            "active_tab": "calendar"
        }
    }
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "5-Day Tender" in data["reply"] or "tender" in data["reply"].lower()


def test_ai_chat_page_overview_context_aware():
    for tab in ["overview", "spreads", "backtest", "calendar", "methodology"]:
        payload = {
            "message": "Explain this page in plain English",
            "context": {"active_tab": tab}
        }
        resp = client.post("/api/chat", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["context_tab"] == tab
        assert len(data["reply"]) > 50


def test_ai_chat_speed_and_spread_inquiry():
    payload = {
        "message": "what does the current speed tells u about it",
        "context": {
            "active_tab": "spreads",
            "selected_pair": "GOLDM_GOLDTEN",
            "cost_bps": 2.5
        }
    }
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    reply = data["reply"]
    # Checks live numbers and concepts
    assert "Current Spread & Speed of Reversion" in reply
    assert "GOLDM" in reply and "GOLDTEN" in reply
    assert "10.0 bps" in reply  # 4 * 2.5 hurdle
    assert "5.5 bps" in reply or "Costs would eat the gap" in reply
    assert "half-life" in reply.lower()


def test_ai_chat_hypothetical_and_creative_questions():
    scenarios = [
        ("what if an asteroid made of solid gold is captured in earth orbit", ["Asteroid", "Scarcity Collapse"]),
        ("what happens if gold price hits 200000", ["2,00,000", "Notional Value"]),
        ("what happens if dogs take over Wall Street", ["Hypothetical Scenario", "Arbitrage"]),
        ("how does quantum computing affect arbitrage", ["Quantum Computing", "Combinatorial"])
    ]
    for prompt, expected_phrases in scenarios:
        resp = client.post("/api/chat", json={"message": prompt, "context": {}})
        assert resp.status_code == 200
        data = resp.json()
        for phrase in expected_phrases:
            assert phrase.lower() in data["reply"].lower()

