#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LevyFly — Cross-Domain Demonstration
Runs the SAME simulation engine across 3 different industries.
Proves framework extensibility: swap CSV config, same code.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulation.csv_loader import load_from_directory
from simulation.engine import SupplyChainEngine
from simulation.report_generator import ReportGenerator
from visualization.renderer import SupplyChainRenderer
from visualization.stats_chart import generate_stats_chart


DOMAINS = [
    {
        "name": "🍜 Retail Supply Chain",
        "data_dir": "data/",
        "output_dir": "docs/assets/retail",
        "days": 30,
    },
    {
        "name": "🏥 Healthcare Supply Chain",
        "data_dir": "data/healthcare/",
        "output_dir": "docs/assets/healthcare",
        "days": 30,
    },
    {
        "name": "💹 Financial Data Pipeline",
        "data_dir": "data/finance/",
        "output_dir": "docs/assets/finance",
        "days": 30,
    },
]


def run_domain(domain: dict):
    """Run simulation for a single domain."""
    print(f"\n{'─' * 60}")
    print(f"  {domain['name']}")
    print(f"{'─' * 60}")

    # Load
    network, disruptions = load_from_directory(domain["data_dir"])

    # Simulate
    engine = SupplyChainEngine(network, seed=42)
    snapshots = engine.run(days=domain["days"], disruptions=disruptions)

    # Report
    reporter = ReportGenerator(engine)
    os.makedirs(domain["output_dir"], exist_ok=True)

    report = reporter.generate_full_report()
    es = report["executive_summary"]

    print(f"\n   Status:      {es['health_status']}")
    print(f"   Fill Rate:   {es['fill_rate']:.1%}")
    print(f"   Stockouts:   {es['stockouts']}")
    print(f"   Disruptions: {es['disruptions']}")
    print(f"   Risks:       {report['risk_analysis']['total_risks']}")
    print(f"   Recs:        {len(report['recommendations'])}")

    reporter.save_report(os.path.join(domain["output_dir"], "report.json"))

    # Visualize
    renderer = SupplyChainRenderer(network)
    frames = [renderer.render_frame(s) for s in snapshots]
    gif_path = os.path.join(domain["output_dir"], "simulation.gif")
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=600, loop=0)
    print(f"   GIF: {gif_path}")

    # Stats chart
    chart_path = os.path.join(domain["output_dir"], "stats.png")
    generate_stats_chart(engine, chart_path)

    return report


def main():
    print("=" * 60)
    print("⚡ LevyFly — Cross-Domain Extensibility Demo")
    print("   Same engine. Different configs. Three industries.")
    print("=" * 60)

    results = {}
    for domain in DOMAINS:
        report = run_domain(domain)
        results[domain["name"]] = report

    # Summary comparison
    print(f"\n\n{'=' * 60}")
    print("📊 CROSS-DOMAIN COMPARISON")
    print(f"{'=' * 60}")
    print(f"\n{'Domain':<30} {'Fill Rate':>10} {'Stockouts':>10} {'Risks':>8} {'Recs':>6}")
    print(f"{'─' * 30} {'─' * 10} {'─' * 10} {'─' * 8} {'─' * 6}")
    for name, report in results.items():
        es = report["executive_summary"]
        ra = report["risk_analysis"]
        print(f"{name:<30} {es['fill_rate']:>9.1%} {es['stockouts']:>10} {ra['total_risks']:>8} {len(report['recommendations']):>6}")

    print(f"\n✅ All domains simulated with ZERO code changes.")
    print(f"   Only CSV configuration files differ.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
