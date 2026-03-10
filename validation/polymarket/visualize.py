#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polymarket Backtest Visualization — Brier Score comparison chart.
"""
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Colors
BG = (15, 20, 35)
PANEL_BG = (20, 28, 48)
PANEL_BORDER = (40, 55, 85)
TEXT = (220, 225, 235)
MUTED = (120, 130, 150)
AGENT_COLOR = (46, 204, 113)   # Green
MARKET_COLOR = (52, 152, 219)  # Blue
WIN_HIGHLIGHT = (241, 196, 15) # Yellow


def generate_comparison_chart(report_path: str, output_path: str = "validation/polymarket/results/brier_comparison.png"):
    """Generate side-by-side Brier Score comparison chart."""
    with open(report_path, "r") as f:
        report = json.load(f)

    results = report["results"]
    summary = report["summary"]

    # Layout
    W = 1000
    bar_h = 40
    bar_gap = 12
    top_margin = 140
    left_margin = 320
    right_margin = 80
    H = top_margin + len(results) * (bar_h + bar_gap) + 160

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Fonts
    font_sm = ImageFont.load_default()
    font_md = ImageFont.load_default()
    font_lg = ImageFont.load_default()
    font_title = ImageFont.load_default()
    try:
        for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
            if os.path.exists(fp):
                font_sm = ImageFont.truetype(fp, 12)
                font_md = ImageFont.truetype(fp, 14)
                font_lg = ImageFont.truetype(fp, 18)
                font_title = ImageFont.truetype(fp, 24)
                break
    except:
        pass

    # Header
    draw.rectangle([(0, 0), (W, 80)], fill=PANEL_BG)
    draw.line([(0, 80), (W, 80)], fill=PANEL_BORDER, width=2)
    draw.text((25, 12), "🎯 Agent Credibility Validation", fill=(100, 180, 255), font=font_title)
    draw.text((25, 42), f"Polymarket Backtesting | {summary['markets_tested']} resolved markets | Brier Score comparison",
              fill=MUTED, font=font_md)

    # Legend
    draw.rectangle([(25, 90), (45, 106)], fill=AGENT_COLOR)
    draw.text((50, 90), "Agent", fill=TEXT, font=font_md)
    draw.rectangle([(120, 90), (140, 106)], fill=MARKET_COLOR)
    draw.text((145, 90), "Market Consensus", fill=TEXT, font=font_md)
    draw.text((320, 90), "(Lower Brier Score = Better Prediction)", fill=MUTED, font=font_sm)

    # Find max brier for scaling
    max_brier = max(
        max(r["agent_brier"] for r in results),
        max(r["market_brier"] for r in results),
        0.01
    )
    bar_area = W - left_margin - right_margin

    # Bars
    for i, r in enumerate(results):
        y = top_margin + i * (bar_h + bar_gap)
        question = r["question"][:38]

        # Label
        draw.text((10, y + 2), question, fill=TEXT, font=font_md)
        # Outcome badge
        outcome_text = r["outcome"][:6]
        draw.text((10, y + 20), f"→ {outcome_text}", fill=MUTED, font=font_sm)

        # Agent bar (top half)
        agent_w = max(2, int(bar_area * r["agent_brier"] / max_brier))
        draw.rounded_rectangle(
            [(left_margin, y), (left_margin + agent_w, y + bar_h // 2 - 1)],
            radius=3, fill=AGENT_COLOR
        )

        # Market bar (bottom half)
        market_w = max(2, int(bar_area * r["market_brier"] / max_brier))
        draw.rounded_rectangle(
            [(left_margin, y + bar_h // 2 + 1), (left_margin + market_w, y + bar_h)],
            radius=3, fill=MARKET_COLOR
        )

        # Score labels
        draw.text((left_margin + agent_w + 5, y + 1),
                  f"{r['agent_brier']:.4f}", fill=AGENT_COLOR, font=font_sm)
        draw.text((left_margin + market_w + 5, y + bar_h // 2 + 2),
                  f"{r['market_brier']:.4f}", fill=MARKET_COLOR, font=font_sm)

        # Winner indicator
        if "Agent" in r["winner"]:
            draw.text((W - 70, y + 10), "🤖 ✓", fill=AGENT_COLOR, font=font_md)

    # Summary boxes
    box_y = top_margin + len(results) * (bar_h + bar_gap) + 20
    boxes = [
        ("Agent Avg Brier", f"{summary['agent_avg_brier']:.4f}", AGENT_COLOR),
        ("Market Avg Brier", f"{summary['market_avg_brier']:.4f}", MARKET_COLOR),
        ("Agent Win Rate", f"{summary['win_rate']:.0%}", AGENT_COLOR if summary['win_rate'] > 0.5 else MARKET_COLOR),
        ("Improvement", f"{summary['improvement']:.1%}", AGENT_COLOR if summary['improvement'] > 0 else (231, 76, 60)),
    ]

    box_w = (W - 50) // len(boxes) - 10
    for i, (label, value, color) in enumerate(boxes):
        bx = 25 + i * (box_w + 10)
        draw.rounded_rectangle(
            [(bx, box_y), (bx + box_w, box_y + 65)],
            radius=8, fill=PANEL_BG, outline=PANEL_BORDER
        )
        draw.text((bx + 12, box_y + 8), label, fill=MUTED, font=font_sm)
        draw.text((bx + 12, box_y + 28), value, fill=color, font=font_lg)

    # Bottom note
    note_y = box_y + 80
    draw.text((25, note_y), "Current: rule-based agent (momentum + mean reversion) | Next: LLM-powered agent with news processing",
              fill=MUTED, font=font_sm)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, quality=95)
    print(f"📊 Chart saved: {output_path} ({os.path.getsize(output_path)/1024:.0f} KB)")
    return output_path


if __name__ == "__main__":
    generate_comparison_chart("validation/polymarket/results/backtest_report.json")
