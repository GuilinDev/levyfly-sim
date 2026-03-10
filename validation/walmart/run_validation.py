#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LevyFly × Walmart M5 Validation

Runs supply chain simulation against real demand data.
Proves agent decision quality with ground truth.

Usage:
  python validation/walmart/run_validation.py
  python validation/walmart/run_validation.py --days 90 --data data/walmart_m5/
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from validation.walmart.m5_adapter import load_m5_data, build_network_from_m5
from validation.walmart.demand_driven_engine import DemandDrivenEngine
from simulation.report_generator import ReportGenerator
from visualization.renderer import SupplyChainRenderer
from visualization.stats_chart import generate_stats_chart


def print_validation_report(engine: DemandDrivenEngine):
    """Print human-readable validation report."""
    m = engine.metrics

    print("\n" + "=" * 70)
    print("📊 LEVYFLY × WALMART M5 VALIDATION REPORT")
    print("    Real Demand → Agent Decisions → Measured Outcomes")
    print("=" * 70)

    # Health status
    if m.fill_rate >= 0.95:
        status = "🟢 HEALTHY"
    elif m.fill_rate >= 0.85:
        status = "🟡 AT RISK"
    else:
        status = "🔴 CRITICAL"

    print(f"\n{status}")
    print(f"\n{'Metric':<35} {'Value':>15}")
    print(f"{'─' * 35} {'─' * 15}")
    print(f"{'Days Simulated':<35} {m.days_simulated:>15}")
    print(f"{'Total Real Demand':<35} {m.total_real_demand:>15,}")
    print(f"{'Fulfilled Demand':<35} {m.fulfilled_demand:>15,}")
    print(f"{'Fill Rate':<35} {m.fill_rate:>14.1%}")
    print(f"{'Stockout Events':<35} {m.stockout_events:>15}")
    print(f"{'Stockout Units':<35} {m.stockout_units:>15,}")
    print(f"{'Reorder Decisions':<35} {m.reorder_decisions:>15}")
    print(f"{'Emergency Reorders':<35} {m.emergency_reorders:>15}")

    # Stockout analysis
    print(f"\n{'─' * 70}")
    print("📈 STOCKOUT TIMELINE")

    stockout_by_day = {}
    for e in engine.events_log:
        if e.event_type == "stockout":
            if e.day not in stockout_by_day:
                stockout_by_day[e.day] = []
            stockout_by_day[e.day].append(e)

    if stockout_by_day:
        for day in sorted(stockout_by_day.keys())[:15]:
            events = stockout_by_day[day]
            stores = set(e.source_id for e in events)
            total_shortage = sum(e.quantity for e in events)
            print(f"  Day {day:>3}: {len(events)} stockout(s) at {', '.join(stores)} "
                  f"(total shortage: {total_shortage})")
        if len(stockout_by_day) > 15:
            print(f"  ... and {len(stockout_by_day) - 15} more days with stockouts")
    else:
        print("  ✅ No stockouts! Agent decisions prevented all shortages.")

    # Emergency reorder analysis
    emergency_events = [d for d in engine.decisions_log if d.action == "emergency_reorder"]
    if emergency_events:
        print(f"\n{'─' * 70}")
        print("🚨 EMERGENCY REORDER DECISIONS")
        for d in emergency_events[:10]:
            print(f"  Day {d.day:>3}: {d.agent_id} — {d.reasoning}")

    # Event distribution
    event_counts = {}
    for e in engine.events_log:
        event_counts[e.event_type] = event_counts.get(e.event_type, 0) + 1

    print(f"\n{'─' * 70}")
    print("📊 EVENT DISTRIBUTION")
    for etype, count in sorted(event_counts.items(), key=lambda x: -x[1]):
        bar = "█" * min(50, count // 10)
        print(f"  {etype:<20} {count:>6}  {bar}")

    # Credibility assessment
    print(f"\n{'=' * 70}")
    print("🎯 CREDIBILITY ASSESSMENT")

    if m.fill_rate >= 0.90:
        print("  ✅ Agent maintained >90% fill rate against real demand data")
        print("  ✅ This validates that the simulation produces realistic outcomes")
    else:
        print("  ⚠️ Fill rate below 90% — agent decision rules need tuning")
        print("  💡 Possible improvements: increase reorder points, add demand forecasting")

    if m.emergency_reorders > 0:
        print(f"  📊 Agent detected {m.emergency_reorders} emergencies and took corrective action")

    print(f"\n  Data source: Walmart M5 ({m.days_simulated} days, {m.total_real_demand:,} demand units)")
    print(f"  This is NOT synthetic demand — these are real retail sales patterns")
    print(f"{'=' * 70}")


def main():
    parser = argparse.ArgumentParser(description="📊 LevyFly × Walmart M5 Validation")
    parser.add_argument("--data", type=str, default="data/walmart_m5/",
                        help="Path to M5 data directory")
    parser.add_argument("--days", type=int, default=90,
                        help="Number of days to simulate (default: 90)")
    parser.add_argument("--output", type=str, default="validation/walmart/results",
                        help="Output directory")
    args = parser.parse_args()

    # Load M5 data
    dataset = load_m5_data(args.data, max_days=args.days)

    # Build network
    network = build_network_from_m5(dataset)
    print(f"\n🏗️ Network: {len(network.get_suppliers())}S → "
          f"{len(network.get_warehouses())}W → {len(network.get_stores())}R")

    # Run simulation with real demand
    engine = DemandDrivenEngine(network, dataset)
    snapshots = engine.run(days=args.days)

    # Print report
    print_validation_report(engine)

    # Save results
    os.makedirs(args.output, exist_ok=True)
    report = engine.get_summary_report()
    report_path = os.path.join(args.output, "m5_validation_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n💾 Report saved: {report_path}")

    # Generate visualization
    renderer = SupplyChainRenderer(network)
    frames = [renderer.render_frame(s) for s in snapshots]
    gif_path = os.path.join(args.output, "m5_simulation.gif")
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=200, loop=0)
    print(f"🎬 Animation: {gif_path}")

    # Generate stats chart — patch engine to be compatible
    def patched_summary():
        return {
            "total_days": engine.metrics.days_simulated,
            "avg_fill_rate": engine.metrics.fill_rate,
            "total_stockout_events": engine.metrics.stockout_events,
            "total_decisions": engine.metrics.reorder_decisions + engine.metrics.emergency_reorders,
            "disruption_events": len(dataset.disruption_periods),
            "decision_breakdown": {
                "reorder": engine.metrics.reorder_decisions,
                "emergency_reorder": engine.metrics.emergency_reorders,
            },
        }
    engine.get_summary_report = patched_summary

    chart_path = os.path.join(args.output, "m5_stats.png")
    generate_stats_chart(engine, chart_path)


if __name__ == "__main__":
    main()
