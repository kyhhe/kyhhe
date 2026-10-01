"""
content_io.py

All filesystem/YAML I/O for the resume builder: where content.yaml and the
output directory live, and how to load/save the content data. Nothing in
here touches Streamlit or the app's data model/logic — just reading and
writing files.
"""

from pathlib import Path
import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml

BASE_DIR = Path(__file__).parent
CONTENT_PATH = BASE_DIR / "content.yaml"
OUTPUT_DIR = BASE_DIR / "output"


def _setting(name, default=None):
    """Read deployment configuration from env vars or Streamlit secrets."""
    value = os.environ.get(name)
    if value is not None:
        return value
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:
        return default


def _load_remote_data(owner, repo, token, branch, path):
    api_path = quote(path, safe="/")
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{api_path}?ref={quote(branch)}"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(
            f"Could not fetch {path} from {owner}/{repo} (GitHub returned HTTP {error.code}). "
            "Check the repository name, branch, file path, and token access."
        ) from error
    except URLError as error:
        raise RuntimeError(f"Could not connect to GitHub to load {path}: {error.reason}") from error

    if payload.get("type") != "file" or payload.get("encoding") != "base64":
        raise RuntimeError(f"GitHub did not return {path} as a base64 encoded file.")

    yaml_text = base64.b64decode(payload["content"]).decode("utf-8")
    return yaml.safe_load(yaml_text)


def load_data():
    """Load resume content from configured private GitHub repo or local YAML."""
    owner = _setting("CONTENT_GITHUB_OWNER")
    repo = _setting("CONTENT_GITHUB_REPO")
    token = _setting("CONTENT_GITHUB_TOKEN")
    if owner or repo or token:
        missing = [
            key for key, value in (
                ("CONTENT_GITHUB_OWNER", owner),
                ("CONTENT_GITHUB_REPO", repo),
                ("CONTENT_GITHUB_TOKEN", token),
            ) if not value
        ]
        if missing:
            raise RuntimeError("Missing Streamlit secrets: " + ", ".join(missing))
        branch = _setting("CONTENT_GITHUB_BRANCH", "main")
        path = _setting("CONTENT_GITHUB_PATH", "content.yaml")
        return _load_remote_data(owner, repo, token, branch, path)

    if not CONTENT_PATH.exists():
        raise RuntimeError(
            "Resume content was not found. Set CONTENT_GITHUB_OWNER, CONTENT_GITHUB_REPO, "
            "and CONTENT_GITHUB_TOKEN in Streamlit secrets, or provide a local content.yaml."
        )
    with open(CONTENT_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_data(data):
    """Persist the (possibly edited) data dict back to content.yaml."""
    with open(CONTENT_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=1000)
