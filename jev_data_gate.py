"""Jev-assisted data-quality gate for an Online Retail batch.

Deterministic data checks identify/count concrete row defects. Jev classifies the
summary and gives a semantic recommendation. Hard rules always take precedence.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import pandas as pd

REQUIRED_COLUMNS = [
    "InvoiceNo", "StockCode", "Description", "Quantity",
    "InvoiceDate", "UnitPrice", "CustomerID", "Country",
]

CHOICE_CRITERIA = {
    "missing_critical_key": "One or more rows lack InvoiceNo or StockCode, so transaction identity/product identity may be lost.",
    "invalid_date": "One or more InvoiceDate values cannot be parsed, affecting time-based reporting or partitioning.",
    "invalid_measure": "A non-cancellation row has Quantity <= 0 or a row has a negative UnitPrice; business measures may be unreliable.",
    "cancellation_pattern": "Cancellation invoices (InvoiceNo begins with C) contain negative quantities; this can be a valid business event and should be handled explicitly.",
    "optional_attribute_missing": "CustomerID or Description is missing while the core transaction fields remain available; a join or descriptive report may be affected.",
    "duplicate_rows": "Exact duplicate records exist; review whether they are accidental duplicates or legitimate repeated line items before deduplicating.",
    "no_material_issue": "No material issue is visible in the supplied batch profile.",
    "other": "A different or mixed quality issue not adequately described by the other options.",
}

SEVERITY_LEVELS = [
    "Low - only optional descriptive fields are missing; core identifiers, dates and measures remain usable.",
    "Moderate - isolated suspicious records can be quarantined while most of the batch remains usable.",
    "High - repeated defects threaten joins, time-based analysis or transaction measures and require review.",
    "Critical - broad identifier, schema or timestamp failure means the batch cannot be interpreted reliably.",
]

def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    normalised = {str(c).strip().casefold(): c for c in df.columns}
    rename = {}
    for required in REQUIRED_COLUMNS:
        found = normalised.get(required.casefold())
        if found is not None and found != required:
            rename[found] = required
    return df.rename(columns=rename)

def analyse_rows(input_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return row-level flags and a compact JSON-safe batch profile."""
    df = _clean_columns(input_df)
    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_columns:
        raise ValueError(f"Dataset is missing required columns: {missing_columns}")
    # A stable RangeIndex makes row-wise flag access safe even if the input had duplicate index labels.
    df = df[REQUIRED_COLUMNS].copy().reset_index(drop=True)
    row_count = int(len(df))

    invoice = df["InvoiceNo"].astype("string").str.strip()
    stock = df["StockCode"].astype("string").str.strip()
    is_cancellation = invoice.str.upper().str.startswith("C", na=False).fillna(False)
    invoice_missing = invoice.isna() | invoice.eq("").fillna(False)
    stock_missing = stock.isna() | stock.eq("").fillna(False)

    parsed_date = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    date_invalid = parsed_date.isna()
    quantity = pd.to_numeric(df["Quantity"], errors="coerce")
    unit_price = pd.to_numeric(df["UnitPrice"], errors="coerce")
    quantity_missing = df["Quantity"].isna() | df["Quantity"].astype("string").str.strip().eq("").fillna(False)
    price_missing = df["UnitPrice"].isna() | df["UnitPrice"].astype("string").str.strip().eq("").fillna(False)
    quantity_type_invalid = ~quantity_missing & quantity.isna()
    price_type_invalid = ~price_missing & unit_price.isna()
    quantity_invalid = quantity_missing | quantity_type_invalid | ((quantity <= 0) & ~is_cancellation)
    negative_price = unit_price < 0
    exact_duplicate = df.duplicated(keep="first")

    row_flags = []
    for idx in df.index:
        flags = []
        if bool(invoice_missing.loc[idx]): flags.append("missing_invoice_no")
        if bool(stock_missing.loc[idx]): flags.append("missing_stock_code")
        if bool(date_invalid.loc[idx]): flags.append("invalid_invoice_date")
        if bool(quantity_missing.loc[idx]): flags.append("quantity_missing")
        if bool(quantity_type_invalid.loc[idx]): flags.append("quantity_not_numeric")
        if bool(price_missing.loc[idx]): flags.append("unit_price_missing")
        if bool(price_type_invalid.loc[idx]): flags.append("unit_price_not_numeric")
        if bool((quantity <= 0).loc[idx]) and not bool(is_cancellation.loc[idx]) and not bool(quantity_missing.loc[idx]) and not bool(quantity_type_invalid.loc[idx]): flags.append("nonpositive_quantity_non_cancellation")
        if bool(negative_price.loc[idx]): flags.append("negative_unit_price")
        row_flags.append(";".join(flags))
    df["quality_flags"] = row_flags
    df["is_cancellation"] = is_cancellation.astype(bool).values
    df["is_exact_duplicate_repeat"] = exact_duplicate.astype(bool).values
    df["parsed_invoice_date"] = parsed_date.astype("string")
    df["net_line_value"] = (quantity * unit_price).round(2)
    df["is_hard_invalid"] = df["quality_flags"].ne("")

    def count(series: pd.Series) -> int:
        return int(series.fillna(False).sum())
    pct = lambda n: round((100.0 * n / row_count), 3) if row_count else 0.0
    missing_customer = count(df["CustomerID"].isna() | df["CustomerID"].astype("string").str.strip().eq(""))
    missing_description = count(df["Description"].isna() | df["Description"].astype("string").str.strip().eq(""))
    hard_invalid_rows = count(df["is_hard_invalid"])
    profile = {
        "dataset": "UCI Online Retail (or schema-compatible included sample)",
        "row_count": row_count,
        "required_columns_present": REQUIRED_COLUMNS,
        "missing_required_columns": missing_columns,
        "missing_invoice_no_rows": count(invoice_missing),
        "missing_stock_code_rows": count(stock_missing),
        "invalid_invoice_date_rows": count(date_invalid),
        "quantity_missing_rows": count(quantity_missing),
        "quantity_not_numeric_rows": count(quantity_type_invalid),
        "unit_price_missing_rows": count(price_missing),
        "unit_price_not_numeric_rows": count(price_type_invalid),
        "nonpositive_quantity_non_cancellation_rows": count((quantity <= 0) & ~is_cancellation),
        "negative_unit_price_rows": count(negative_price),
        "zero_unit_price_rows": count(unit_price.eq(0)),
        "cancellation_rows": count(is_cancellation),
        "negative_quantity_cancellation_rows": count((quantity < 0) & is_cancellation),
        "exact_duplicate_repeat_rows": count(exact_duplicate),
        "missing_customer_id_rows": missing_customer,
        "missing_customer_id_pct": pct(missing_customer),
        "missing_description_rows": missing_description,
        "missing_description_pct": pct(missing_description),
        "hard_invalid_rows": hard_invalid_rows,
        "hard_invalid_pct": pct(hard_invalid_rows),
        "net_line_value_negative_rows": count((quantity * unit_price) < 0),
        "notes": [
            "Cancellation invoices commonly use an InvoiceNo beginning with C; negative cancellation quantities are not automatically treated as bad data.",
            "Missing CustomerID and Description are reported as optional-attribute gaps, not hard blockers by themselves.",
            "The exact business rules must be confirmed with the dataset owner before production use.",
        ],
    }
    return df, profile

def deterministic_action(profile: dict[str, Any], jev_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply safe Python rules. Jev is advisory and cannot overrule hard blockers."""
    jev_result = jev_result or {}
    hard_count = int(profile.get("hard_invalid_rows", 0))
    row_count = max(int(profile.get("row_count", 0)), 1)
    hard_pct = 100 * hard_count / row_count
    confidence = float(jev_result.get("issue_confidence") or 0.0)
    safe_prob = jev_result.get("safe_to_promote_probability")
    severity = jev_result.get("severity_index")
    reasons = []
    if hard_count > 0:
        reasons.append(f"{hard_count} row(s) failed deterministic integrity rules and will be isolated.")
    if hard_pct >= 2.0:
        reasons.append(f"Hard-invalid row rate ({hard_pct:.2f}%) is at or above the demo hold threshold of 2.00%.")
        return {"action": "HOLD_BATCH_FOR_REVIEW", "reasons": reasons or ["Hard-invalid rate exceeded threshold."], "hard_invalid_pct": round(hard_pct, 3)}
    if hard_count > 0:
        reasons.append("Only rows with explicit hard-rule failures are quarantined; clean rows can be considered separately.")
    if safe_prob is not None and float(safe_prob) < 0.70:
        reasons.append("Jev estimates low probability that the batch can be promoted without review (<0.70).")
        return {"action": "QUARANTINE_BAD_ROWS_AND_REVIEW_CLEAN_REMAINDER", "reasons": reasons, "hard_invalid_pct": round(hard_pct, 3)}
    if confidence and confidence < 0.65:
        reasons.append("Jev's issue classification confidence is below the demo threshold (0.65).")
        return {"action": "REVIEW_PROFILE", "reasons": reasons, "hard_invalid_pct": round(hard_pct, 3)}
    if severity is not None and int(severity) >= 2:
        reasons.append("Jev assigned high/critical severity; human review is required by demo policy.")
        return {"action": "REVIEW_PROFILE", "reasons": reasons, "hard_invalid_pct": round(hard_pct, 3)}
    if hard_count > 0:
        return {"action": "QUARANTINE_BAD_ROWS_AND_PROMOTE_REMAINDER", "reasons": reasons, "hard_invalid_pct": round(hard_pct, 3)}
    if not reasons:
        reasons.append("No deterministic blocker found; Jev signal is advisory and profile passed configured demo thresholds.")
    return {"action": "PROMOTE_TO_SILVER", "reasons": reasons, "hard_invalid_pct": round(hard_pct, 3)}

def offline_decision(profile: dict[str, Any]) -> dict[str, Any]:
    """No-key demo ONLY. This is deterministic stub logic, not a Jev inference."""
    # Priority is intentional: a critical identifier/date/measure defect should
    # not be hidden just because there are more optional-field gaps.
    categories = [
        ("missing_critical_key", profile["missing_invoice_no_rows"] + profile["missing_stock_code_rows"]),
        ("invalid_date", profile["invalid_invoice_date_rows"]),
        ("invalid_measure", profile["nonpositive_quantity_non_cancellation_rows"] + profile["negative_unit_price_rows"] + profile["quantity_missing_rows"] + profile["quantity_not_numeric_rows"] + profile["unit_price_missing_rows"] + profile["unit_price_not_numeric_rows"]),
        ("duplicate_rows", profile["exact_duplicate_repeat_rows"]),
        ("optional_attribute_missing", profile["missing_customer_id_rows"] + profile["missing_description_rows"]),
        ("cancellation_pattern", profile["cancellation_rows"]),
    ]
    issue = next((name for name, count in categories if count > 0), "no_material_issue")
    sev = 3 if profile["hard_invalid_pct"] >= 2 else 2 if profile["hard_invalid_rows"] else 1 if issue != "no_material_issue" else 0
    # Mark the source so these values cannot be mistaken for live Jev output.
    return {
        "decision_source": "OFFLINE_RULES_NOT_JEV",
        "model": "offline-demo-rules",
        "primary_issue": issue,
        "issue_confidence": None,
        "safe_to_promote_probability": None,
        "severity_index": sev,
        "severity_label": ["Low", "Moderate", "High", "Critical"][sev],
        "explanation": "Simulated result from deterministic demo rules. Set mode=live to call Jev.",
    }

def live_jev_decision(profile: dict[str, Any], model: str | None = None) -> dict[str, Any]:
    """Call TypeSafe Jev once with Choice, Noul, Score questions."""
    try:
        from typesafe_sdk import Choice, Noul, Score, TypeSafeClient
    except ImportError as exc:
        raise RuntimeError("Install SDK with `pip install -r requirements.txt` before using --mode live.") from exc
    model = model or os.getenv("JEV_MODEL", "jev-1.13.0")
    state = {
        "business_context": "A data engineer is deciding how to handle a batch before publishing retail order lines to the Silver layer.",
        "batch_profile": profile,
        "policy": {
            "deterministic_rules": "Python has already counted exact row-level integrity errors; do not recalculate arithmetic.",
            "cancellation_semantics": "An invoice number starting with C commonly indicates a cancellation. Negative quantity in such a row is not automatically corruption.",
            "optional_fields": "CustomerID and Description gaps can reduce descriptive/joins coverage but are not automatically a hard blocker.",
            "authority": "This is advisory triage only; Python rules and a human data owner control promotion.",
        },
    }
    questions = {
        "primary_issue": Choice(
            instructions="Choose the single most operationally important issue in this batch profile.",
            criteria=CHOICE_CRITERIA,
        ),
        "safe_to_promote": Noul(
            instructions="The Silver layer can receive the valid remainder of this batch without human review, after rows flagged by deterministic hard rules are isolated.",
        ),
        "severity": Score(
            instructions="Rate the impact of this batch's data-quality situation using these ordered descriptions. Use the most severe level supported by the evidence.",
            criteria=SEVERITY_LEVELS,
        ),
    }
    # The documented synchronous SDK quickstart uses a direct client instance.
    client = TypeSafeClient()
    response = client.system_one(state=state, questions=questions, model=model)
    choice_obj = response.choices["primary_issue"]
    noul_obj = response.nouls["safe_to_promote"]
    score_obj = response.scores["severity"]
    raw_score = getattr(score_obj, "score", 0)
    try:
        severity_index = max(0, min(len(SEVERITY_LEVELS)-1, int(round(float(raw_score)))))
    except (TypeError, ValueError):
        severity_index = 0
    return {
        "decision_source": "LIVE_JEV",
        "model": getattr(response, "model", model),
        "primary_issue": getattr(choice_obj, "choice", None),
        "issue_confidence": getattr(choice_obj, "confidence", None),
        "issue_probabilities": getattr(choice_obj, "probabilities", None),
        "safe_to_promote_probability": getattr(noul_obj, "noul", None),
        "severity_index": severity_index,
        "severity_label": ["Low", "Moderate", "High", "Critical"][severity_index],
        "severity_score_raw": raw_score,
        "usage": getattr(response, "usage", None),
        "explanation": "Jev classified the supplied batch profile; deterministic Python rules still decide row quarantine and final gate action.",
    }
