#!/usr/bin/env python3
"""
app.py

Streamlit UI for toggling resume sections/entries/bullets on or off,
editing bullet text, choosing/adding bullet variants (individually or
globally), adding new bullets, and building the PDF.

This file just wires together the other modules:
    content_io.py    - loading/saving content.yaml
    content_model.py - pure data-model logic (no Streamlit)
    ui.py            - all Streamlit widget rendering
    build.py         - process_content / render_tex / compile_pdf (unchanged)

Run with:
    streamlit run app.py
"""

import streamlit as st
from html import escape
import os

from content_io import load_data, save_data, OUTPUT_DIR
from ui import render_sections, render_build_panel
from content_model import RESUME_PRESETS, apply_resume_preset

st.set_page_config(page_title="Kelly's Resume", layout="wide")

if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data

# Seed keyed widget state once from the loaded resume. Preset callbacks can
# then update these keys directly without also passing widget defaults.
for section in data.get("sections", []):
    st.session_state.setdefault(f"sec_{section['id']}", section.get("enabled", True))
    for entry in section.get("entries", []):
        st.session_state.setdefault(f"entry_{entry['id']}", entry.get("enabled", True))
        if section["type"] == "education":
            highlights = entry.get("courses", [])
        elif section["type"] == "experience":
            highlights = entry.get("highlights", [])
        else:
            highlights = []
        for highlight in highlights:
            st.session_state.setdefault(f"h_en_{highlight['id']}", highlight.get("enabled", True))
            selected = highlight.get("selected")
            if selected in highlight.get("variants", {}):
                st.session_state.setdefault(f"h_var_{highlight['id']}", selected)
        for item in entry.get("items", []):
            st.session_state.setdefault(f"item_{item['id']}", item.get("enabled", True))

editor_setting = os.environ.get("EDITOR_MODE")
if editor_setting is None:
    try:
        editor_setting = st.secrets.get("EDITOR_MODE", "false")
    except Exception:
        editor_setting = "false"
editor_mode = str(editor_setting).strip().lower() in {"1", "true", "yes", "on"}

if editor_mode:
    st.title("Kelly's Resume - Editor")
else:
    st.title("Kelly's Resume")
st.caption("Toggle experiences and bullets, select variants, then build a PDF.")

profile = data.get("personal", {})
profile_links = []
for label, field in (("GitHub", "github"), ("LinkedIn", "linkedin")):
    url = profile.get(field, "").strip()
    if url:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        profile_links.append((label, url))

if profile_links:
    icons = {
        "GitHub": '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .5a12 12 0 0 0-3.79 23.39c.6.11.82-.26.82-.58v-2.05c-3.34.73-4.04-1.42-4.04-1.42-.55-1.39-1.33-1.76-1.33-1.76-1.09-.75.08-.74.08-.74 1.2.09 1.83 1.23 1.83 1.23 1.07 1.83 2.8 1.3 3.49.99.11-.78.42-1.3.76-1.6-2.67-.3-5.47-1.34-5.47-5.95 0-1.31.47-2.38 1.23-3.22-.12-.3-.53-1.52.12-3.18 0 0 1-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.3-1.55 3.3-1.23 3.3-1.23.65 1.66.24 2.88.12 3.18.77.84 1.23 1.91 1.23 3.22 0 4.62-2.8 5.64-5.48 5.94.43.37.81 1.1.81 2.22v3.29c0 .32.22.69.83.57A12 12 0 0 0 12 .5Z"/></svg>',
        "LinkedIn": '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M20.45 2H3.55C2.69 2 2 2.68 2 3.52v16.96c0 .84.69 1.52 1.55 1.52h16.9c.86 0 1.55-.68 1.55-1.52V3.52c0-.84-.69-1.52-1.55-1.52ZM8.03 18.34H5.06V9.75h2.97v8.59ZM6.55 8.58a1.72 1.72 0 1 1 .02-3.44 1.72 1.72 0 0 1-.02 3.44Zm12.3 9.76h-2.97v-4.18c0-1-.02-2.28-1.39-2.28-1.39 0-1.6 1.08-1.6 2.2v4.26H9.92V9.75h2.85v1.17h.04c.4-.74 1.37-1.52 2.82-1.52 3.02 0 3.58 1.99 3.58 4.57v4.37Z"/></svg>',
    }
    links_html = ''.join(
        f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" '
        f'aria-label="{label}" title="{label}" '
        'style="display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;'
        'margin-right:8px;border:1px solid rgba(128,128,128,.35);border-radius:8px;'
        'color:inherit;text-decoration:none">'
        f'<span style="display:flex;width:20px;height:20px">{icons[label]}</span></a>'
        for label, url in profile_links
    )
    st.markdown(links_html, unsafe_allow_html=True)


def _apply_selected_preset():
    preset_name = st.session_state.resume_preset
    if preset_name == "Custom selections":
        return

    apply_resume_preset(data, preset_name)
    for section in data.get("sections", []):
        st.session_state[f"sec_{section['id']}"] = section["enabled"]
        for entry in section.get("entries", []):
            st.session_state[f"entry_{entry['id']}"] = entry["enabled"]
            if section["type"] == "education":
                highlights = entry.get("courses", [])
            elif section["type"] == "experience":
                highlights = entry.get("highlights", [])
            else:
                highlights = []
            for highlight in highlights:
                st.session_state[f"h_en_{highlight['id']}"] = highlight["enabled"]
                selected = highlight.get("selected")
                if selected in highlight.get("variants", {}):
                    st.session_state[f"h_var_{highlight['id']}"] = selected
            for item in entry.get("items", []):
                st.session_state[f"item_{item['id']}"] = item["enabled"]

    # Rebuild the public PDF so the preview matches the selected profile.
    if not editor_mode:
        st.session_state.public_pdf_initialized = False


st.selectbox(
    "Resume focus",
    ["Custom selections", *RESUME_PRESETS.keys()],
    key="resume_preset",
    on_change=_apply_selected_preset,
    help="Choose a tailored starting point. You can still adjust individual sections and bullets afterward.",
)

col_editor, col_preview = st.columns([4, 3])

with col_editor:
    render_sections(data, editor_mode=editor_mode)

with col_preview:
    render_build_panel(data, save_data_fn=save_data, output_dir=OUTPUT_DIR, editor_mode=editor_mode)
