from __future__ import annotations

import math
from datetime import datetime, timedelta
from html import escape

from .dashboard_render_utils import _format_time_short


def _render_line_chart_svg(
    *,
    points: list[dict],
    value_key: str,
    stroke: str,
    fill: str,
    show_grid: bool = True,
    integer_axis: bool = False,
) -> str:
    timestamped_values: list[tuple[datetime, float]] = []
    chart_values: list[float] = []
    for point in points:
        value = point.get(value_key)
        if isinstance(value, (int, float)):
            numeric_value = float(value)
            chart_values.append(numeric_value)
            timestamp = point.get("timestamp")
            if timestamp:
                try:
                    timestamped_values.append((datetime.fromisoformat(timestamp), numeric_value))
                except ValueError:
                    pass
    if not chart_values:
        return "<div class='chart-empty'><span class='chart-empty-icon'>◎</span><span>waiting for data</span></div>"
    values = list(chart_values)
    if len(values) == 1:
        values = [values[0], values[0]]
    data_min = min(values)
    data_max = max(values)
    min_value = data_min
    max_value = data_max
    if max_value == min_value:
        if max_value >= 0:
            min_value = 0.0
            max_value = max(max_value * 1.2, 1.0 if max_value == 0 else max_value * 1.2)
        else:
            min_value = min(max_value * 1.2, -1.0)
            max_value = 0.0
    spread = max(max_value - min_value, 1e-9)
    width = 600
    height = 200
    pad_x = 50
    pad_y = 20
    chart_width = width - pad_x * 2
    chart_height = height - pad_y * 2
    axis_magnitude = max(abs(min_value), abs(max_value), spread)
    original_value_count = len(chart_values)

    def _format_axis_value(value: float) -> str:
        if integer_axis:
            return f"{int(round(value)):,}"
        if axis_magnitude >= 100:
            return f"{value:,.0f}"
        if axis_magnitude >= 10:
            return f"{value:,.1f}"
        if axis_magnitude >= 1:
            return f"{value:,.1f}"
        if axis_magnitude >= 0.1:
            return f"{value:,.2f}"
        return f"{value:,.3f}"

    if integer_axis:
        tick_start = int(math.floor(data_max))
        tick_end = int(math.floor(data_min))
        if tick_start == tick_end:
            tick_start += 1
        tick_step = max(1, math.ceil((tick_start - tick_end) / 4))
        tick_values: list[float] = []
        current_tick = tick_start
        while current_tick >= tick_end:
            tick_values.append(float(current_tick))
            current_tick -= tick_step
        if tick_values[-1] != float(tick_end):
            tick_values.append(float(tick_end))
    else:
        tick_values = [max_value - (spread * i / 4) for i in range(5)]

    timestamp_mode = bool(timestamped_values) and len(timestamped_values) == len(chart_values)
    coordinates: list[tuple[float, float]] = []
    x_axis_ticks: list[tuple[float, str]] = []
    if timestamp_mode:
        raw_min_timestamp = min(timestamp for timestamp, _ in timestamped_values)
        raw_max_timestamp = max(timestamp for timestamp, _ in timestamped_values)
        min_timestamp = raw_min_timestamp
        max_timestamp = raw_max_timestamp
        if raw_min_timestamp == raw_max_timestamp:
            min_timestamp = raw_min_timestamp - timedelta(seconds=30)
            max_timestamp = raw_max_timestamp + timedelta(seconds=30)
            x_axis_ticks = [(pad_x + (chart_width / 2), _format_time_short(raw_min_timestamp.isoformat()))]
        else:
            timestamp_range = raw_max_timestamp - raw_min_timestamp
            for factor in (0.0, 0.5, 1.0):
                tick_timestamp = raw_min_timestamp + (timestamp_range * factor)
                x_axis_ticks.append((pad_x + (chart_width * factor), _format_time_short(tick_timestamp.isoformat())))
        timestamp_spread = max((max_timestamp - min_timestamp).total_seconds(), 1e-9)
        for parsed_timestamp, value in timestamped_values:
            x = pad_x + (((parsed_timestamp - min_timestamp).total_seconds()) / timestamp_spread) * chart_width
            y = pad_y + chart_height - (((value - min_value) / spread) * chart_height)
            coordinates.append((x, y))
    else:
        for index, value in enumerate(values):
            x = pad_x + (chart_width * index / max(len(values) - 1, 1))
            y = pad_y + chart_height - (((value - min_value) / spread) * chart_height)
            coordinates.append((x, y))
        if original_value_count <= 1:
            x_axis_ticks = [(pad_x + (chart_width / 2), "1")]
        else:
            for factor in (0.0, 0.5, 1.0):
                label = str(int(round((original_value_count - 1) * factor)) + 1)
                x_axis_ticks.append((pad_x + (chart_width * factor), label))
    polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
    area = " ".join([f"{coordinates[0][0]:.2f},{height - pad_y:.2f}", polyline, f"{coordinates[-1][0]:.2f},{height - pad_y:.2f}"])
    grid_lines = ""
    if show_grid:
        for tick_value in tick_values:
            y = pad_y + chart_height - (((tick_value - min_value) / spread) * chart_height)
            grid_lines += f"<line x1='{pad_x}' y1='{y:.2f}' x2='{width - pad_x}' y2='{y:.2f}' class='grid-line'/>"
        for i in range(5):
            x = pad_x + (chart_width * i / 4)
            grid_lines += f"<line x1='{x:.2f}' y1='{pad_y}' x2='{x:.2f}' y2='{height - pad_y}' class='grid-line'/>"
    y_labels = ""
    for val in tick_values:
        y = pad_y + chart_height - (((val - min_value) / spread) * chart_height)
        y_labels += f"<text x='{pad_x - 8}' y='{y + 4:.2f}' class='axis-label' text-anchor='end'>{_format_axis_value(val)}</text>"
    x_axis = f"<line x1='{pad_x}' y1='{height - pad_y}' x2='{width - pad_x}' y2='{height - pad_y}' class='x-axis-line'/>"
    for x, label in x_axis_ticks:
        x_axis += f"<text x='{x:.2f}' y='{height - 5}' class='x-axis-label' text-anchor='middle'>{escape(label)}</text>"
    dots = ""
    for x, y in coordinates[-3:]:
        dots += f"<circle cx='{x:.2f}' cy='{y:.2f}' r='4' fill='{stroke}' class='chart-dot'/>"
    return (
        f"<svg viewBox='0 0 {width} {height}' class='chart-svg' role='img' aria-label='{escape(value_key)} chart'>"
        f"<defs><linearGradient id='grad-{escape(value_key)}' x1='0%' y1='0%' x2='0%' y2='100%'>"
        f"<stop offset='0%' stop-color='{stroke}' stop-opacity='0.3'/><stop offset='100%' stop-color='{stroke}' stop-opacity='0.02'/></linearGradient></defs>"
        f"{grid_lines}"
        f"<polygon points='{area}' fill='url(#grad-{escape(value_key)})'></polygon>"
        f"{y_labels}{x_axis}"
        f"<polyline points='{polyline}' fill='none' stroke='{stroke}' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'></polyline>"
        f"{dots}"
        f"</svg>"
    )

def _render_pie_chart_svg(*, data: dict[str, int], colors: list[str] | None = None) -> str:
    if not data:
        return "<div class='chart-empty'><span class='chart-empty-icon'>◎</span><span>no data</span></div>"
    default_colors = ["#4cc9f0", "#36d98a", "#ffbc42", "#ff5d73", "#a855f7", "#ec4899", "#f97316", "#14b8a6"]
    colors = colors or default_colors
    total = sum(data.values())
    size = 160
    cx, cy = size / 2, size / 2
    r = size / 2 - 20
    paths = ""
    legend = ""
    start_angle = -90
    for i, (label, count) in enumerate(sorted(data.items(), key=lambda x: -x[1])):
        angle = (count / total) * 360
        end_angle = start_angle + angle
        x1 = cx + r * _cos_deg(start_angle)
        y1 = cy + r * _sin_deg(start_angle)
        x2 = cx + r * _cos_deg(end_angle)
        y2 = cy + r * _sin_deg(end_angle)
        large_arc = 1 if angle > 180 else 0
        color = colors[i % len(colors)]
        paths += f"<path d='M{cx},{cy} L{x1:.2f},{y1:.2f} A{r},{r} 0 {large_arc},1 {x2:.2f},{y2:.2f} Z' fill='{color}' class='pie-slice'/>"
        legend += f"<div class='legend-item'><span class='legend-color' style='background:{color}'></span><span class='legend-label'>{escape(label)}</span><span class='legend-value'>{count}</span></div>"
        start_angle = end_angle
    return f"<div class='pie-container'><svg viewBox='0 0 {size} {size}' class='pie-svg'>{paths}</svg><div class='pie-legend'>{legend}</div></div>"

def _cos_deg(angle: float) -> float:
    import math

    return math.cos(math.radians(angle))

def _sin_deg(angle: float) -> float:
    import math

    return math.sin(math.radians(angle))

def _render_bar_chart_svg(*, data: dict[str, int], color: str = "#4cc9f0") -> str:
    if not data:
        return "<div class='chart-empty'><span class='chart-empty-icon'>◎</span><span>no data</span></div>"
    width = 400
    height = 180
    pad_x = 60
    pad_y = 20
    bar_width = max(20, (width - pad_x * 2) / len(data) - 8)
    max_val = max(data.values())
    bars = ""
    labels = ""
    for i, (label, val) in enumerate(sorted(data.items())):
        x = pad_x + i * (bar_width + 8)
        bar_height = (val / max_val) * (height - pad_y * 2 - 20) if max_val > 0 else 0
        y = height - pad_y - bar_height
        bars += f"<rect x='{x:.2f}' y='{y:.2f}' width='{bar_width:.2f}' height='{bar_height:.2f}' fill='{color}' rx='4' class='bar-rect'/>"
        bars += f"<text x='{x + bar_width/2:.2f}' y='{y - 6:.2f}' class='bar-value' text-anchor='middle'>{val}</text>"
        short_label = label[:10] + "..." if len(label) > 10 else label
        labels += f"<text x='{x + bar_width/2:.2f}' y='{height - 6:.2f}' class='bar-label' text-anchor='middle' transform='rotate(-30 {x + bar_width/2:.2f},{height - 6:.2f})'>{escape(short_label)}</text>"
    return f"<svg viewBox='0 0 {width} {height}' class='bar-svg'>{bars}{labels}</svg>"

def _render_timeline_svg(*, events: list[dict]) -> str:
    if not events:
        return "<div class='chart-empty'><span class='chart-empty-icon'>◎</span><span>no events</span></div>"
    width = 600
    height = 120
    pad = 40
    line_y = height / 2
    timeline = f"<line x1='{pad}' y1='{line_y}' x2='{width - pad}' y2='{line_y}' class='timeline-line'/>"
    step = (width - pad * 2) / max(len(events) - 1, 1)
    for i, event in enumerate(events[:10]):
        x = pad + i * step
        symbol = event.get("symbol", "?")
        timestamp = event.get("timestamp", "")
        is_current = i == len(events[:10]) - 1
        color = "#4cc9f0" if is_current else "#36d98a" if i % 2 == 0 else "#ffbc42"
        radius = 12 if is_current else 8
        timeline += f"<circle cx='{x:.2f}' cy='{line_y:.2f}' r='{radius}' fill='{color}' class='timeline-dot{' current' if is_current else ''}'/>"
        timeline += f"<text x='{x:.2f}' y='{line_y - 22:.2f}' class='timeline-label' text-anchor='middle'>{escape(str(symbol))}</text>"
        if timestamp:
            short_time = _format_time_short(timestamp)
            timeline += f"<text x='{x:.2f}' y='{line_y + 28:.2f}' class='timeline-time' text-anchor='middle'>{escape(short_time)}</text>"
    return f"<svg viewBox='0 0 {width} {height}' class='timeline-svg'>{timeline}</svg>"
