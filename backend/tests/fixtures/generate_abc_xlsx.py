"""Generate ABC_Subsidiary.xlsx from sample_gl.csv for Excel parity tests."""

import csv
from pathlib import Path

try:
    from openpyxl import Workbook
except ImportError:
    raise SystemExit("openpyxl required")

fixtures = Path(__file__).parent
csv_path = fixtures / "sample_gl.csv"
xlsx_path = fixtures / "ABC_Subsidiary.xlsx"

with open(csv_path, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    fieldnames = reader.fieldnames

wb = Workbook()
ws = wb.active
ws.append(fieldnames)
for row in rows:
    ws.append([row.get(h, "") for h in fieldnames])
wb.save(xlsx_path)
print(f"Written {len(rows)} rows to {xlsx_path}")
