#!/usr/bin/env python3
"""
LLM Agent vs Traditional Policies — Head-to-head comparison.

Runs the LLM-powered agent alongside baselines on real M5 data
and generates a comparison report with decision reasoning.

Usage:
  python validation/walmart/run_llm_comparison.py
  python validation/walmart/run_llm_comparison.py --days 90 --model mistral-small3.2:24b
"""
import os
import sys
import json
import argparse
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from validation.walmart.m5_adapter import load_m5_data, build_network_from_m5
from validation.walmart.policy_engine import PolicyDrivenEngine
from validation.walmart.policies import SSPolicy
from validation.walmart.scoring import evaluate_engine
from simulation.llm_agent import LLMAgent

RESULTS_DIR = Path(__file__).parent / "results"


def main():
    parser = argparse.ArgumentParser(description="🧠 LLM Agent Comparison")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--data", type=str, default="data/walmart_m5/")
    parser.add_argument("--model", type=str, default="mistral-small3.2:24b")
    parser.add_argument("--scenario", type=str, default="baseline",
                        choices=["baseline", "disruption"])
    args = parser.parse_args()

    print("=" * 70)
    print("🧠 LLM AGENT vs TRADITIONAL POLICIES")
    print(f"   Model: {args.model} | Days: {args.days}")
    print("=" * 70)

    # Load data
    print("\nLoading Walmart M5 data...")
    dataset = load_m5_data(args.data, max_days=args.days)

    # Compute per-store params for (s,S)
    product_daily = defaultdict(int)
    n_days = len(dataset.daily_demands)
    for day, demands in dataset.daily_demands.items():
        for d in demands:
            product_daily[d.product] += d.quantity
    avg_daily_total = sum(q // max(1, n_days) for q in product_daily.values())
    per_store = avg_daily_total // max(1, len(dataset.stores))

    # Add disruption if requested
    if args.scenario == "disruption":
        import copy
        dataset = copy.deepcopy(dataset)
        dataset.disruption_periods = [
            (15, 25, "Major supplier outage — FOODS factory fire"),
            (22, 29, "Secondary disruption — port congestion"),
        ]
        print("  💥 Disruption scenario: 2 disruptions injected")

    results = []

    # 1. Run (s,S) baseline
    print(f"\n{'─' * 60}")
    print("📦 Running (s,S) baseline...")
    network = build_network_from_m5(dataset)
    ss_policy = SSPolicy(s=per_store * 2, S=per_store * 7)
    engine = PolicyDrivenEngine(network, dataset, ss_policy)
    engine.run(days=args.days, quiet=True)
    ss_result = evaluate_engine(engine, days_simulated=args.days)
    ss_result["policy"] = "(s,S) Fixed"
    results.append(ss_result)
    print(f"  Score: {ss_result['score']:.2f} | Fill: {ss_result['fill_rate']:.1%} | "
          f"Stockouts: {ss_result['stockouts']}")

    # 2. Run Evolved Policy
    print(f"\n{'─' * 60}")
    print("⚡ Running Evolved Policy...")
    try:
        from autotuning.evolvable_policy import EvolvablePolicy
        network = build_network_from_m5(dataset)
        engine = PolicyDrivenEngine(network, dataset, EvolvablePolicy())
        engine.run(days=args.days, quiet=True)
        evolved_result = evaluate_engine(engine, days_simulated=args.days)
        evolved_result["policy"] = "Evolved Agent"
        results.append(evolved_result)
        print(f"  Score: {evolved_result['score']:.2f} | Fill: {evolved_result['fill_rate']:.1%} | "
              f"Stockouts: {evolved_result['stockouts']}")
    except ImportError:
        print("  ⚠️ Evolved Policy not available")

    # 3. Run LLM Agent
    print(f"\n{'─' * 60}")
    print(f"🧠 Running LLM Agent ({args.model})...")
    network = build_network_from_m5(dataset)
    llm_agent = LLMAgent(model=args.model, verbose=True)
    engine = PolicyDrivenEngine(network, dataset, llm_agent)
    engine.run(days=args.days, quiet=True)
    llm_result = evaluate_engine(engine, days_simulated=args.days)
    llm_result["policy"] = f"LLM Agent ({args.model.split(':')[0]})"
    llm_result["strategic_decisions"] = len(llm_agent.decisions)
    results.append(llm_result)
    print(f"\n  Score: {llm_result['score']:.2f} | Fill: {llm_result['fill_rate']:.1%} | "
          f"Stockouts: {llm_result['stockouts']}")
    print(f"  Strategic decisions: {llm_result['strategic_decisions']}")

    # Comparison table
    print(f"\n{'=' * 70}")
    print("📊 HEAD-TO-HEAD COMPARISON")
    print(f"{'=' * 70}")
    print(f"\n{'Policy':<30s} {'Score':>8s} {'Fill':>8s} {'Outs':>6s} {'Excess':>8s}")
    print(f"{'─' * 30} {'─' * 8} {'─' * 8} {'─' * 6} {'─' * 8}")
    for r in results:
        emoji = "🏆" if r["score"] == max(x["score"] for x in results) else "  "
        print(f"{emoji}{r['policy']:<28s} {r['score']:>8.2f} {r['fill_rate']:>7.1%} "
              f"{r['stockouts']:>6d} {r['excess_ratio']:>7.0%}")

    # LLM Decision Log
    print(f"\n{'=' * 70}")
    print(llm_agent.get_decision_summary())

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "comparison": results,
        "llm_decisions": llm_agent.get_decision_log(),
        "model": args.model,
        "days": args.days,
        "scenario": args.scenario,
    }
    output_path = RESULTS_DIR / "llm_comparison.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n📁 Results saved to: {output_path}")

    # Generate markdown report
    report_path = RESULTS_DIR / "llm_agent_report.md"
    with open(report_path, "w") as f:
        f.write(f"# LLM Agent Performance Report\n\n")
        f.write(f"**Model**: {args.model}  \n")
        f.write(f"**Data**: Walmart M5 ({args.days} days)  \n")
        f.write(f"**Scenario**: {args.scenario}  \n\n")
        
        f.write("## Results\n\n")
        f.write("| Policy | Score | Fill Rate | Stockouts | Excess |\n")
        f.write("|--------|-------|-----------|-----------|--------|\n")
        for r in results:
            winner = " 🏆" if r["score"] == max(x["score"] for x in results) else ""
            f.write(f"| {r['policy']}{winner} | {r['score']:.2f} | "
                    f"{r['fill_rate']:.1%} | {r['stockouts']} | "
                    f"{r['excess_ratio']:.0%} |\n")
        
        f.write(f"\n{llm_agent.get_decision_summary()}\n")
    
    print(f"📄 Report: {report_path}")


if __name__ == "__main__":
    main()
