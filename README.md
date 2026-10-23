# Jev Data Quality Gate (developer learning project)

A small Python project that shows how Jev can make a **semantic decision about a data-quality profile** before an e-commerce batch moves from Bronze to Silver. It uses the UCI Online Retail dataset (541,909 transaction rows, 2010-2011) when downloaded, and includes a tiny schema-compatible fixture for a zero-download smoke test.

## What this project does

1. Reads a batch from a CSV fixture or the real UCI Online Retail Excel workbook.
2. Uses pandas for exact checks and row-level flags (missing transaction/product identifiers, invalid dates/measures, exact duplicate repeats).
3. Summarises the batch into a compact profile.
4. In `--mode live`, sends the profile to Jev using `typesafe-sdk`, with one Choice, one Noul and one Score question.
5. Applies deterministic Python gate rules. Jev is advisory: it cannot override row-level hard blockers.
6. Writes `batch_report.json`, `decision_summary.csv`, `silver_candidate.csv`, and `quarantine.csv`.

This project does not compare Jev with another LLM. It is a single-model learning demo.

## 1. Requirements

- Python 3.10-3.13 (Python 3.12 is pinned for reproducible local and CI runs)
- `uv` (recommended; a Rust-based Python package and environment manager)
- Internet access only when downloading the UCI workbook or making live Jev calls
- A TypeSafe API key for real Jev inference (offline mode needs no key)

## 2. Setup with uv (Windows PowerShell)

```powershell
cd jev_data_gate_project
uv sync
```

This creates `.venv`, installs the locked dependencies, and uses Python 3.12.
Run commands without activation:

```powershell
uv run python main.py --source sample --mode offline
uv run pytest
```

To activate the environment instead, run `.\.venv\Scripts\Activate.ps1` on
Windows or `source .venv/bin/activate` on macOS/Linux. `requirements.txt`
remains available for pip users; `pyproject.toml` and `uv.lock` are the source
of truth for uv.

## 3. Zero-key smoke run

```powershell
python main.py --source sample --mode offline
pytest -q
```

The offline result is **rule-based simulation**, not a Jev prediction. It validates the data pipeline and output writing only.

## 4. Run on the real public dataset

Download the original workbook from UCI (the script downloads the upstream ZIP and extracts the workbook):

```powershell
python download_dataset.py
```

Try a 5,000-row batch first; `--rows 0` means all available rows:

```powershell
python main.py --source uci --rows 5000 --mode offline
```

The official dataset includes cancellations; an InvoiceNo beginning with `C` indicates a cancellation. A negative quantity on a cancellation is not automatically treated as bad data. The dataset can contain missing CustomerID or Description values, which are profiled as optional attribute gaps rather than automatically quarantined.

## 5. Run a real Jev inference

Create an API key in the TypeSafe console, then set it in the current PowerShell session (don't commit it):

```powershell
$env:TYPESAFE_API_KEY = "YOUR_KEY_HERE"
$env:JEV_MODEL = "jev-1.13.0"
python main.py --source uci --rows 5000 --mode live
```

macOS/Linux:

```bash
export TYPESAFE_API_KEY="YOUR_KEY_HERE"
export JEV_MODEL="jev-1.13.0"
python main.py --source uci --rows 5000 --mode live
```

You can also try `--source sample --mode live` to avoid the large data download. In live mode the code uses `TypeSafeClient.system_one()` and sends a compact JSON-safe profile instead of sending every transaction row.

## 6. Outputs

- `outputs/batch_report.json`: complete batch profile, Jev response fields and gate reasoning.
- `outputs/decision_summary.csv`: one-row summary suitable for Excel/Power BI.
- `outputs/silver_candidate.csv`: records that passed the deterministic row-level rules.
- `outputs/quarantine.csv`: records with explicit hard-rule flags.

## 7. What each code file does

- `main.py`: command-line entrypoint and orchestration.
- `download_dataset.py`: downloads the official UCI archive only when requested.
- `jev_data_gate.py`: required-column validation, row-level quality flags, batch profiling, Jev question definitions, offline mode and the deterministic policy.
- `tests/test_jev_data_gate.py`: tests the profiling behavior, cancellation handling, hard-rule precedence and offline labelling.
- `data/sample_online_retail.csv`: a small educational fixture with ordinary, cancellation, missing-field and intentionally malformed examples. This file is not the original UCI source data.

## 8. How Jev questions map to the use case

- **Choice:** select the most operationally important issue in the batch profile (missing key, invalid date, invalid measure, cancellation pattern, optional attribute gaps, duplicate rows, no material issue, other).
- **Noul:** estimate whether the valid remainder can be promoted after deterministic hard-error rows are isolated.
- **Score:** assign Low / Moderate / High / Critical using explicit descriptions.

Jev handles semantic classification. Python handles counts, arithmetic, parsing, row isolation, thresholds, logging and the final action.

## 9. Important engineering caveats

- An API response is not proof of correctness. Review reports and test on representative data.
- Do not send confidential customer data to an external API without approval. This sample dataset is public; production records may not be.
- The demo threshold (2% hard-invalid rows, confidence 0.65, Noul probability 0.70) is illustrative. Calibrate thresholds to your data owners' risk tolerance.
- This gate uses a small batch and is not a production data platform: it does not include a scheduler, warehouse writes, idempotent batch registry, access controls or monitoring alerts. Add those only after the basic logic is understood.
- Cancellation semantics and the definition of a duplicate should be confirmed with the data owner. Exact duplicate rows are flagged, not automatically dropped.
- Pin the model version when repeatability matters, and rerun labelled validations after any version change.

## 10. Provenance

`PROVENANCE.md` explains the project-specific design, the external libraries,
and the attribution that must remain with the UCI dataset. It is intentionally
not a claim that an automated detector can prove authorship or originality.

## 11. Architecture

See `ARCHITECTURE.md` for a concise walkthrough of the code path, decisions,
and row-handling rules.

## Dataset attribution

Chen, D. (2015). *Online Retail*. UCI Machine Learning Repository. DOI: https://doi.org/10.24432/C5BW33. Licensed under Creative Commons Attribution 4.0 (CC BY 4.0). Dataset page: https://archive.ics.uci.edu/dataset/352/online+retail

## Jev API reference

TypeSafe AI API reference: https://docs.typesafe.ai/api (verify current endpoint/schema and SDK release before deployment). Official Python SDK: https://github.com/typesafe-ai/typesafe-sdk-python

## Small Jev learning reference

For the generic primitives and confidence-gated routing patterns this mini-project builds on, see the small independent examples repository: https://github.com/robdelaney007/jev-examples. This project is a separate data-engineering adaptation for the UCI retail dataset; it is not that repository's complete application.
