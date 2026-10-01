"""
content_io.py

All filesystem/YAML I/O for the resume builder: where content.yaml and the
output directory live, and how to load/save the content data. Nothing in
here touches Streamlit or the app's data model/logic — just reading and
writing files.
"""

from pathlib import Path

import yaml

BASE_DIR = Path(__file__).parent
CONTENT_PATH = BASE_DIR / "content.yaml"
OUTPUT_DIR = BASE_DIR / "output"


def load_data():
    """Load content.yaml into a plain dict."""
    with open(CONTENT_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_data(data):
    """Persist the (possibly edited) data dict back to content.yaml."""
    with open(CONTENT_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=1000)