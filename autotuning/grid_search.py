#!/usr/bin/env python3
"""
Grid search over evolvable policy parameters.
Faster than waiting for LLM agent — brute force the parameter space.
"""
import os, sys, json, itertools, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validation.walmart.m5_adapter import load_m5_data, build_network_from_m5
from validation.walmart.policy_engine import PolicyDrivenEngine
from validation.walmart.scoring import evaluate_engine

# Load data ONCE
print("Loading M5 data...")
dataset = load_m5_data("data/walmart_m5/", max_days=90)

def evaluate_params(safety_factor, order_horizon, order_buffer, emergency_thresh, emergency_mult):
    """Run one evaluation with given params."""
    # Dynamically create policy with these params
    from collections import defaultdict
    import statistics

    class TestPolicy:
        def __init__(self):
            self.demand_history = defaultdict(list)

        def name(self):
            return f"SF={safety_factor},OH={order_horizon},OB={order_buffer}"

        def should_reorder(self, node_id, product, current_inventory, day, **ctx):
            daily_demand = ctx.get("daily_demand", 0)
            if daily_demand > 0:
                self.demand_history[product].append(daily_demand)

            history = self.demand_history.get(product, [])
            if len(history) < 3:
                if current_inventory < 300:
                    return True, 600, "bootstrap"
                return False, 0, ""

            recent = history[-14:]
            avg = statistics.mean(recent)
            std = statistics.stdev(recent) if len(recent) > 1 else avg * 0.3

            # Reorder point
            s = int(avg * 3 + 1.65 * std * (3 ** 0.5) * safety_factor)

            # Emergency
            if current_inventory < avg * emergency_thresh:
                qty = int(avg * order_horizon * emergency_mult)
                return True, qty, "emergency"

            # Normal
            if current_inventory < s:
                target = avg * order_horizon * order_buffer
                qty = int(target)
                return True, max(qty, int(avg * 2)), "normal"

            return False, 0, ""

    network = build_network_from_m5(dataset)
    engine = PolicyDrivenEngine(network, dataset, TestPolicy())
    engine.run(days=90, quiet=True)

    # Use unified scoring
    result = evaluate_engine(engine, days_simulated=90)
    result["params"] = {
        "safety_factor": safety_factor,
        "order_horizon": order_horizon,
        "order_buffer": order_buffer,
        "emergency_thresh": emergency_thresh,
        "emergency_mult": emergency_mult,
    }
    return result

# Parameter grid
grid = {
    "safety_factor": [0.8, 1.0, 1.2, 1.5, 1.8],
    "order_horizon": [5, 7, 10],
    "order_buffer": [0.8, 0.9, 1.0, 1.1],
    "emergency_thresh": [0.3, 0.5],
    "emergency_mult": [1.5, 2.0],
}

combos = list(itertools.product(
    grid["safety_factor"], grid["order_horizon"], grid["order_buffer"],
    grid["emergency_thresh"], grid["emergency_mult"]
))
print(f"Total combinations: {len(combos)}")

results = []
best_score = -999
best_result = None
start = time.time()

for i, (sf, oh, ob, et, em) in enumerate(combos):
    r = evaluate_params(sf, oh, ob, et, em)
    results.append(r)
    if r["score"] > best_score:
        best_score = r["score"]
        best_result = r
        print(f"[{i+1}/{len(combos)}] NEW BEST: score={r['score']:.2f} fill={r['fill_rate']:.4f} stockouts={r['stockouts']} excess={r['excess_ratio']:.2%} | SF={sf} OH={oh} OB={ob}")
    elif (i+1) % 20 == 0:
        print(f"[{i+1}/{len(combos)}] score={r['score']:.2f} | best so far={best_score:.2f}")

elapsed = time.time() - start
print(f"\n{'='*60}")
print(f"GRID SEARCH COMPLETE — {len(combos)} combos in {elapsed:.0f}s")
print(f"{'='*60}")
print(f"Best score: {best_result['score']:.4f}")
print(f"Fill rate:  {best_result['fill_rate']:.4%}")
print(f"Stockouts:  {best_result['stockouts']}")
print(f"Excess:     {best_result['excess_ratio']:.2%}")
print(f"Params:     {best_result['params']}")

# Save top 10
results.sort(key=lambda x: x["score"], reverse=True)
os.makedirs("autotuning/results", exist_ok=True)
with open("autotuning/results/grid_search.json", "w") as f:
    json.dump({"best": best_result, "top10": results[:10], "total": len(combos), "elapsed_s": elapsed}, f, indent=2)
print(f"\nSaved to autotuning/results/grid_search.json")
