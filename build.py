#!/usr/bin/env python3
"""Render every view of Danny Rollo's CV from the single source of truth.

    data/cv.yml  ──▶  index.html      (website)
                 ──▶  cv.tex          (4-page academic CV)
                 ──▶  resume.tex      (1-page industry resume)
                 ──▶  resume-research.tex (1-page research/econ resume)

Prose fields in cv.yml use a neutral inline markup (**bold**, *italic*,
`code`) plus real unicode, and may reference any metric as {{ m.group.key }}.
This module resolves those references once, then escapes per target format so
the same sentence can render into HTML and LaTeX without being written twice.

Usage:  ./build.py            # render all targets
        ./build.py --check    # verify index.html is in sync, don't write
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cv.yml"
TEMPLATES = ROOT / "templates"

# Fields that hold prose and must be recursively resolved + markup-rendered.
# Everything else passes through untouched.
GENERATED_BANNER = "DO NOT EDIT — generated from data/cv.yml by build.py"


# ─────────────────────────────────────────────────────────────────────────────
#  Metric interpolation
# ─────────────────────────────────────────────────────────────────────────────
class Dotted(dict):
    """dict whose keys are reachable as attributes, for {{ m.group.key }}."""

    def __getattr__(self, key):
        try:
            value = self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc
        return Dotted(value) if isinstance(value, dict) else value


def resolve(node, env, metrics):
    """Walk the data tree rendering every string through Jinja.

    This is what makes {{ m.nucleus.dice_pannuke }} work anywhere in cv.yml.
    """
    if isinstance(node, str):
        if "{{" not in node:
            return node
        return env.from_string(node).render(m=metrics)
    if isinstance(node, list):
        return [resolve(v, env, metrics) for v in node]
    if isinstance(node, dict):
        return {k: resolve(v, env, metrics) for k, v in node.items()}
    return node


# ─────────────────────────────────────────────────────────────────────────────
#  Inline markup  →  HTML
# ─────────────────────────────────────────────────────────────────────────────
def md_html(text):
    """**bold** / *italic* / `code`  →  <strong> / <em> / <code>."""
    if not isinstance(text, str):
        return text
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    out = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  Inline markup + unicode  →  LaTeX
# ─────────────────────────────────────────────────────────────────────────────
# Order matters: backslash first, then LaTeX specials, then unicode.
TEX_SPECIALS = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
]

TEX_UNICODE = [
    ("—", "---"),
    ("–", "--"),
    ("·", r"\textperiodcentered{}"),
    ("×", r"$\times$"),
    ("÷", r"$\div$"),
    ("≤", r"$\leq$"),
    ("≥", r"$\geq$"),
    ("→", r"$\rightarrow$"),
    ("←", r"$\leftarrow$"),
    ("↔", r"$\leftrightarrow$"),
    ("↓", r"$\downarrow$"),
    ("↗", ""),
    ("²", r"$^2$"),
    ("³", r"$^3$"),
    ("τ", r"$\tau$"),
    ("~", r"$\sim$"),
    ("“", "``"),
    ("”", "''"),
    ("‘", "`"),
    ("’", "'"),
    ("│", "|"),
]


def tex(text):
    """Escape a prose string for LaTeX, honouring the inline markup."""
    if not isinstance(text, str):
        return text

    # Pull markup spans out before escaping so their delimiters survive.
    spans: list[str] = []

    def stash(wrapper):
        def repl(match):
            spans.append(wrapper % tex_plain(match.group(1)))
            return f"\0{len(spans) - 1}\0"

        return repl

    out = re.sub(r"\*\*(.+?)\*\*", stash(r"\textbf{%s}"), text)
    out = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", stash(r"\textit{%s}"), out)
    out = re.sub(r"`(.+?)`", stash(r"\texttt{%s}"), out)

    out = tex_plain(out)
    return re.sub(r"\0(\d+)\0", lambda mo: spans[int(mo.group(1))], out)


def tex_plain(text):
    """Escape with no markup handling (used inside already-extracted spans)."""
    for src, dst in TEX_SPECIALS:
        text = text.replace(src, dst)
    for src, dst in TEX_UNICODE:
        text = text.replace(src, dst)
    return text


# ─────────────────────────────────────────────────────────────────────────────
#  Rendering
# ─────────────────────────────────────────────────────────────────────────────
# Optional keys, filled with None/[] so templates can test them plainly while
# StrictUndefined still catches genuine typos in required fields.
DEFAULTS = {
    "publications": {"site_anchor": None, "status": None, "status_cv": None,
                     "year": None, "peer_reviewed": False, "links": []},
    "projects": {"site_id": None, "meta": None, "media": [], "detail_groups": [],
                 "links": [], "title_cv": None, "dates": None, "role_cv": None,
                 "stack_cv": None, "cv_bullets": [], "resume": False,
                 "cv_rank": None, "subtitle": None,
                 "research_rank": None, "research_bullets": []},
    "experience": {"title_short": None, "org_cv": None, "site_summary": None,
                   "date_short": None, "location": None, "resume": False,
                   "bullets": [], "roles": [], "org_short": None},
    "teaching": {"title_short": None, "org_cv": None, "site_summary": None,
                 "date_short": None, "resume": False, "bullets": [],
                 "course": None, "org_short": None},
    "honors": {"resume": False, "note": None, "title_short": None},
    "skills": {"resume": False, "resume_max": None,
               "research": False, "research_max": None},
}
MEDIA_DEFAULTS = {"position": None, "type": None, "html": None, "src": None,
                  "alt": None, "caption": None, "title": None, "videos": []}
LINK_DEFAULTS = {"external": False, "disabled": False, "title": None}


def apply_defaults(data):
    for section, defaults in DEFAULTS.items():
        for entry in data.get(section) or []:
            for key, value in defaults.items():
                entry.setdefault(key, value)
            for link in entry.get("links") or []:
                for key, value in LINK_DEFAULTS.items():
                    link.setdefault(key, value)
            for block in entry.get("media") or []:
                for key, value in MEDIA_DEFAULTS.items():
                    block.setdefault(key, value)
    return data


def load():
    raw = yaml.safe_load(DATA.read_text())
    # A bare Jinja env is used only to expand metric references in the data.
    interp = Environment(undefined=StrictUndefined, autoescape=False)
    metrics = Dotted(raw.get("metrics") or {})
    data = apply_defaults(resolve(raw, interp, metrics))

    data["projects"].sort(key=lambda p: p.get("site_order", 99))
    data["site_experience"] = sorted(
        [e for e in data["experience"] + data["teaching"] if "site_order" in e],
        key=lambda e: e["site_order"],
    )
    data["cv_projects"] = sorted(
        [p for p in data["projects"] if p.get("cv_rank")],
        key=lambda p: p["cv_rank"],
    )
    data["resume_projects"] = [p for p in data["cv_projects"] if p.get("resume")]
    data["research_projects"] = sorted(
        [p for p in data["projects"] if p.get("research_rank")],
        key=lambda p: p["research_rank"],
    )
    data["research_skills"] = [s for s in data["skills"] if s.get("research")]
    data["resume_experience"] = [e for e in data["experience"] if e.get("resume")]
    data["resume_skills"] = [s for s in data["skills"] if s.get("resume")]
    data["resume_honors"] = [h for h in data["honors"] if h.get("resume")]
    data["pubs_reviewed"] = [p for p in data["publications"] if p.get("peer_reviewed")]
    data["pubs_draft"] = [p for p in data["publications"] if not p.get("peer_reviewed")]
    data["banner"] = GENERATED_BANNER
    return data


# LaTeX uses { } heavily, so the .tex templates get non-colliding delimiters:
#   << var >>   <% block %>   <# comment #>
TEX_DELIMITERS = dict(
    variable_start_string="<<", variable_end_string=">>",
    block_start_string="<%", block_end_string="%>",
    comment_start_string="<#", comment_end_string="#>",
)


def env_for(target):
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,
        **({} if target == "html" else TEX_DELIMITERS),
    )
    env.filters["md"] = md_html if target == "html" else tex
    env.filters["tex"] = tex
    return env


# (template, output, escaper, extra context)
#
# These three are the documents you actually maintain: the site, the CV, and
# one resume. They are the only committed outputs.
TARGETS = [
    ("index.html.j2", "index.html", "html", {}),
    ("cv.tex.j2", "cv.tex", "tex", {}),
    ("resume.tex.j2", "resume.tex", "tex", {"variant": "ml"}),
]

# Disposable, built on demand with --targeted for a specific application.
# Not committed, not linked from the site. Generate it, send it, forget it.
TARGETED = [
    ("resume.tex.j2", "resume-research.tex", "tex", {"variant": "research"}),
]


def variant_context(data, variant):
    """Pick the project ordering, bullets, and skills for one resume variant."""
    if variant == "research":
        projects = data["research_projects"]
        skills = data["research_skills"]
    else:
        projects = data["resume_projects"]
        skills = data["resume_skills"]
    out = []
    for p in projects:
        p = dict(p)
        if variant == "research" and p["research_bullets"]:
            p["pick_bullets"] = p["research_bullets"]
        else:
            p["pick_bullets"] = p["cv_bullets"]
        out.append(p)
    return {"r_projects": out, "r_skills": skills}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="fail if any target is stale instead of writing")
    ap.add_argument("--targeted", action="store_true",
                    help="also render the research-targeted resume (not committed)")
    args = ap.parse_args()

    data = load()
    stale = []
    targets = TARGETS + (TARGETED if args.targeted else [])
    for template, output, target, extra in targets:
        ctx = dict(data, **extra)
        if "variant" in extra:
            ctx.update(variant_context(data, extra["variant"]))
        rendered = env_for(target).get_template(template).render(**ctx)
        path = ROOT / output
        current = path.read_text() if path.exists() else None
        if args.check:
            if current != rendered:
                stale.append(output)
            continue
        if current != rendered:
            path.write_text(rendered)
            print(f"  wrote {output}")
        else:
            print(f"  {output} unchanged")

    if args.check:
        if stale:
            print("STALE (run ./build.py): " + ", ".join(stale), file=sys.stderr)
            return 1
        print("all targets in sync with data/cv.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
