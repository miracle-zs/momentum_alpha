from __future__ import annotations


def _render_dashboard_base_styles() -> str:
    return (
        ".dashboard-tab { display: inline-flex; }\n"
        ".dashboard-tab.is-active { color: var(--fg); }\n"
        ".action-button { cursor: pointer; }\n"
    )
