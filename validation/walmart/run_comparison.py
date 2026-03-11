#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Policy Comparison — Fair A/B Testing on Real M5 Data

Runs multiple inventory policies on the same demand data
and compares fill rates, stockouts, and excess inventory.

Usage:
  python validation/walmart/run_comparison.py --days 90
"""
import os
import sys
import json
import copy
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from validation.walmart.m5_adapter import load_m5_data, build_network_from_m5
from validation.walmart.policy_engine import PolicyDrivenEngine
from validation.walmart.policies import (
    NaivePolicy, SQPolicy, SSPolicy, AdaptiveSQPolicy, AIPolicy
)


def run_policy(dataset, policy, days, label):
    """Run a single policy and return results."""
    # Build fresh network for each run
    network = build_network_from_m5(dataset)
    engine = PolicyDrivenEngine(network, dataset, policy)
    engine.run(days=days, quiet=True)
    m = engine.metrics

    return {
        "policy": label,
        "fill_rate": round(m.fill_rate, 4),
        "total_demand": m.total_real_demand,
        "fulfilled": m.fulfilled_demand,
        "stockouts": m.stockout_events,
        "stockout_units": m.stockout_units,
        "reorders": m.reorder_decisions,
        "emergency_reorders": m.emergency_reorders,
    }


def main():
    parser = argparse.ArgumentParser(description="📊 Policy Comparison on M5 Data")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--data", type=str, default="data/walmart_m5/")
    parser.add_argument("--output", type=str, default="validation/walmart/results")
    args = parser.parse_args()

    # Load data once
    dataset = load_m5_data(args.data, max_days=args.days)

    # Calculate demand-based params for fair comparison
    from collections import defaultdict
    product_daily = defaultdict(int)
    n_days = len(dataset.daily_demands)
    for day, demands in dataset.daily_demands.items():
        for d in demands:
            product_daily[d.product] += d.quantity
    avg_daily_per_product = {p: q // max(1, n_days) for p, q in product_daily.items()}
    avg_daily_total = sum(avg_daily_per_product.values())
    n_stores = len(dataset.stores)
    per_store = avg_daily_total // max(1, n_stores)

    # Define policies with comparable parameters
    policies = [
        (NaivePolicy(period=7, fixed_qty=per_store * 5),
         "Naive (weekly fixed)"),

        (SQPolicy(s=per_store * 2, Q=per_store * 5),
         f"(s,Q) s={per_store*2}, Q={per_store*5}"),

        (SSPolicy(s=per_store * 2, S=per_store * 7),
         f"(s,S) s={per_store*2}, S={per_store*7}"),

        (AdaptiveSQPolicy(service_level=0.95, lead_time=3),
         "Adaptive (s,Q) SL=95%"),

    ]

    # Try loading AI model
    try:
        from validation.walmart.forecast_model import ChronosForecastModel
        chronos = ChronosForecastModel("tiny", device="cpu")
        policies.append((AIPolicy(forecast_model=chronos), f"AI Agent ({chronos.name})"))
    except Exception as e:
        print(f"⚠️ Chronos not available: {e}")
        policies.append((AIPolicy(forecast_model=None), "AI Agent (fallback)"))


    print("=" * 75)
    print("📊 INVENTORY POLICY COMPARISON — Walmart M5 Real Data")
    print(f"   {args.days} days | {dataset.days} available | {len(dataset.stores)} stores | {len(dataset.products)} products")
    print(f"   Avg daily demand: {avg_daily_total:,} units")
    print("=" * 75)

    results = []
    for policy, label in policies:
        print(f"\n🔄 Running: {label}...")
        result = run_policy(dataset, policy, args.days, label)
        results.append(result)
        print(f"   Fill rate: {result['fill_rate']:.1%} | Stockouts: {result['stockouts']} | Reorders: {result['reorders']}")

    # Print comparison table
    print(f"\n\n{'=' * 75}")
    print("📊 RESULTS COMPARISON")
    print(f"{'=' * 75}")
    print(f"\n{'Policy':<35} {'Fill Rate':>10} {'Stockouts':>10} {'Reorders':>10}")
    print(f"{'─' * 35} {'─' * 10} {'─' * 10} {'─' * 10}")
    for r in results:
        print(f"{r['policy']:<35} {r['fill_rate']:>9.1%} {r['stockouts']:>10} {r['reorders']:>10}")

    # Winner
    best = max(results, key=lambda x: x['fill_rate'])
    print(f"\n🏆 Best: {best['policy']} ({best['fill_rate']:.1%} fill rate)")

    # Gap analysis
    print(f"\n{'─' * 75}")
    print("📈 GAP FOR AI AGENT TO BEAT:")
    print(f"   Must exceed: {best['fill_rate']:.1%} fill rate ({best['policy']})")
    print(f"   Must reduce: {best['stockouts']} stockouts")
    print(f"   Especially during disruption periods and demand spikes")

    # Save
    os.makedirs(args.output, exist_ok=True)
    output_path = os.path.join(args.output, "policy_comparison.json")
    with open(output_path, "w") as f:
        json.dump({"results": results, "days": args.days}, f, indent=2)
    print(f"\n💾 Results saved: {output_path}")
    print(f"{'=' * 75}")


if __name__ == "__main__":
    main()
