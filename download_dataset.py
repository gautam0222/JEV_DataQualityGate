"""Download the publicly available UCI Online Retail dataset (CC BY 4.0).
The original workbook is not redistributed in this repository.
"""
from pathlib import Path
import urllib.request
import zipfile

DATA_DIR = Path(__file__).parent / "data" / "raw"
ZIP_PATH = DATA_DIR / "online_retail.zip"
XLSX_PATH = DATA_DIR / "Online Retail.xlsx"
URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if XLSX_PATH.exists():
        print(f"Dataset already exists: {XLSX_PATH}")
        return
    print("Downloading UCI Online Retail dataset. This is about 23 MB.")
    request = urllib.request.Request(URL, headers={"User-Agent": "JevDataQualityGate/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response, ZIP_PATH.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except Exception as exc:
        ZIP_PATH.unlink(missing_ok=True)
        raise RuntimeError(
            "Download failed. Open https://archive.ics.uci.edu/dataset/352/online+retail "
            "in a browser, download Online Retail.xlsx, and place it at data/raw/Online Retail.xlsx."
        ) from exc
    try:
        with zipfile.ZipFile(ZIP_PATH) as archive:
            candidates = [n for n in archive.namelist() if n.lower().endswith(".xlsx")]
            if not candidates:
                raise RuntimeError(f"No .xlsx workbook found in archive: {archive.namelist()}")
            member = candidates[0]
            with archive.open(member) as src, XLSX_PATH.open("wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
    finally:
        ZIP_PATH.unlink(missing_ok=True)
    print(f"Saved workbook: {XLSX_PATH}")
    print("Dataset attribution: Chen (2015), UCI Online Retail, DOI 10.24432/C5BW33, CC BY 4.0.")

if __name__ == "__main__":
    main()
