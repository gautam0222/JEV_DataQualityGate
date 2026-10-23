import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import pytest
from jev_data_gate import analyse_rows, deterministic_action, offline_decision
from main import main

def test_sample_profiles_and_finds_bad_rows():
    data = pd.read_csv("data/sample_online_retail.csv", dtype={"InvoiceNo":"string", "StockCode":"string", "CustomerID":"string"})
    flagged, profile = analyse_rows(data)
    assert profile["row_count"] > 0
    assert profile["missing_invoice_no_rows"] >= 1
    assert profile["missing_stock_code_rows"] >= 1
    assert profile["invalid_invoice_date_rows"] >= 1
    assert profile["cancellation_rows"] >= 1
    assert profile["hard_invalid_rows"] >= 1
    assert "is_hard_invalid" in flagged.columns

def test_cancellation_negative_quantity_not_automatically_invalid():
    data = pd.DataFrame([{"InvoiceNo":"C123", "StockCode":"ABC", "Description":"return", "Quantity":-1, "InvoiceDate":"2010-12-01", "UnitPrice":2.0, "CustomerID":"123", "Country":"UK"}])
    flagged, profile = analyse_rows(data)
    assert profile["negative_quantity_cancellation_rows"] == 1
    assert profile["hard_invalid_rows"] == 0

def test_hard_rule_never_ignored_by_jev():
    profile = {"row_count": 100, "hard_invalid_rows": 1, "hard_invalid_pct": 1.0}
    jev = {"safe_to_promote_probability": 0.99, "issue_confidence": 0.99, "severity_index": 0}
    result = deterministic_action(profile, jev)
    assert result["action"] == "QUARANTINE_BAD_ROWS_AND_PROMOTE_REMAINDER"

def test_offline_output_labels_itself_not_jev():
    profile = {"missing_invoice_no_rows":0,"missing_stock_code_rows":0,"invalid_invoice_date_rows":0,"nonpositive_quantity_non_cancellation_rows":0,"negative_unit_price_rows":0,"quantity_missing_rows":0,"quantity_not_numeric_rows":0,"unit_price_missing_rows":0,"unit_price_not_numeric_rows":0,"exact_duplicate_repeat_rows":0,"missing_customer_id_rows":0,"missing_description_rows":0,"cancellation_rows":0,"hard_invalid_pct":0,"hard_invalid_rows":0,"row_count":2}
    decision = offline_decision(profile)
    assert decision["decision_source"] == "OFFLINE_RULES_NOT_JEV"


def test_missing_numeric_measure_is_quarantined():
    data = pd.DataFrame([{"InvoiceNo":"123", "StockCode":"ABC", "Description":"item", "Quantity":1, "InvoiceDate":"2010-12-01", "UnitPrice":None, "CustomerID":"123", "Country":"UK"}])
    flagged, profile = analyse_rows(data)
    assert profile["unit_price_missing_rows"] == 1
    assert profile["hard_invalid_rows"] == 1


def test_negative_rows_argument_is_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--rows", "-1"])
    with pytest.raises(SystemExit):
        main()
