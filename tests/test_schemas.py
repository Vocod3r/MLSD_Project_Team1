"""Unit tests for FNOL schema validation (F1, F2, D1)."""

import datetime as dt
import pytest
from app.schemas import FNOL, validate_fnol


@pytest.fixture
def valid_fnol_payload():
    today = dt.date.today()
    return {
        "policy_number": "POL-12345678",
        "insured_name": "Aditi Sharma",
        "vehicle_registration": "KA-01-MJ-5050",
        "channel": "app",
        "date_of_loss": str(today - dt.timedelta(days=2)),
        "date_of_report": str(today),
        "place_of_loss": "Bangalore, Karnataka",
        "estimated_loss_inr": 25000.0,
        "description": "Vehicle hit a tree branch during heavy rain. Front windscreen cracked.",
        "garage_name": "Apex Motors Bangalore",
        "fir_number": None,
        "cashless_requested": True,
        "third_party_involved": False,
        "injuries": False,
        "police_report_filed": False,
    }


def test_valid_payload_passes(valid_fnol_payload):
    clean, errors = validate_fnol(valid_fnol_payload)
    assert errors == []
    assert clean is not None
    assert clean["vehicle_registration"] == "KA-01-MJ-5050"


def test_bharat_series_registration(valid_fnol_payload):
    valid_fnol_payload["vehicle_registration"] = "22-BH-1234-AA"
    clean, errors = validate_fnol(valid_fnol_payload)
    assert errors == []
    assert clean["vehicle_registration"] == "22-BH-1234-AA"


def test_invalid_registration_rejected(valid_fnol_payload):
    valid_fnol_payload["vehicle_registration"] = "INVALID_PLATE_123"
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    fields = [e["field"] for e in errors]
    assert "vehicle_registration" in fields


@pytest.mark.parametrize("channel", ["web", "app", "call_centre"])
def test_valid_channels(valid_fnol_payload, channel):
    valid_fnol_payload["channel"] = channel
    clean, errors = validate_fnol(valid_fnol_payload)
    assert errors == []
    assert clean["channel"] == channel


def test_invalid_channel(valid_fnol_payload):
    valid_fnol_payload["channel"] = "whatsapp"
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    assert any(e["field"] == "channel" for e in errors)


def test_negative_loss_estimate_rejected(valid_fnol_payload):
    valid_fnol_payload["estimated_loss_inr"] = -100.0
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    assert any(e["field"] == "estimated_loss_inr" for e in errors)


def test_excessive_loss_estimate_rejected(valid_fnol_payload):
    valid_fnol_payload["estimated_loss_inr"] = 60_000_000.0  # 6 crore > 5 crore limit
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    assert any(e["field"] == "estimated_loss_inr" for e in errors)


def test_future_date_of_loss_rejected(valid_fnol_payload):
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    valid_fnol_payload["date_of_loss"] = str(tomorrow)
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    assert any(e["field"] == "date_of_loss" for e in errors)


def test_report_before_loss_rejected(valid_fnol_payload):
    today = dt.date.today()
    valid_fnol_payload["date_of_loss"] = str(today)
    valid_fnol_payload["date_of_report"] = str(today - dt.timedelta(days=2))
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    assert any(e["field"] == "date_of_report" and "on or after" in e["message"] for e in errors)


def test_late_report_over_365_days_rejected(valid_fnol_payload):
    today = dt.date.today()
    valid_fnol_payload["date_of_loss"] = str(today - dt.timedelta(days=400))
    valid_fnol_payload["date_of_report"] = str(today)
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    assert any(e["field"] == "date_of_report" and "365 days" in e["message"] for e in errors)


def test_cashless_without_garage_rejected(valid_fnol_payload):
    valid_fnol_payload["cashless_requested"] = True
    valid_fnol_payload["garage_name"] = None
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    assert any(e["field"] == "garage_name" for e in errors)


def test_fir_required_when_police_report_filed(valid_fnol_payload):
    valid_fnol_payload["police_report_filed"] = True
    valid_fnol_payload["fir_number"] = None
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    assert any(e["field"] == "fir_number" for e in errors)


def test_extra_fields_forbidden(valid_fnol_payload):
    valid_fnol_payload["unauthorized_hack_field"] = "malicious_data"
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    assert any(e["field"] == "unauthorized_hack_field" for e in errors)


def test_short_description_rejected(valid_fnol_payload):
    valid_fnol_payload["description"] = "Too short"
    clean, errors = validate_fnol(valid_fnol_payload)
    assert clean is None
    assert any(e["field"] == "description" for e in errors)
