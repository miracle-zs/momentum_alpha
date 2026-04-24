from __future__ import annotations

from html import escape


def _render_cosmic_color_swatches() -> str:
    swatches = (
        ("Cosmic Black", "#050507", "cosmic-dot-black"),
        ("Deep Space", "#0E0F14", "cosmic-dot-space"),
        ("Soft White", "#F5F6F8", "cosmic-dot-white"),
        ("Stardust Gold", "#F5D28A", "cosmic-dot-gold"),
        ("Night Purple", "#1A1C2A", "cosmic-dot-purple"),
    )
    return (
        "<div class='cosmic-identity-card cosmic-identity-colors'>"
        "<div class='cosmic-identity-card-label'>COLOR</div>"
        "<div class='cosmic-swatches'>"
        + "".join(
            (
                "<div class='cosmic-swatch'>"
                f"<span class='cosmic-dot {escape(css_class)}'></span>"
                "<div>"
                f"<div class='cosmic-swatch-name'>{escape(label)}</div>"
                f"<div class='cosmic-swatch-value'>{escape(value)}</div>"
                "</div>"
                "</div>"
            )
            for label, value, css_class in swatches
        )
        + "</div>"
        "<div class='cosmic-gradient-bar'></div>"
        "</div>"
    )

def _render_cosmic_component_gallery() -> str:
    return (
        "<div class='cosmic-identity-card cosmic-identity-components'>"
        "<div class='cosmic-identity-card-label'>UI COMPONENTS</div>"
        "<div class='cosmic-component-row'>"
        "<span class='cosmic-chip cosmic-chip-primary'>BUTTON</span>"
        "<span class='cosmic-chip cosmic-chip-secondary'>CANCEL</span>"
        "<span class='cosmic-chip cosmic-chip-ghost'>MORE</span>"
        "</div>"
        "<div class='cosmic-toggle-row'>"
        "<span class='cosmic-toggle cosmic-toggle-off'><span></span></span>"
        "<span class='cosmic-toggle cosmic-toggle-on'><span></span></span>"
        "</div>"
        "<div class='cosmic-tag-block'>"
        "<div class='cosmic-identity-card-label cosmic-inline-label'>TAGS</div>"
        "<div class='cosmic-tag-row'>"
        "<span class='cosmic-tag cosmic-tag-gold'>BLACK HOLE</span>"
        "<span class='cosmic-tag cosmic-tag-violet'>JUPITER</span>"
        "<span class='cosmic-tag cosmic-tag-teal'>ORBIT</span>"
        "<span class='cosmic-tag'>CARDS</span>"
        "</div>"
        "</div>"
        "</div>"
    )

def _render_cosmic_data_display() -> str:
    return (
        "<div class='cosmic-identity-card cosmic-identity-data'>"
        "<div class='cosmic-identity-card-label'>DATA DISPLAY</div>"
        "<div class='cosmic-data-grid'>"
        "<div class='cosmic-data-card'><div class='cosmic-data-label'>ENERGY</div><div class='cosmic-ring'>87%</div></div>"
        "<div class='cosmic-data-card'><div class='cosmic-data-label'>SLIDER</div><div class='cosmic-slider'><span></span></div><div class='cosmic-data-value'>72%</div></div>"
        "</div>"
        "<div class='cosmic-icon-row'>"
        "<span class='cosmic-icon'>ICON</span>"
        "<span class='cosmic-icon'>BLACK HOLE</span>"
        "<span class='cosmic-icon'>GRAVITY RING</span>"
        "<span class='cosmic-icon'>NEBULA DUST</span>"
        "</div>"
        "</div>"
    )

def _render_cosmic_visual_elements() -> str:
    visuals = (
        ("BLACK HOLE", "cosmic-visual-black-hole"),
        ("GRAVITY RING", "cosmic-visual-gravity-ring"),
        ("LIGHT GLOW", "cosmic-visual-light-glow"),
        ("NEBULA DUST", "cosmic-visual-nebula-dust"),
        ("GLASS SURFACE", "cosmic-visual-glass-surface"),
    )
    return (
        "<div class='cosmic-identity-card cosmic-identity-visuals'>"
        "<div class='cosmic-identity-card-label'>VISUAL ELEMENTS</div>"
        "<div class='cosmic-visual-tiles'>"
        + "".join(
            (
                "<div class='cosmic-visual-tile "
                f"{escape(css_class)}'>"
                "<span class='cosmic-visual-tile-glow'></span>"
                f"<span class='cosmic-visual-tile-label'>{escape(label)}</span>"
                "</div>"
            )
            for label, css_class in visuals
        )
        + "</div>"
        "</div>"
    )

def render_cosmic_identity_panel() -> str:
    return (
        "<section class='cosmic-identity-panel'>"
        "<div class='cosmic-identity-copy'>"
        "<div class='cosmic-identity-kicker'>DESIGN SYSTEM</div>"
        "<div class='cosmic-identity-title'>COSMIC GRAVITY</div>"
        "<div class='cosmic-identity-subtitle'>A control surface for the trading engine, composed as a black-gold instrument panel with dense data, soft glow, and orbit-like hierarchy.</div>"
        "</div>"
        "<div class='cosmic-identity-grid'>"
        f"{_render_cosmic_color_swatches()}"
        f"{_render_cosmic_component_gallery()}"
        f"{_render_cosmic_data_display()}"
        f"{_render_cosmic_visual_elements()}"
        "</div>"
        "</section>"
    )
