"""
content_model.py

Pure logic over the content data structure — no Streamlit, no file I/O.
These functions just walk or mutate the `data` dict, so they're easy to
unit test with plain dicts/lists.
"""

import uuid


# Curated public resume profiles. IDs refer to stable IDs in content.yaml.
RESUME_PRESETS = {
    "Hardware": {
        "entries": {"ubc", "cet", "biomed_team", "uas_team", "timer_cube", "tron_game", "comb_lock", "virtual_pet"},
        "bullets": {"course_h1", "h_0d257d26", "cet_h1", "cet_h4", "cet_h5", "h_294eb3ab", "biomed_h2", "biomed_h3", "uas_h1", "uas_h2", "uas_h3", "timer_cube_h1", "h_ac0a4132", "tron_h1", "tron_h2", "tron_h4", "lock_h1", "lock_h2", "pet_h1", "pet_h2", "pet_h3"},
        "items": {"lang1", "lang3", "lang4", "lang8", "emb1", "emb2", "emb3", "emb4", "emb5", "emb6", "emb7", "emb8", "hw1", "hw2", "hw3", "hw4", "hw7"},
    },
    "Firmware / Embedded": {
        "entries": {"ubc", "cet", "biomed_team", "uas_team", "timer_cube", "tron_game", "comb_lock"},
        "bullets": {"course_h1", "cet_h1", "cet_h2", "cet_h3", "cet_h4", "h_294eb3ab", "cet_h7", "biomed_h1", "biomed_h3", "uas_h1", "timer_cube_h1", "h_52cc361c", "h_5b1df0e1", "tron_h1", "tron_h2", "tron_h3", "tron_h4", "lock_h1", "lock_h2", "pet_h1", "pet_h2", "pet_h3"},
        "items": {"lang1", "lang3", "lang4", "lang8", "emb1", "emb2", "emb3", "emb4", "emb5", "emb6", "emb7", "emb8", "hw1", "hw2", "hw3", "hw4", "hw7"},
    },
    "Software": {
        "entries": {"ubc", "cet", "timer_cube", "tron_game", "gardening_game", "journal"},
        "bullets": {"course_h2", "course_h3", "h_13cb73ae", "cet_h1", "cet_h2", "cet_h3", "cet_h6", "cet_h7", "timer_cube_h1", "h_52cc361c", "h_5b1df0e1", "tron_h1", "tron_h3", "tron_h4", "garden_h1", "garden_h2", "garden_h3", "h_9301f2b6", "journal_h1", "journal_h2"},
        "items": {"lang1", "lang2", "lang3", "lang4", "lang5", "lang6", "lang7", "fw1", "fw2", "fw3", "fw4", "fw5", "tool1", "tool2", "tool3", "tool9", "tool4", "tool5"},
    },
}


def apply_resume_preset(data: dict, preset_name: str) -> None:
    """Apply a curated profile by enabling its entries, bullets, and skills."""
    preset = RESUME_PRESETS[preset_name]
    for section in data.get("sections", []):
        section["enabled"] = section["id"] != "work"
        for entry in section.get("entries", []):
            if section["type"] == "skills":
                entry["enabled"] = True
                for item in entry.get("items", []):
                    item["enabled"] = item["id"] in preset["items"]
            else:
                entry["enabled"] = entry["id"] in preset["entries"]
                highlights = entry.get("courses", []) if section["type"] == "education" else entry.get("highlights", [])
                for highlight in highlights:
                    highlight["enabled"] = highlight["id"] in preset["bullets"]


def new_bullet_id() -> str:
    """Generate a fresh unique id for a new bullet."""
    return f"h_{uuid.uuid4().hex[:8]}"


def new_skill_id() -> str:
    """Generate a fresh id for a skill category or item."""
    return f"skill_{uuid.uuid4().hex[:8]}"


def all_highlight_lists(data):
    """Yield every highlights list in the document (flat, for global variant switching)."""
    for section in data["sections"]:
        for entry in section.get("entries", []):
            if section["type"] == "education":
                yield entry.get("courses", [])
            elif section["type"] == "experience":
                yield entry.get("highlights", [])


def all_variant_names(data):
    """All distinct variant keys used anywhere, for variant dropdowns."""
    names = set()
    for hl in all_highlight_lists(data):
        for h in hl:
            names.update(h.get("variants", {}).keys())
    return sorted(names)


def apply_global_variant(data, variant_name):
    """
    Switch every bullet that has `variant_name` among its variants to use
    it as the selected variant. Bullets without that variant are left
    untouched. Returns the count of bullets that were switched.
    """
    switched = 0
    for hl in all_highlight_lists(data):
        for h in hl:
            if variant_name in h.get("variants", {}):
                h["selected"] = variant_name
                switched += 1
    return switched
