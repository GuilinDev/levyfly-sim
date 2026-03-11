#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluate the evolvable policy against M5 data.
Returns a single score number. Higher = better.

This is the evaluation harness for the autotuning loop.
"""
import os
import sys
import json
import importlib

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from validation.walmart.m5_adapter import load_m5_data, build_network_from_m5
from validation.walmart.policy_engine import PolicyDrivenEngine


class PolicyAdapter:
    """Adapts EvolvablePolicy to InventoryPolicy interface."""

    def __init__(self, evolvable):
        self.evolvable = evolvable

    def name(self):
        return self.evolvable.name()

    def should_reorder(self, node_id, product, current_inventory, day, **ctx):
        return self.evolvable.should_reorder(
            node_id, product, current_inventory, day, **ctx
        )


def evaluate(days=90, data_path="data/walmart_m5/", verbose=True):
    """Run evaluation and return score."""
    # Reload evolvable_policy module to pick up changes
    import autotuning.evolvable_policy as ep
    importlib.reload(ep)

    policy = PolicyAdapter(ep.EvolvablePolicy())
    dataset = load_m5_data(data_path, max_days=days)
    network = build_network_from_m5(dataset)
    engine = PolicyDrivenEngine(network, dataset, policy)
    engine.run(days=days, quiet=True)

    m = engine.metrics
    fill_rate = m.fill_rate
    stockouts = m.stockout_events
    reorders = m.reorder_decisions

    # Calculate excess inventory ratio
    total_inv = sum(
        sum(inv.values())
        for inv in engine.history[-1].inventories.values()
    ) if engine.history else 0
    avg_daily = m.total_real_demand / max(1, m.days_simulated)
    excess_ratio = max(0, (total_inv - avg_daily * 7) / max(1, avg_daily * 7))

    # Score function from strategy.md
    score = fill_rate * 100 - stockouts * 0.5 - excess_ratio * 10

    result = {
        "score": round(score, 4),
        "fill_rate": round(fill_rate, 6),
        "stockouts": stockouts,
        "reorders": reorders,
        "total_demand": m.total_real_demand,
        "fulfilled": m.fulfilled_demand,
        "excess_ratio": round(excess_ratio, 4),
    }

    if verbose:
        print(f"{'=' * 60}")
        print(f"📊 EVALUATION RESULT")
        print(f"{'=' * 60}")
        print(f"  Score:       {score:.4f}")
        print(f"  Fill Rate:   {fill_rate:.4%}")
        print(f"  Stockouts:   {stockouts}")
        print(f"  Reorders:    {reorders}")
        print(f"  Excess:      {excess_ratio:.2%}")
        print(f"{'=' * 60}")

    return result


# Baseline scores for reference
BASELINES = {
    "(s,S) fixed": {"score": 97.9, "fill_rate": 0.999, "stockouts": 4},
    "(s,Q) fixed": {"score": 92.5, "fill_rate": 0.995, "stockouts": 14},
    "Naive": {"score": 50.0, "fill_rate": 0.637, "stockouts": 2307},
}


if __name__ == "__main__":
    result = evaluate()
    print(f"\n📈 vs Baselines:")
    for name, base in BASELINES.items():
        delta = result["score"] - base["score"]
        print(f"  vs {name}: {'+' if delta > 0 else ''}{delta:.2f}")

    # Save result
    os.makedirs("autotuning/results", exist_ok=True)
    with open("autotuning/results/latest.json", "w") as f:
        json.dump(result, f, indent=2)
