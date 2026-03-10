#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LevyFly Supply Chain Simulation — End-to-End Demo

Usage:
  python run_demo.py                    # Run with built-in demo network
  python run_demo.py --data ./data/     # Load from CSV files in directory
  python run_demo.py --data ./data/ --days 60 --no-gif
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulation.network import build_demo_network
from simulation.engine import SupplyChainEngine
from simulation.csv_loader import load_from_directory
from simulation.report_generator import ReportGenerator
from visualization.renderer import SupplyChainRenderer
from visualization.stats_chart import generate_stats_chart


def main():
    parser = argparse.ArgumentParser(description="⚡ LevyFly Supply Chain Simulation")
    parser.add_argument("--data", type=str, default=None,
                        help="Path to directory containing CSV files (network.csv, routes.csv, etc.)")
    parser.add_argument("--days", type=int, default=30,
                        help="Number of days to simulate (default: 30)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")
    parser.add_argument("--no-gif", action="store_true",
                        help="Skip GIF generation")
    parser.add_argument("--output", type=str, default="docs/assets",
                        help="Output directory for reports and GIF")
    args = parser.parse_args()

    print("=" * 60)
    print("⚡ LevyFly — Agentic Supply Chain Simulation")
    print("=" * 60)

    # ── Step 1: Load data ──────────────────────────────────────
    if args.data:
        print(f"\n📂 Loading supply chain from: {args.data}")
        network, disruptions = load_from_directory(args.data)
    else:
        print("\n📡 Using built-in demo network...")
        network = build_demo_network()
        disruptions = [
            {"day": 8, "node_id": "S1", "duration": 12,
             "description": "🔥 Sichuan Spice Co. factory fire — production halted for 12 days"},
            {"day": 18, "node_id": "S2", "duration": 5,
             "description": "🌊 Yunnan flooding — fresh produce supply cut for 5 days"},
        ]

    print(f"   Network: {len(network.get_suppliers())}S → {len(network.get_warehouses())}W → {len(network.get_stores())}R")
    print(f"   Routes:  {len(network.edges)}")

    # ── Step 2: Run simulation ────────────────────────────────
    print(f"\n🚀 Simulating {args.days} days...")
    engine = SupplyChainEngine(network, seed=args.seed)

    if disruptions:
        print(f"   Scheduled disruptions:")
        for d in disruptions:
            print(f"     Day {d['day']}: {d.get('description', d['node_id'] + ' disrupted')}")

    snapshots = engine.run(days=args.days, disruptions=disruptions)

    # ── Step 3: Generate report ───────────────────────────────
    print(f"\n📋 Generating report...")
    reporter = ReportGenerator(engine)
    reporter.print_report_summary()

    os.makedirs(args.output, exist_ok=True)
    report_path = os.path.join(args.output, "simulation_report.json")
    reporter.save_report(report_path)
    print(f"\n💾 Full report: {report_path}")

    # ── Step 4: Generate visualization ────────────────────────
    if not args.no_gif:
        print(f"\n🎬 Rendering {len(snapshots)} frames...")
        renderer = SupplyChainRenderer(network)

        frames = []
        for i, snapshot in enumerate(snapshots):
            frame = renderer.render_frame(snapshot)
            frames.append(frame)
            if (i + 1) % 10 == 0:
                print(f"   Rendered {i+1}/{len(snapshots)} frames")

        gif_path = os.path.join(args.output, "supply_chain_sim.gif")
        frames[0].save(
            gif_path, save_all=True, append_images=frames[1:],
            duration=600, loop=0
        )
        file_size = os.path.getsize(gif_path) / 1024
        print(f"\n✅ Animation: {gif_path} ({file_size:.0f} KB)")

    # ── Step 5: Generate stats chart ─────────────────────────
    stats_path = os.path.join(args.output, "stats_chart.png")
    generate_stats_chart(engine, stats_path)

    # ── Done ──────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"✅ End-to-end pipeline complete!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
