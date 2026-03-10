#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supply Chain Simulation Statistics — Bar Chart Dashboard
Similar to CareLoop's event statistics page.
"""
from PIL import Image, ImageDraw, ImageFont
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simulation.engine import SupplyChainEngine

# ── Colors ──
BG = (15, 20, 35)
PANEL_BG = (20, 28, 48)
PANEL_BORDER = (40, 55, 85)
TEXT = (220, 225, 235)
MUTED = (120, 130, 150)
GRID_LINE = (30, 40, 60)

# Bar colors per event type
EVENT_COLORS = {
    "demand":           (52, 152, 219),   # Blue
    "shipment":         (46, 204, 113),   # Green
    "reorder":          (155, 89, 182),   # Purple
    "emergency_reorder":(241, 196, 15),   # Yellow
    "stockout":         (231, 76, 60),    # Red
    "disruption":       (255, 80, 80),    # Bright red
    "recovery":         (26, 188, 156),   # Teal
}

EVENT_LABELS = {
    "demand":           "Sales Fulfilled",
    "shipment":         "Shipments Arrived",
    "reorder":          "Reorder Decisions",
    "emergency_reorder":"Emergency Reorders",
    "stockout":         "Stockout Events",
    "disruption":       "Disruptions",
    "recovery":         "Recoveries",
}

EVENT_ICONS = {
    "demand":           "🛒",
    "shipment":         "📦",
    "reorder":          "🔄",
    "emergency_reorder":"🚨",
    "stockout":         "❌",
    "disruption":       "🔥",
    "recovery":         "✅",
}


def generate_stats_chart(engine: SupplyChainEngine, output_path: str = "docs/assets/stats_chart.png"):
    """
    Generate a CareLoop-style bar chart showing event counts.
    """
    # ── Count events ──
    event_counts = defaultdict(int)
    for e in engine.events_log:
        event_counts[e.event_type] += 1

    # Count decisions separately
    decision_counts = defaultdict(int)
    for d in engine.decisions_log:
        decision_counts[d.action] += 1

    # Merge into display data
    display_data = []
    for etype in ["demand", "shipment", "reorder", "emergency_reorder", "stockout", "disruption", "recovery"]:
        count = event_counts.get(etype, 0) + decision_counts.get(etype, 0)
        if count > 0 or etype in ("stockout", "disruption", "emergency_reorder"):
            display_data.append({
                "type": etype,
                "label": EVENT_LABELS.get(etype, etype),
                "icon": EVENT_ICONS.get(etype, "•"),
                "count": count,
                "color": EVENT_COLORS.get(etype, (100, 100, 100)),
            })

    # ── Layout ──
    W = 900
    bar_height = 52
    bar_gap = 14
    top_margin = 120
    left_margin = 220
    right_margin = 100
    chart_height = len(display_data) * (bar_height + bar_gap) + top_margin + 80
    H = max(500, chart_height)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Load font
    font_sm = ImageFont.load_default()
    font_md = ImageFont.load_default()
    font_lg = ImageFont.load_default()
    font_title = ImageFont.load_default()
    try:
        for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
            if os.path.exists(fp):
                font_sm = ImageFont.truetype(fp, 13)
                font_md = ImageFont.truetype(fp, 16)
                font_lg = ImageFont.truetype(fp, 20)
                font_title = ImageFont.truetype(fp, 26)
                break
    except Exception:
        pass

    # ── Header ──
    draw.rectangle([(0, 0), (W, 70)], fill=PANEL_BG)
    draw.line([(0, 70), (W, 70)], fill=PANEL_BORDER, width=2)
    draw.text((25, 15), "⚡ LevyFly", fill=(100, 180, 255), font=font_title)
    draw.text((190, 20), "Simulation Event Statistics", fill=MUTED, font=font_lg)
    draw.text((25, 48), f"{len(engine.history)} days  •  {sum(d['count'] for d in display_data)} total events  •  {len(engine.decisions_log)} agent decisions", fill=MUTED, font=font_sm)

    # ── Subtitle ──
    draw.text((25, 85), "Event Distribution", fill=TEXT, font=font_lg)

    # ── Bar chart ──
    max_count = max(d["count"] for d in display_data) if display_data else 1
    bar_area_width = W - left_margin - right_margin

    # Grid lines
    for i in range(5):
        val = int(max_count * i / 4)
        x = left_margin + int(bar_area_width * i / 4)
        draw.line([(x, top_margin - 5), (x, top_margin + len(display_data) * (bar_height + bar_gap))],
                  fill=GRID_LINE, width=1)
        draw.text((x - 10, top_margin - 18), str(val), fill=MUTED, font=font_sm)

    for i, item in enumerate(display_data):
        y = top_margin + i * (bar_height + bar_gap)

        # Label (left side)
        label = f"{item['icon']} {item['label']}"
        draw.text((15, y + 14), label, fill=TEXT, font=font_md)

        # Bar
        bar_width = int(bar_area_width * item["count"] / max_count) if max_count > 0 else 0
        bar_width = max(bar_width, 4)  # minimum visible

        # Bar background (subtle)
        draw.rectangle(
            [(left_margin, y + 6), (left_margin + bar_area_width, y + bar_height - 6)],
            fill=(25, 32, 50)
        )

        # Bar fill with gradient effect
        color = item["color"]
        for offset in range(bar_width):
            # Slight gradient: brighter at top
            pct = offset / max(1, bar_width)
            draw.rectangle(
                [(left_margin + offset, y + 6), (left_margin + offset + 1, y + bar_height - 6)],
                fill=color
            )

        # Rounded cap
        if bar_width > 8:
            draw.rounded_rectangle(
                [(left_margin, y + 6), (left_margin + bar_width, y + bar_height - 6)],
                radius=6, fill=color
            )

        # Count label (on or after bar)
        count_text = str(item["count"])
        bbox = draw.textbbox((0, 0), count_text, font=font_lg)
        tw = bbox[2] - bbox[0]

        if bar_width > tw + 20:
            # Inside bar
            draw.text((left_margin + bar_width - tw - 12, y + 12), count_text,
                      fill=(255, 255, 255), font=font_lg)
        else:
            # After bar
            draw.text((left_margin + bar_width + 8, y + 12), count_text,
                      fill=color, font=font_lg)

    # ── Bottom summary boxes ──
    box_y = top_margin + len(display_data) * (bar_height + bar_gap) + 20
    summary = engine.get_summary_report()

    boxes = [
        ("Fill Rate", f"{summary['avg_fill_rate']:.1%}",
         (46, 204, 113) if summary['avg_fill_rate'] > 0.95 else (231, 76, 60)),
        ("Stockouts", str(summary['total_stockout_events']),
         (231, 76, 60) if summary['total_stockout_events'] > 0 else (46, 204, 113)),
        ("Decisions", str(summary['total_decisions']), (155, 89, 182)),
        ("Disruptions", str(summary['disruption_events']), (255, 80, 80)),
    ]

    box_w = (W - 50) // len(boxes) - 10
    for i, (label, value, color) in enumerate(boxes):
        bx = 25 + i * (box_w + 10)
        draw.rounded_rectangle(
            [(bx, box_y), (bx + box_w, box_y + 65)],
            radius=8, fill=PANEL_BG, outline=PANEL_BORDER
        )
        draw.text((bx + 15, box_y + 8), label, fill=MUTED, font=font_sm)
        draw.text((bx + 15, box_y + 28), value, fill=color, font=font_lg)

    # ── Save ──
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, quality=95)
    print(f"📊 Stats chart saved: {output_path} ({os.path.getsize(output_path) / 1024:.0f} KB)")
    return output_path


if __name__ == "__main__":
    from simulation.network import build_demo_network
    from simulation.engine import SupplyChainEngine

    network = build_demo_network()
    engine = SupplyChainEngine(network, seed=42)
    engine.run(days=30, disruptions=[
        {"day": 8, "node_id": "S1", "duration": 12, "description": "Factory fire"},
        {"day": 18, "node_id": "S2", "duration": 5, "description": "Flooding"},
    ])
    generate_stats_chart(engine)
