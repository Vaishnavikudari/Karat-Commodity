"""
KARAT – Module 5: API Layer Tests.

Tests all required FastAPI endpoints with TestClient:
- GET /contracts?date=
- GET /curve?symbol=&date=
- GET /spread?pair=&from=&to=
- GET /signal?date=
- GET /backtest?period=test&cost_bps=&slippage_x=
- GET /calendar
- GET /quality
- GET /methodology
- GET /export/trades.csv
- GET /export/signals.csv
- Every response carries data_source: 'mcx' | 'sample'
- Validation & clear error messages on malformed inputs
"""

from __future__ import annotations

import csv
import io
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)


class TestApiEndpoints:
    def test_health_root(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project"] == "KARAT"
        assert data["data_source"] in ("mcx", "sample")

    def test_get_contracts(self):
        resp = client.get("/contracts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_source"] in ("mcx", "sample")
        assert "contracts" in data
        assert len(data["contracts"]) == 4

        # Check required fields on each contract
        for c in data["contracts"]:
            assert "symbol" in c
            assert "normalised_price" in c
            assert "premium_bps" in c
            assert "liquidity_status" in c
            assert c["liquidity_status"] in ("liquid", "thin", "unavailable")

    def test_get_contracts_invalid_date(self):
        resp = client.get("/contracts?date=invalid-date")
        assert resp.status_code == 400
        assert "Invalid date format" in resp.json()["detail"]

    def test_get_curve(self):
        resp = client.get("/curve?symbol=GOLDM")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_source"] in ("mcx", "sample")
        assert "curves" in data
        assert len(data["curves"]) > 0

    def test_get_spread(self):
        resp = client.get("/spread?pair=GOLDM-GOLDTEN&window=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_source"] in ("mcx", "sample")
        assert "summary" in data
        assert "chart" in data
        assert "terrain_points" in data
        assert data["summary"]["symbol_a"] == "GOLDM"
        assert data["summary"]["symbol_b"] == "GOLDTEN"

    def test_get_signal(self):
        resp = client.get("/signal?symbol_a=GOLDM&symbol_b=GOLDTEN")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_source"] in ("mcx", "sample")
        assert "signal" in data
        assert "state" in data
        assert data["signal"] in ("none", "Short GOLDM (Rich) / Long GOLDTEN (Cheap)", "Long GOLDM (Cheap) / Short GOLDTEN (Rich)")

    def test_get_backtest(self):
        resp = client.get("/backtest?period=unseen&cost_bps=0.5&slippage_x=2.0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_source"] in ("mcx", "sample")
        assert "unseen" in data
        assert "build" in data
        assert "verdict" in data
        assert "attribution" in data["unseen"]
        assert "headline_conclusion" in data["verdict"]

    def test_get_calendar(self):
        resp = client.get("/calendar")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_source"] in ("mcx", "sample")
        assert "events" in data
        assert "rules" in data
        assert "upcoming_roll_windows" in data

    def test_get_quality(self):
        resp = client.get("/quality")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_source"] in ("mcx", "sample")
        assert "total_rows" in data
        assert "date_range" in data
        assert "zero_volume_rows" in data
        assert "price_outliers_flagged" in data

    def test_get_methodology(self):
        resp = client.get("/methodology")
        assert resp.status_code == 200
        data = resp.json()
        assert "formula" in data
        assert "explanation" in data
        assert "cost_model" in data
        assert "strategy_rules" in data
        assert "disclaimer" in data
        assert "limitations" in data

    def test_export_trades_csv(self):
        resp = client.get("/export/trades.csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader)
        assert "entry_date" in header
        assert "exit_date" in header
        assert "gross_pnl_bps" in header

    def test_export_signals_csv(self):
        resp = client.get("/export/signals.csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader)
        assert "pair" in header
        assert "z_score" in header

    def test_export_normalised_csv(self):
        resp = client.get("/export/normalised.csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader)
        assert "NormalisedPrice" in header

    def test_export_spreads_csv(self):
        resp = client.get("/export/spreads.csv?pair=GOLDM_GOLDTEN")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader)
        assert "spread_rupees" in header
        assert "z_score" in header

    def test_all_endpoints_carry_data_status_and_source(self):
        """Step 1 Requirement: Every response carries data_status, last_verified_trading_date, and data_source."""
        endpoints = [
            "/health",
            "/contracts",
            "/spread?pair=GOLDM-GOLDTEN",
            "/signal?symbol_a=GOLDM&symbol_b=GOLDTEN",
            "/backtest",
            "/curve?symbol=GOLDM",
            "/curve/regimes",
            "/calendar",
            "/quality",
            "/methodology",
        ]
        for ep in endpoints:
            resp = client.get(ep)
            assert resp.status_code == 200, f"Endpoint {ep} failed with status {resp.status_code}"
            data = resp.json()
            assert "data_status" in data, f"{ep} missing data_status"
            assert data["data_status"] in ("real", "demo", "incomplete"), f"{ep} invalid data_status {data['data_status']}"
            assert "data_source" in data, f"{ep} missing data_source"
            assert data["data_source"] in ("mcx", "sample"), f"{ep} invalid data_source {data['data_source']}"
            assert "last_verified_trading_date" in data, f"{ep} missing last_verified_trading_date"
            assert data["last_verified_trading_date"] is not None, f"{ep} last_verified_trading_date is None"

