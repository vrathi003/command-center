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
