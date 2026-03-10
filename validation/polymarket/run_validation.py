#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LevyFly Agent Credibility Validation — Polymarket Backtesting

Proves agent prediction reliability using real-world prediction markets.
Ground truth comes from resolved Polymarket events.

Usage:
  python validation/polymarket/run_validation.py
  python validation/polymarket/run_validation.py --count 20
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from validation.polymarket.fetcher import PolymarketFetcher
from validation.polymarket.backtester import run_full_backtest, SimpleAgent


def print_report(report: dict):
    """Print a human-readable validation report."""
    s = report["summary"]

    print("\n" + "=" * 70)
    print("🎯 LEVYFLY AGENT CREDIBILITY REPORT")
    print("    Polymarket Backtesting Validation")
    print("=" * 70)

    print(f"\n📊 Markets Tested: {s['markets_tested']}")
    print(f"\n{'Metric':<30} {'Agent':>12} {'Market':>12}")
    print(f"{'─' * 30} {'─' * 12} {'─' * 12}")
    print(f"{'Avg Brier Score':<30} {s['agent_avg_brier']:>12.4f} {s['market_avg_brier']:>12.4f}")
    print(f"{'Wins':<30} {s['agent_wins']:>12} {s['market_wins']:>12}")
    print(f"{'Win Rate':<30} {s['win_rate']:>11.0%} {1 - s['win_rate']:>11.0%}")

    improvement = s['improvement']
    if improvement > 0:
        print(f"\n✅ Agent outperforms market consensus by {improvement:.1%}")
    elif improvement < 0:
        print(f"\n📊 Market consensus outperforms agent by {abs(improvement):.1%}")
    else:
        print(f"\n🤝 Agent matches market consensus")

    print(f"\n{'─' * 70}")
    print(f"{'Market':<42} {'Outcome':>8} {'Agent':>8} {'Market':>8} {'Winner':>10}")
    print(f"{'─' * 42} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 10}")

    for r in report["results"]:
        q = r["question"][:40]
        print(f"{q:<42} {r['outcome']:>8} {r['agent_brier']:>8.4f} {r['market_brier']:>8.4f} {r['winner']:>10}")

    # Interpretation
    print(f"\n{'=' * 70}")
    print("📖 HOW TO READ THIS:")
    print("   Brier Score: 0.0 = perfect prediction, 1.0 = worst possible")
    print("   Lower is better. Agent vs Market shows who predicted more accurately.")
    print("   Current agent: rule-based (momentum + mean reversion)")
    print("   Next step: LLM-powered agent with news/information processing")
    print(f"{'=' * 70}")


def main():
    parser = argparse.ArgumentParser(description="🎯 LevyFly Agent Credibility Validation")
    parser.add_argument("--count", type=int, default=10,
                        help="Number of resolved markets to test (default: 10)")
    parser.add_argument("--output", type=str, default="validation/polymarket/results",
                        help="Output directory for results")
    args = parser.parse_args()

    # Fetch data
    fetcher = PolymarketFetcher()
    dataset = fetcher.fetch_resolved_dataset(count=args.count)

    if not dataset:
        print("❌ No markets fetched. Check network connection.")
        return

    # Run backtest
    print(f"\n🧪 Running backtest on {len(dataset)} markets...")
    agent = SimpleAgent(lookback=5)
    report = run_full_backtest(dataset, agent)

    # Print report
    print_report(report)

    # Save results
    os.makedirs(args.output, exist_ok=True)
    output_path = os.path.join(args.output, "backtest_report.json")
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n💾 Full report saved: {output_path}")


if __name__ == "__main__":
    main()
