"""PDF rendering engine for Plinth site intelligence reports.

Usage:
    from plinth.report.render import render_report_pdf
    pdf_bytes = render_report_pdf(context)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML


_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

# Multi-stop blue→white→red gradient anchors for °F
# Tuned for the US continental range (~10°F–100°F)
_TEMP_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (10,  (69,  117, 180)),   # deep blue
    (32,  (145, 191, 219)),   # mid blue
    (50,  (215, 234, 245)),   # pale blue
    (58,  (247, 247, 247)),   # near-white neutral
    (68,  (254, 224, 182)),   # pale orange
    (82,  (253, 174,  97)),   # orange
    (92,  (244, 109,  67)),   # red-orange
    (102, (215,  48,  39)),   # deep red
]


def _interpolate_color(temp_f: float) -> tuple[int, int, int]:
    temp_f = max(_TEMP_STOPS[0][0], min(_TEMP_STOPS[-1][0], temp_f))
    for i in range(len(_TEMP_STOPS) - 1):
        t0, c0 = _TEMP_STOPS[i]
        t1, c1 = _TEMP_STOPS[i + 1]
        if t0 <= temp_f <= t1:
            frac = (temp_f - t0) / (t1 - t0)
            return (
                round(c0[0] + frac * (c1[0] - c0[0])),
                round(c0[1] + frac * (c1[1] - c0[1])),
                round(c0[2] + frac * (c1[2] - c0[2])),
            )
    return (247, 247, 247)


def _temp_bg_filter(temp_f) -> str:
    """Jinja2 filter: map °F → hex background color (blue→white→red). Handles None."""
    if temp_f is None:
        return "#e0e0e0"
    r, g, b = _interpolate_color(float(temp_f))
    return f"#{r:02x}{g:02x}{b:02x}"


def _temp_fg_filter(temp_f) -> str:
    """Jinja2 filter: return legible text color for a given temperature background. Handles None."""
    if temp_f is None:
        return "#888888"
    r, g, b = _interpolate_color(float(temp_f))
    # Relative luminance (sRGB approximation)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#ffffff" if luminance < 0.50 else "#1a1a1a"


def _load_css() -> str:
    return (_STATIC_DIR / "report.css").read_text(encoding="utf-8")


def _make_jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["temp_bg"] = _temp_bg_filter
    env.filters["temp_fg"] = _temp_fg_filter
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
