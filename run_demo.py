#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LevyFly Supply Chain Simulation — Demo Runner
Generates animated GIF of a 30-day supply chain simulation
with a disruption event on Day 12.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulation.network import build_demo_network
from simulation.engine import SupplyChainEngine
from visualization.renderer import SupplyChainRenderer


def run_demo():
    print("=" * 60)
    print("⚡ LevyFly — Supply Chain Simulation Demo")
    print("=" * 60)

    # 1. Build network
    print("\n📡 Building supply chain network...")
    network = build_demo_network()
    print(f"   Suppliers:  {len(network.get_suppliers())}")
    print(f"   Warehouses: {len(network.get_warehouses())}")
    print(f"   Stores:     {len(network.get_stores())}")
    print(f"   Routes:     {len(network.edges)}")

    # 2. Initialize engine
    print("\n🔧 Initializing simulation engine...")
    engine = SupplyChainEngine(network, seed=42)

    # 3. Define disruption scenario
    disruptions = [
        {
            "day": 8,
            "node_id": "S1",
            "duration": 12,
            "description": "🔥 Sichuan Spice Co. factory fire — production halted for 12 days"
        },
        {
            "day": 18,
            "node_id": "S2",
            "duration": 5,
            "description": "🌊 Yunnan flooding — fresh produce supply cut for 5 days"
        }
    ]
    print(f"\n⚠️  Scheduled disruptions:")
    for d in disruptions:
        print(f"   Day {d['day']}: {d['description']}")

    # 4. Run simulation
    print(f"\n🚀 Running 30-day simulation...")
    snapshots = engine.run(days=30, disruptions=disruptions)

    # 5. Generate report
    report = engine.get_summary_report()
    print(f"\n📊 Simulation Complete!")
    print(f"   Average Fill Rate: {report['avg_fill_rate']:.1%}")
    print(f"   Lowest Fill Rate:  {report['min_fill_rate']:.1%} (Day {report['min_fill_rate_day']})")
    print(f"   Stockout Events:   {report['total_stockout_events']}")
    print(f"   Total Orders:      {report['total_orders']}")
    print(f"   Agent Decisions:   {report['total_decisions']}")
    print(f"   Decision Types:    {report['decision_breakdown']}")

    # 6. Save report JSON
    os.makedirs("docs/assets", exist_ok=True)
    report_path = "docs/assets/simulation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n💾 Report saved to {report_path}")

    # 7. Render animation
    print(f"\n🎬 Rendering {len(snapshots)} frames...")
    renderer = SupplyChainRenderer(network)

    frames = []
    for i, snapshot in enumerate(snapshots):
        frame = renderer.render_frame(snapshot)
        frames.append(frame)
        if (i + 1) % 10 == 0:
            print(f"   Rendered {i+1}/{len(snapshots)} frames")

    # 8. Save GIF
    gif_path = "docs/assets/supply_chain_sim.gif"
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=600,  # 600ms per frame
        loop=0
    )
    file_size = os.path.getsize(gif_path) / 1024
    print(f"\n✅ Animation saved: {gif_path} ({file_size:.0f} KB)")

    # 9. Print key events timeline
    print(f"\n📅 Key Events Timeline:")
    for snapshot in snapshots:
        critical = [e for e in snapshot.events if e.severity in ("warning", "critical")]
        emergency = [d for d in snapshot.decisions if d.action == "emergency_reorder"]
        if critical or emergency:
            print(f"\n   Day {snapshot.day}:")
            for e in critical:
                print(f"     {e.description}")
            for d in emergency:
                print(f"     🤖 {d.agent_id}: {d.reasoning}")

    print(f"\n{'=' * 60}")
    print(f"Demo complete. Files generated:")
    print(f"  📊 {report_path}")
    print(f"  🎬 {gif_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run_demo()
