"""Sphinx configuration for the Personal Finance OS product guide."""

from __future__ import annotations

project = "Personal Finance OS"
copyright = "2026, Vaibhav"
author = "Vaibhav"
release = "1.0"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_copybutton",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]
html_title = "Personal Finance OS"
html_short_title = "PFOS"
# MagicDNS serves docs at /guide/; absolute base keeps CSS/JS working with or without a trailing slash.
html_baseurl = "/guide/"

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "tasklist",
]
myst_heading_anchors = 3

autodoc_typehints = "description"
autodoc_member_order = "bysource"
python_use_unqualified_type_names = True

# Autodoc imports from the workspace packages when the venv is active.
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _pkg in ("common", "api", "bot"):
    sys.path.insert(0, str(_ROOT / "packages" / _pkg / "src"))


def _inject_base_href(app, pagename, templatename, context, doctree) -> None:  # noqa: ARG001
    """Put <base> early in <head> so relative _static/ assets resolve under /guide/."""
    base = '<base href="/guide/">'
    existing = context.get("metatags") or ""
    if '<base href="/guide/">' not in existing:
        context["metatags"] = f"{base}\n{existing}" if existing else base


def setup(app):
    app.connect("html-page-context", _inject_base_href)
    return {"parallel_read_safe": True, "parallel_write_safe": True}