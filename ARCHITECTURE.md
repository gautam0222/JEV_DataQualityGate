# How the data-quality gate works

The project separates facts about records from advisory interpretation. That
means a model response cannot silently override a known row-level defect.

```text
CSV or UCI workbook
       |
       v
analyse_rows() -----> flagged records + compact batch profile
       |                            |
       |                            +--> offline_decision() OR live_jev_decision()
       |                                                |
       +--------------------------> deterministic_action()
                                                     |
                                                     v
                         JSON report, decision CSV, Silver candidate, quarantine CSV
```

## Files and responsibilities

- `main.py` is the command-line coordinator. It chooses the input, calls the
  analysis and decision functions, and writes four outputs.
- `jev_data_gate.py` contains the business logic. `analyse_rows()` standardizes
  columns and identifies missing identifiers, invalid dates, invalid measures,
  cancellation rows, and exact duplicate repeats. `deterministic_action()`
  applies the final policy: a hard-invalid rate of 2% or more holds the batch.
- `offline_decision()` is a predictable no-key demonstration. Its return value
  is labelled `OFFLINE_RULES_NOT_JEV` so it cannot be confused with model
  output.
- `live_jev_decision()` sends only the compact profile to Jev. It asks Jev for
  the main issue, a promotion probability, and severity. That response is
  advisory; the Python policy still controls the final action.
- `download_dataset.py` obtains the original UCI workbook only when requested.
- `tests/` covers the core profiling and policy behaviour.

## Data flow rules

1. Missing `InvoiceNo` or `StockCode`, invalid dates, missing/non-numeric
   measures, non-positive non-cancellation quantities, and negative prices are
   hard-invalid and go to quarantine.
2. A cancellation invoice begins with `C`. Its negative quantity is retained as
   a valid business event, unless another hard rule also fails.
3. Missing `CustomerID` and `Description` are reported but do not alone
   quarantine a row.
4. Exact duplicates are reported for review, not automatically removed.

The 2% threshold is a demonstration default, not a universal rule. Replace it
with a threshold agreed by the data owner before using this in production.
