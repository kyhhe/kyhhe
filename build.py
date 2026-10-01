#!/usr/bin/env python3
"""
build.py

Loads content.yaml, resolves which sections/entries/bullets are enabled
and which bullet variant is selected, renders template.tex.jinja into a
final .tex file, and (if pdflatex is available) compiles it to PDF.

Usage:
    python build.py                       # uses content.yaml -> output/resume.tex(+pdf)
    python build.py --content my.yaml     # use a different content file
    python build.py --no-pdf              # only render .tex, skip compiling
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).parent
DEFAULT_CONTENT = BASE_DIR / "content.yaml"
TEMPLATE_NAME = "template.tex.jinja"
OUTPUT_DIR = BASE_DIR / "output"


def load_content(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_highlight_text(highlight: dict) -> str:
    """Pick the selected variant's text for a single bullet."""
    variants = highlight.get("variants", {})
    selected = highlight.get("selected", "default")
    if selected not in variants:
        # fall back to first available variant if selection is invalid
        selected = next(iter(variants))
    return variants[selected]


def process_content(data: dict) -> dict:
    """
    Filter out disabled sections/entries/bullets/items and resolve each
    bullet down to plain text based on its selected variant. Returns a
    simplified structure the Jinja template can loop over directly.
    """
    processed = {"personal": data["personal"], "sections": []}

    for section in data.get("sections", []):
        if not section.get("enabled", True):
            continue

        new_section = {
            "id": section["id"],
            "name": section["name"],
            "type": section["type"],
            "entries": [],
        }

        for entry in section.get("entries", []):
            if not entry.get("enabled", True):
                continue

            new_entry = dict(entry)  # shallow copy, we'll overwrite bullet fields
            if section["type"] == "education":
                new_entry["courses"] = [
                    resolve_highlight_text(h)
                    for h in entry.get("courses", [])
                    if h.get("enabled", True)
                ]

            elif section["type"] == "experience":
                new_entry["highlights"] = [
                    resolve_highlight_text(h)
                    for h in entry.get("highlights", [])
                    if h.get("enabled", True)
                ]

            elif section["type"] == "skills":
                new_entry["items"] = [
                    i["text"] for i in entry.get("items", []) if i.get("enabled", True)
                ]
                if not new_entry["items"]:
                    continue

            new_section["entries"].append(new_entry)

        # Skip sections that ended up with no visible entries
        if new_section["entries"]:
            processed["sections"].append(new_section)

    return processed


def render_tex(processed: dict) -> str:
    env = Environment(
        block_start_string="\\BLOCK{",
        block_end_string="}",
        variable_start_string="\\VAR{",
        variable_end_string="}",
        comment_start_string="\\#{",
        comment_end_string="}",
        line_statement_prefix=None,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
        loader=FileSystemLoader(str(BASE_DIR)),
    )
    template = env.get_template(TEMPLATE_NAME)
    return template.render(**processed)


def compile_pdf(tex_path: Path) -> bool:
    """Try latexmk first (handles multiple passes automatically), then pdflatex.

    LaTeX/latexmk can return a non-zero exit code even when a PDF was
    successfully produced (benign warnings, font substitution notices,
    MiKTeX on-the-fly package installation messages, etc). So the real
    signal of success is: does a PDF now exist, and is it newer than
    before we ran the compiler? We fall back to the exit code only if
    we can't tell from the file itself.
    """
    pdf_path = tex_path.with_suffix(".pdf")
    log_path = tex_path.with_suffix(".log")
    pdf_existed_before = pdf_path.exists()
    mtime_before = pdf_path.stat().st_mtime if pdf_existed_before else None

    # Prefer pdflatex: this resume has no table of contents, citations, or
    # cross-references, so it never needs latexmk's multi-pass automation --
    # and latexmk itself requires a Perl interpreter, which isn't guaranteed
    # to be present even when latexmk is installed (common on Windows/MiKTeX).
    if shutil.which("pdflatex"):
        cmd = ["pdflatex", "-interaction=nonstopmode", tex_path.name]
    elif shutil.which("latexmk"):
        cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", tex_path.name]
    else:
        print("No pdflatex/latexmk found on PATH -- skipping PDF compile.")
        print("Install a LaTeX distribution (e.g. TeX Live, MacTeX, MiKTeX) to enable this.")
        return False

    result = subprocess.run(
        cmd,
        cwd=tex_path.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # Some setups (notably latexmk on Windows) route diagnostics through
    # stderr instead of stdout -- combine both so we don't miss anything.
    combined_output = (result.stdout or "") + (result.stderr or "")

    pdf_now_exists = pdf_path.exists()
    pdf_is_fresh = pdf_now_exists and (
        mtime_before is None or pdf_path.stat().st_mtime > mtime_before
    )

    if pdf_is_fresh:
        if result.returncode != 0:
            print(
                "Note: the compiler exited with a non-zero status, but a fresh "
                f"PDF was produced -- likely just warnings. Full log: {log_path}"
            )
        return True

    # No fresh PDF -- this is a real failure. Try to show something useful.
    print("LaTeX compilation failed.")
    if combined_output.strip():
        print("Last 40 lines of compiler output:")
        print("\n".join(combined_output.splitlines()[-40:]))
    else:
        # stdout/stderr were empty (common with latexmk on some setups) --
        # the .log file always has the real detail, so fall back to that.
        print(f"(No output captured from the process directly -- reading {log_path} instead)")
        if log_path.exists():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            print("Last 40 lines of the LaTeX log file:")
            print("\n".join(log_text.splitlines()[-40:]))
        else:
            print(
                f"No log file found at {log_path} either. This usually means the "
                "compiler couldn't start at all -- double check pdflatex/latexmk "
                "is really on PATH for this process (not just your regular terminal)."
            )
    return False


def main():
    parser = argparse.ArgumentParser(description="Build a resume PDF from content.yaml")
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT, help="Path to content YAML file")
    parser.add_argument("--no-pdf", action="store_true", help="Only render .tex, don't compile to PDF")
    parser.add_argument("--out", type=str, default="resume", help="Output filename stem (no extension)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    data = load_content(args.content)
    processed = process_content(data)
    tex_source = render_tex(processed)

    tex_path = OUTPUT_DIR / f"{args.out}.tex"
    tex_path.write_text(tex_source, encoding="utf-8")
    print(f"Wrote {tex_path}")

    if not args.no_pdf:
        ok = compile_pdf(tex_path)
        pdf_path = OUTPUT_DIR / f"{args.out}.pdf"
        if ok and pdf_path.exists():
            print(f"Wrote {pdf_path}")
        elif ok:
            print("Compile reported success but PDF not found -- check output/ directory.")


if __name__ == "__main__":
    main()
