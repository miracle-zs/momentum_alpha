from __future__ import annotations

from .dashboard_assets_styles_base import _render_dashboard_base_styles
from .dashboard_assets_styles_components import _render_dashboard_component_styles
from .dashboard_assets_styles_cosmic import _render_dashboard_cosmic_styles
from .dashboard_assets_styles_responsive import _render_dashboard_responsive_styles


def render_dashboard_styles() -> str:
    return (
        _render_dashboard_base_styles()
        + _render_dashboard_cosmic_styles()
        + _render_dashboard_component_styles()
        + _render_dashboard_responsive_styles()
    )
