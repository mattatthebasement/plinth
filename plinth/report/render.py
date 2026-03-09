"""PDF rendering engine for Plinth site intelligence reports.

Usage:
    from plinth.report.render import render_report_pdf
    pdf_bytes = render_report_pdf(context)
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML, CSS


_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


def _load_css() -> str:
    css_path = _STATIC_DIR / "report.css"
    return css_path.read_text(encoding="utf-8")


def _make_jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    return env


def render_report_html(context: dict[str, Any]) -> str:
    """Render the report Jinja2 template to an HTML string."""
    env = _make_jinja_env()
    template = env.get_template("report.html")
    context = dict(context, css=_load_css())
    return template.render(**context)


def render_report_pdf(context: dict[str, Any]) -> bytes:
    """Render the report to a PDF byte string via WeasyPrint."""
    html_str = render_report_html(context)
    html = HTML(string=html_str, base_url=str(_STATIC_DIR))
    return html.write_pdf()
