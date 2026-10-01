"""
ui.py

All Streamlit widget rendering for the resume builder. These functions
both draw widgets and mutate `data` in place based on widget state — that
part of Streamlit's model (render-and-mutate in one pass) isn't worth
fighting, so it stays together here rather than being split further.

Public entry points used by app.py:
    render_sections(data)
    render_build_panel(data, out_name)
"""

import streamlit as st
import hashlib
import tempfile
from pathlib import Path

from streamlit_sortables import sort_items
from streamlit_pdf_viewer import pdf_viewer
from content_model import all_variant_names, new_bullet_id, new_skill_id
from build import process_content, render_tex, compile_pdf

NEW_VARIANT_SENTINEL = "+ Add new variant..."


def _bullet_editor(h, container, variant_names, can_move_up=False, can_move_down=False, editor_mode=True):
    """Render one bullet's controls (enable, text preview, variant picker,
    edit-toggle, delete). When the edit toggle is on, shows inline controls
    (no expander/box) for editing variant text, deleting a variant, and
    adding a new variant to this specific bullet. Returns True if the
    bullet itself was deleted."""
    variant_keys = list(h.get("variants", {}).keys())
    edit_key = f"edit_mode_{h['id']}"
    if edit_key not in st.session_state:
        st.session_state[edit_key] = False

    row = container.columns([0.05, 0.47, 0.18, 0.06, 0.06, 0.08, 0.1] if editor_mode else [0.08, 0.62, 0.30])

    h["enabled"] = row[0].checkbox(
        "Include bullet", key=f"h_en_{h['id']}", label_visibility="collapsed"
    )

    preview_text = h["variants"].get(h.get("selected", variant_keys[0]), "")
    row[1].markdown(
        f"<span style='opacity:{1 if h['enabled'] else 0.4}'>{preview_text}</span>", unsafe_allow_html=True
    )

    if len(variant_keys) > 1:
        h["selected"] = row[2].selectbox(
            "variant", variant_keys, key=f"h_var_{h['id']}", label_visibility="collapsed"
        )
    else:
        h["selected"] = variant_keys[0]
        row[2].caption(variant_keys[0])

    if not editor_mode:
        return None

    if row[3].button("↑", key=f"h_up_{h['id']}", help="Move bullet up", disabled=not can_move_up):
        return "up"
    if row[4].button("↓", key=f"h_down_{h['id']}", help="Move bullet down", disabled=not can_move_down):
        return "down"
    if row[5].button("✏️", key=f"h_edittoggle_{h['id']}", help="Edit this bullet's variants"):
        st.session_state[edit_key] = not st.session_state[edit_key]
        st.rerun()

    deleted = row[6].button("✕", key=f"h_del_{h['id']}", help="Delete this bullet")    # Inline editing
    if st.session_state[edit_key]:
        variant_to_delete = None
        for vname in list(h["variants"].keys()):
            vrow = container.columns([0.06, 0.16, 0.68, 0.1])
            vrow[1].caption(vname + (" ⭐" if vname == h["selected"] else ""))
            edited_text = vrow[2].text_input(
                f"Text for '{vname}'",
                value=h["variants"][vname],
                key=f"h_vartext_{h['id']}_{vname}",
                label_visibility="collapsed",
            )
            h["variants"][vname] = edited_text
            can_delete_variant = len(h["variants"]) > 1
            if vrow[3].button(
                "×", key=f"h_vardel_{h['id']}_{vname}", help="Delete this variant", disabled=not can_delete_variant
            ):
                variant_to_delete = vname

        if variant_to_delete is not None:
            del h["variants"][variant_to_delete]
            if h["selected"] == variant_to_delete:
                h["selected"] = next(iter(h["variants"]))
            st.rerun()

        # Build the dropdown options: known variant names not already on this
        # bullet, plus a sentinel to create a brand new variant category.
        # (Variants this bullet already has are excluded since re-adding
        # them would just be editing, which the rows above already do.)
        options = [v for v in variant_names if v not in h["variants"]]
        if "default" not in options and "default" not in h["variants"]:
            options = ["default"] + options
        options = options + [NEW_VARIANT_SENTINEL]

        # The dropdown sits in its own column to the left of the form
        # (rather than above it, and rather than inside it) so that
        # picking "+ Add new variant..." can immediately reveal the new
        # variant-name field — forms only rerun on submit, not on every
        # widget change, so the dropdown has to live outside the form.
        outer_row = container.columns([0.2, 0.8])
        variant_choice = outer_row[0].selectbox(
            "Variant category for new variant",
            options,
            key=f"h_addvar_choice_{h['id']}",
            label_visibility="collapsed",
        )

        with outer_row[1].form(key=f"h_addvarform_{h['id']}", clear_on_submit=True):
            if variant_choice == NEW_VARIANT_SENTINEL:
                add_row = st.columns([0.3, 0.5, 0.2])
                new_vname = add_row[0].text_input(
                    "New variant name",
                    label_visibility="collapsed",
                    placeholder="new variant name",
                )
                text_col = add_row[1]
                submit_col = add_row[2]
            else:
                add_row = st.columns([0.8, 0.2])
                new_vname = variant_choice
                text_col = add_row[0]
                submit_col = add_row[1]

            new_vtext = text_col.text_input(
                "New variant text",
                label_visibility="collapsed",
                placeholder="bullet text",
            )
            add_submitted = submit_col.form_submit_button("+ Add", use_container_width=True)
            if add_submitted and new_vtext.strip():
                vname = new_vname.strip() if variant_choice == NEW_VARIANT_SENTINEL else new_vname
                if vname:
                    h["variants"][vname] = new_vtext.strip()
                    st.rerun()

    return "delete" if deleted else None


def _add_bullet_form(highlights_list, form_key, variant_names):
    """Add a brand new bullet, choosing an existing variant category or
    creating a new one. The variant dropdown lives outside the form so
    picking '+ Add new variant...' immediately reveals the name field."""
    options = list(variant_names) if variant_names else []
    if "default" not in options:
        options = ["default"] + options
    options = options + [NEW_VARIANT_SENTINEL]

    # Dropdown in its own column to the left of the form, rather than
    # stacked above it. Kept outside the form so picking "+ Add new
    # variant..." immediately reveals the new-variant-name field.
    outer_row = st.columns([0.2, 0.8])
    variant_select_key = f"{form_key}_variant_choice"
    variant_choice = outer_row[0].selectbox(
        "Variant category for new bullet", options, key=variant_select_key, label_visibility="collapsed"
    )

    with outer_row[1].form(key=form_key, clear_on_submit=True):
        if variant_choice == NEW_VARIANT_SENTINEL:
            cols = st.columns([0.45, 0.35, 0.2])
            new_text = cols[0].text_input(
                "New bullet text", label_visibility="collapsed", placeholder="New bullet text"
            )
            new_variant_name = cols[1].text_input(
                "New variant name", label_visibility="collapsed", placeholder="new variant category name"
            )
            submit_col = cols[2]
        else:
            cols = st.columns([0.8, 0.2])
            new_text = cols[0].text_input(
                "New bullet text", label_visibility="collapsed", placeholder="New bullet text"
            )
            new_variant_name = ""
            submit_col = cols[1]

        submitted = submit_col.form_submit_button("+ Add bullet", use_container_width=True)

        if submitted and new_text.strip():
            if variant_choice == NEW_VARIANT_SENTINEL:
                variant_key = new_variant_name.strip() or "default"
            else:
                variant_key = variant_choice
            highlights_list.append(
                {
                    "id": new_bullet_id(),
                    "enabled": True,
                    "selected": variant_key,
                    "variants": {variant_key: new_text.strip()},
                }
            )
            st.rerun()


def _entry_label(section, entry):
    """Human-readable label for an entry, used both by the drag-and-drop
    widget and the expander header."""
    if section["type"] == "education":
        return f"{entry.get('institution', '')} — {entry.get('degree', '')}"
    elif section["type"] == "experience":
        bold = entry.get("bold", "")
        italic = entry.get("italic", "")
        return f"{bold} — {italic}" if italic else bold
    else:  # skills
        return entry.get("category", "")


def _render_reorder_widget(section):
    entries = section.get("entries", [])
    if len(entries) < 2:
        return

    def _is_enabled(e):
        # Session state already has the just-clicked value at this point
        # in the script (Streamlit updates it before triggering the rerun),
        # even though entry["enabled"] itself won't be reassigned until the
        # checkbox loop runs later in this same script pass.
        return st.session_state.get(f"entry_{e['id']}", e.get("enabled", True))

    visible_entries = [e for e in entries if _is_enabled(e)]
    if len(visible_entries) < 1:
        return

    labels = [_entry_label(section, e) for e in visible_entries]
    id_by_label = {lbl: e["id"] for lbl, e in zip(labels, visible_entries)}
    entry_by_id = {e["id"]: e for e in entries}

    fingerprint = hashlib.md5("|".join(labels).encode()).hexdigest()[:8]

    st.caption("Drag to reorder:")
    new_order = sort_items(
        labels,
        key=f"sortable_{section['id']}_{fingerprint}",
    )

    if new_order != labels:
        # Rebuild full entries list: reordered visible entries first,
        # keeping disabled entries appended in their existing relative order
        reordered_visible = [entry_by_id[id_by_label[l]] for l in new_order]
        hidden_entries = [e for e in entries if e not in visible_entries]
        section["entries"] = reordered_visible + hidden_entries
        st.rerun()


def render_sections(data, editor_mode=True):
    """Render the full editor column: every section, entry, and bullet."""
    for section in data["sections"]:
        header_cols = st.columns([0.08, 0.92])
        section["enabled"] = header_cols[0].checkbox(
            "Include section",
            key=f"sec_{section['id']}",
            label_visibility="collapsed",
        )
        header_cols[1].subheader(section["name"])

        if not section["enabled"]:
            continue

        if editor_mode:
            _render_reorder_widget(section)

        for entry in section.get("entries", []):
            entry_cols = st.columns([0.06, 0.94])

            # Build a readable label for the entry depending on section type
            label = _entry_label(section, entry)

            entry["enabled"] = entry_cols[0].checkbox(
                "Include entry",
                key=f"entry_{entry['id']}",
                label_visibility="collapsed",
            )
            with entry_cols[1].expander(label, expanded=False):
                if not entry["enabled"]:
                    st.caption("Disabled — won't appear on the resume.")

                if section["type"] == "education":
                    highlights = entry.get("courses", [])
                    to_delete = None
                    for index, h in enumerate(highlights):
                        action = _bullet_editor(h, st, variant_names=all_variant_names(data), editor_mode=editor_mode,
                                                can_move_up=index > 0, can_move_down=index < len(highlights) - 1)
                        if action == "up":
                            highlights[index - 1], highlights[index] = highlights[index], highlights[index - 1]
                            st.rerun()
                        elif action == "down":
                            highlights[index], highlights[index + 1] = highlights[index + 1], highlights[index]
                            st.rerun()
                        elif action == "delete":
                            to_delete = h
                    if to_delete is not None:
                        highlights.remove(to_delete)
                        st.rerun()
                    if editor_mode: _add_bullet_form(highlights, form_key=f"add_{entry['id']}", variant_names=all_variant_names(data))

                elif section["type"] == "experience":
                    highlights = entry.get("highlights", [])
                    to_delete = None
                    for index, h in enumerate(highlights):
                        action = _bullet_editor(h, st, variant_names=all_variant_names(data), editor_mode=editor_mode,
                                                can_move_up=index > 0, can_move_down=index < len(highlights) - 1)
                        if action == "up":
                            highlights[index - 1], highlights[index] = highlights[index], highlights[index - 1]
                            st.rerun()
                        elif action == "down":
                            highlights[index], highlights[index + 1] = highlights[index + 1], highlights[index]
                            st.rerun()
                        elif action == "delete":
                            to_delete = h
                    if to_delete is not None:
                        highlights.remove(to_delete)
                        st.rerun()
                    if editor_mode: _add_bullet_form(highlights, form_key=f"add_{entry['id']}", variant_names=all_variant_names(data))

                elif section["type"] == "skills":
                    if editor_mode:
                        entry["category"] = st.text_input(
                            "Category name",
                            value=entry.get("category", ""),
                            key=f"skill_category_{entry['id']}",
                        )
                    items = entry.get("items", [])
                    for index, item in enumerate(items):
                        skill_row = st.columns([0.06, 0.56, 0.12, 0.12, 0.14] if editor_mode else [1])
                        item["enabled"] = skill_row[0].checkbox(
                            f"Include {item.get('text', 'skill')}" if editor_mode else item.get("text", "skill"),
                            key=f"item_{item['id']}",
                            label_visibility="collapsed" if editor_mode else "visible",
                        )
                        if editor_mode:
                            item["text"] = skill_row[1].text_input(
                                "Skill name", value=item.get("text", ""), key=f"skill_text_{item['id']}",
                                label_visibility="collapsed",
                            )
                            if skill_row[2].button("↑", key=f"skills_{entry['id']}_up_{item['id']}",
                                                    help="Move skill up", disabled=index == 0):
                                items[index - 1], items[index] = items[index], items[index - 1]
                                st.rerun()
                            if skill_row[3].button("↓", key=f"skills_{entry['id']}_down_{item['id']}",
                                                    help="Move skill down", disabled=index == len(items) - 1):
                                items[index], items[index + 1] = items[index + 1], items[index]
                                st.rerun()
                            if skill_row[4].button("✕", key=f"skills_{entry['id']}_delete_{item['id']}",
                                                    help="Remove skill"):
                                items.remove(item)
                                st.rerun()

                    if editor_mode:
                        with st.form(key=f"add_skill_form_{entry['id']}", clear_on_submit=True):
                            add_cols = st.columns([0.8, 0.2])
                            skill_text = add_cols[0].text_input("New skill", placeholder="Add a skill")
                            add_skill = add_cols[1].form_submit_button("+ Add skill", use_container_width=True)
                        if add_skill and skill_text.strip():
                            items.append({"id": new_skill_id(), "enabled": True, "text": skill_text.strip()})
                            st.rerun()
                        if st.button("Remove category", key=f"delete_skill_category_{entry['id']}"):
                            section["entries"].remove(entry)
                            st.rerun()

        if section["type"] == "skills" and editor_mode:
            with st.form(key=f"add_skill_category_form_{section['id']}", clear_on_submit=True):
                category_cols = st.columns([0.8, 0.2])
                category_name = category_cols[0].text_input("New skill category", placeholder="e.g. Frameworks and tools")
                add_category = category_cols[1].form_submit_button("+ Add category", use_container_width=True)
            if add_category and category_name.strip():
                section["entries"].append({
                    "id": new_skill_id(), "enabled": True, "category": category_name.strip(), "items": [],
                })
                st.rerun()
import base64

def render_pdf_preview(pdf_path):
    # if pdf_path.exists():
    #     with open(pdf_path, "rb") as f:
    #         base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        
    #     # style="height: 85vh;" makes the viewer take up 85% of the screen height.
    #     # #view=Fit tells the browser to zoom the PDF so the whole page is visible.
    #     pdf_display = f'''
    #     <iframe 
    #         src="data:application/pdf;base64,{base64_pdf}#view=Fit" 
    #         width="100%" 
    #         style="height: 85vh; border: none;" 
    #         type="application/pdf">
    #     </iframe>
    #     '''
        
    #     st.markdown(pdf_display, unsafe_allow_html=True)
    # else:
        # st.info("No PDF built yet — click 'Build PDF' to generate a preview.")    
    if pdf_path.exists():
        pdf_viewer(str(pdf_path))
    else:
        st.info("No PDF built yet — click 'Build PDF' to generate a preview.")
        
def render_build_panel(data, save_data_fn, output_dir, editor_mode=True):
    st.subheader("Build")
    if not editor_mode:
        if "public_output_dir" not in st.session_state:
            st.session_state.public_output_dir = Path(tempfile.mkdtemp(prefix="resume-builder-"))
        output_dir = st.session_state.public_output_dir
    out_name = st.text_input("Output filename (no extension)", value="resume")
    out_name = Path(out_name).name.strip()
    if out_name.lower().endswith(".tex") or out_name.lower().endswith(".pdf"):
        out_name = Path(out_name).stem
    if not out_name:
        out_name = "resume"

    if editor_mode and st.button("💾 Save selections to content.yaml", use_container_width=True):
        save_data_fn(data)
        st.success("Saved content.yaml")

    build_clicked = st.button("Build PDF", type="primary", use_container_width=True)
    build_initial_public_pdf = not editor_mode and not st.session_state.get("public_pdf_initialized", False)
    if build_clicked or build_initial_public_pdf:
        # if build_initial_public_pdf:
        #     st.info("Preparing your PDF preview…")
        if editor_mode:
            save_data_fn(data)
        output_dir.mkdir(exist_ok=True)
        processed = process_content(data)
        if not editor_mode:
            processed["personal"] = dict(processed.get("personal", {}))
            processed["personal"].pop("phone_display", None)
            processed["personal"].pop("phone_link", None)
        tex_source = render_tex(processed)
        tex_path = output_dir / f"{out_name}.tex"
        tex_path.write_text(tex_source, encoding="utf-8")
        with st.spinner("Compiling LaTeX..."):
            ok = compile_pdf(tex_path)
        pdf_path = output_dir / f"{out_name}.pdf"
        if ok and pdf_path.exists():
            if not editor_mode:
                st.session_state.public_pdf_initialized = True
            st.success(f"Built {pdf_path.name}")
            with open(pdf_path, "rb") as f:
                st.download_button("⬇️ Download PDF", f, file_name=pdf_path.name, use_container_width=True)
            st.download_button(
                "Download TeX",
                data=tex_source,
                file_name=tex_path.name,
                mime="application/x-tex",
                use_container_width=True,
                key="download_built_tex",
            )
        else:
            st.error("Build failed — check the terminal running Streamlit for the LaTeX log.")
            st.code((output_dir / f"{out_name}.tex").read_text(), language="latex")

    st.divider()

    # Live preview: shows the most recently built PDF for this out_name,
    # regardless of whether it was just built in this exact rerun.
    pdf_path = output_dir / f"{out_name}.pdf"
    render_pdf_preview(pdf_path)
