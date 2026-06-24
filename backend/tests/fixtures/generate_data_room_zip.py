"""Generate data_room.zip fixture for multi-document ingestion tests."""

import zipfile
from pathlib import Path

FIXTURES = Path(__file__).parent
FILES = [
    "sample_gl.csv",
    "sample_ar_aging.csv",
    "sample_ap_aging.csv",
    "sample_projections.csv",
]

out = FIXTURES / "data_room.zip"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for name in FILES:
        path = FIXTURES / name
        if path.exists():
            zf.write(path, arcname=name)

print(f"Written {out}")
