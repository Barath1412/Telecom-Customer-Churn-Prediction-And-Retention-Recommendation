"""
Unit tests for customer persistence, queue search across cohorts, and action reset.
"""
from __future__ import annotations

import io
import json
import shutil
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import population, detail, queue_state
from app.settings import ML_ROOT


@pytest.fixture(autouse=True)
def preserve_artifacts():
    """Ensure artifacts modified during batch tests are restored after tests."""
    q_csv = ML_ROOT / "artifacts" / "queue_full.csv"
    up_jsonl = ML_ROOT / "artifacts" / "uploaded_customers.jsonl"
    up_json = ML_ROOT / "artifacts" / "uploaded_customers.json"
    up_csv = ML_ROOT / "artifacts" / "uploaded_customers.csv"
    actions_jsonl = ML_ROOT / "artifacts" / "actions" / "actions.jsonl"

    q_csv_backup = q_csv.read_text(encoding="utf-8") if q_csv.exists() else None
    up_jsonl_backup = up_jsonl.read_text(encoding="utf-8") if up_jsonl.exists() else None
    up_json_backup = up_json.read_text(encoding="utf-8") if up_json.exists() else None
    up_csv_backup = up_csv.read_text(encoding="utf-8") if up_csv.exists() else None
    actions_backup = actions_jsonl.read_text(encoding="utf-8") if actions_jsonl.exists() else None

    yield

    if q_csv_backup is not None:
        q_csv.write_text(q_csv_backup, encoding="utf-8")
    if up_jsonl_backup is not None:
        up_jsonl.write_text(up_jsonl_backup, encoding="utf-8")
    if up_json_backup is not None:
        up_json.write_text(up_json_backup, encoding="utf-8")
    if up_csv_backup is not None:
        up_csv.write_text(up_csv_backup, encoding="utf-8")
    if actions_backup is not None:
        actions_jsonl.write_text(actions_backup, encoding="utf-8")

    # Reset in-memory cache
    population._records.clear()
    population.load()
    detail._queue_full_df = None
    detail._queue_full_by_id = {}
    detail._recommended_ranks = {}
    queue_state.state = queue_state.init_state()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_synthesize_record_from_queue_row():
    """Verify that a customer in queue without a raw survey profile is synthesized correctly."""
    row = {
        "customer_id": "TEST-SYNTH-9999",
        "monthly_charges": 110.0,
        "tenure_months": 3,
        "cltv": 6500.0,
        "levers": "NO_TECH_SUPPORT|NO_ONLINE_SECURITY|FIBER_PREMIUM|MONTH_TO_MONTH",
        "offer_id": "OFF-BUNDLE-ALL",
        "ev": 720.0,
        "p_churn": 0.95,
        "status": "recommended",
    }
    synth = population.synthesize_record_from_queue_row("TEST-SYNTH-9999", row)
    assert synth["customer_id"] == "TEST-SYNTH-9999"
    assert synth["cltv"] == 6500.0
    assert synth["customer"]["Monthly Charges"] == 110.0
    assert synth["customer"]["Tenure Months"] == 3
    assert synth["customer"]["Internet Service"] == "Fiber optic"
    assert synth["customer"]["Tech Support"] == "No"
    assert synth["customer"]["Online Security"] == "No"
    assert synth["customer"]["Contract"] == "Month-to-month"


def test_customer_detail_with_synthesized_profile(client):
    """Verify that get_customer_detail works flawlessly for synthesized profiles."""
    cid = "TEST-SYNTH-DETAIL-001"
    row = {
        "customer_id": cid,
        "monthly_charges": 95.0,
        "tenure_months": 2,
        "cltv": 5800.0,
        "levers": "NO_TECH_SUPPORT|FIBER_PREMIUM|MONTH_TO_MONTH",
        "offer_id": "OFF-BUNDLE-ALL",
        "ev": 500.0,
        "p_churn": 0.85,
        "status": "recommended",
    }
    synth = population.synthesize_record_from_queue_row(cid, row)
    population.add_customer(cid, synth["customer"], synth["cltv"])
    population.save_customer_records([synth])

    d = detail.get_customer_detail(cid)
    assert d["customer_id"] == cid
    assert d["risk"]["p_churn"] > 0.0
    assert d["value"]["cltv"] == 5800.0


def test_queue_search_across_pages(client):
    """Verify that searching for a customer on Page 3 (or any page) returns them on Page 1."""
    # 1240-KNSEZ is a known customer in queue (~item 118 on page 3)
    r = client.get("/api/queue?status=pending&search=1240-KNSEZ")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["customer_id"] == "1240-KNSEZ"
    assert data["items"][0]["rank"] is not None

    # Partial substring search
    r_part = client.get("/api/queue?status=pending&search=KNSEZ")
    assert r_part.status_code == 200
    data_part = r_part.json()
    assert any(item["customer_id"] == "1240-KNSEZ" for item in data_part["items"])


def test_queue_search_across_all_cohorts(client):
    """Verify that search works consistently across different status categories."""
    for cat in ["all_scored", "no_action_needed", "review_no_profitable_offer"]:
        r = client.get(f"/api/queue?status={cat}&page_size=5")
        assert r.status_code == 200
        cat_data = r.json()
        if cat_data["items"]:
            target_cid = cat_data["items"][0]["customer_id"]
            # Search for this ID
            r_search = client.get(f"/api/queue?status={cat}&search={target_cid}")
            assert r_search.status_code == 200
            s_data = r_search.json()
            assert len(s_data["items"]) >= 1
            assert s_data["items"][0]["customer_id"] == target_cid


def test_reset_actions_endpoint(client):
    """Verify that POST /api/actions/reset restores all decisions to pending."""
    # Action a customer first
    cid = "0295-PPHDO"
    r_act = client.post(
        f"/api/customers/{cid}/action",
        json={"action": "approve", "actor": "agent_test"},
    )
    assert r_act.status_code == 200

    # Verify they are now in approved
    r_app = client.get("/api/queue?status=approved")
    assert any(item["customer_id"] == cid for item in r_app.json()["items"])

    # Reset actions
    r_reset = client.post("/api/actions/reset")
    assert r_reset.status_code == 200
    res = r_reset.json()
    assert res["status"] == "reset"
    assert res["approved_total"] == 0

    # Verify they are back in pending
    r_pend = client.get("/api/queue?status=pending&search=0295-PPHDO")
    assert r_pend.status_code == 200
    assert len(r_pend.json()["items"]) == 1


def test_upload_queue_persists_to_csv_and_updates_summary(client):
    """Verify that uploading a customer batch updates queue_full.csv, uploaded_customers.csv, and summary."""
    csv_content = (
        "CustomerID,Gender,Senior Citizen,Partner,Dependents,Tenure Months,Phone Service,Multiple Lines,"
        "Internet Service,Online Security,Online Backup,Device Protection,Tech Support,Streaming TV,"
        "Streaming Movies,Contract,Paperless Billing,Payment Method,Monthly Charges,Total Charges,CLTV\n"
        "UP-TEST-99999,Male,0,No,No,1,Yes,No,Fiber optic,No,No,No,No,Yes,Yes,Month-to-month,Yes,Electronic check,105.5,105.5,6200.0\n"
    )
    r_up = client.post(
        "/api/queue/upload",
        files={"file": ("test_upload.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r_up.status_code == 200
    up_res = r_up.json()
    assert up_res["status"] == "success"
    assert up_res["total_uploaded"] == 1

    # Verify queue_full.csv on disk contains the customer
    q_csv = ML_ROOT / "artifacts" / "queue_full.csv"
    q_df = pd.read_csv(q_csv)
    assert "UP-TEST-99999" in q_df["customer_id"].values

    # Verify uploaded_customers.csv on disk contains the customer
    up_csv = ML_ROOT / "artifacts" / "uploaded_customers.csv"
    if up_csv.exists():
        up_df = pd.read_csv(up_csv)
        assert "UP-TEST-99999" in up_df["customer_id"].values

    # Verify uploaded_customers.jsonl contains the customer
    up_jsonl = ML_ROOT / "artifacts" / "uploaded_customers.jsonl"
    assert "UP-TEST-99999" in up_jsonl.read_text(encoding="utf-8")

    # Verify /api/queue returns the customer
    r_q = client.get("/api/queue?status=pending&search=UP-TEST-99999")
    assert r_q.status_code == 200
    assert len(r_q.json()["items"]) == 1
    assert r_q.json()["items"][0]["customer_id"] == "UP-TEST-99999"

    # Verify /api/summary reflects dynamic counts
    r_sum = client.get("/api/summary")
    assert r_sum.status_code == 200
    sum_data = r_sum.json()
    assert sum_data["funnel"]["scored"] == len(q_df)

