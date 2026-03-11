#!/usr/bin/env python3
"""
Generate GIF from M5 real data + Evolved Policy.
End-to-end: real demand → evolved agent → animated visualization.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from validation.walmart.m5_adapter import load_m5_data, build_network_from_m5
from validation.walmart.policy_engine import PolicyDrivenEngine
from visualization.renderer import SupplyChainRenderer
from simulation.engine import DaySnapshot
from PIL import Image


def run_and_render(days=90, output="docs/assets/supply_chain_sim.gif"):
    """Run M5 simulation with Evolved Policy and generate GIF."""

    # Import evolved policy
    from autotuning.evolvable_policy import EvolvablePolicy

    class PolicyAdapter:
        def __init__(self):
            self.ep = EvolvablePolicy()
        def name(self):
            return self.ep.name()
        def should_reorder(self, *a, **kw):
            return self.ep.should_reorder(*a, **kw)

    # Load real data
    dataset = load_m5_data("data/walmart_m5/", max_days=days)
    network = build_network_from_m5(dataset)

    # Update positions for better visualization layout
    _update_positions(network)

    # Run simulation
    policy = PolicyAdapter()
    engine = PolicyDrivenEngine(network, dataset, policy)
    print(f"🔄 Running {days}-day simulation with Evolved Policy...")
    history = engine.run(days=days, quiet=True)
    m = engine.metrics
    print(f"   Fill rate: {m.fill_rate:.2%} | Stockouts: {m.stockout_events} | Reorders: {m.reorder_decisions}")

    # Render frames
    renderer = SupplyChainRenderer(network)
    renderer.total_days = days
    frames = []

    # Sample every 3 days for GIF (30 frames for 90 days)
    sample_days = list(range(0, len(history), 3))
    if len(history) - 1 not in sample_days:
        sample_days.append(len(history) - 1)

    print(f"🎬 Rendering {len(sample_days)} frames...")
    for i, idx in enumerate(sample_days):
        snap = history[idx]
        frame = renderer.render_frame(snap)
        frames.append(frame)

    # Save GIF
    os.makedirs(os.path.dirname(output), exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=400,  # ms per frame
        loop=0,
        optimize=True,
    )

    size_kb = os.path.getsize(output) / 1024
    print(f"✅ GIF saved: {output} ({size_kb:.0f} KB, {len(frames)} frames)")
    print(f"   {m.fill_rate:.2%} fill rate | {m.stockout_events} stockouts | {m.reorder_decisions} reorders")


def _update_positions(network):
    """
    Arrange nodes in a clear left-to-right layout:
    Suppliers (left) → Warehouses (center) → Stores (right)
    with geographic grouping.
    """
    # Suppliers: left column
    suppliers = network.get_suppliers()
    for i, s in enumerate(suppliers):
        s.position = (80, 120 + i * 180)

    # Warehouses: center column, mapped to regions
    wh_order = {"W_WEST": 0, "W_SOUTH": 1, "W_MIDWEST": 2}
    for w in network.get_warehouses():
        idx = wh_order.get(w.id, 0)
        w.position = (350, 100 + idx * 200)

    # Stores: right column, grouped by state
    state_groups = {"CA": [], "TX": [], "WI": []}
    for store in network.get_stores():
        state = store.id.split("_")[0]
        state_groups.get(state, []).append(store)

    y = 50
    for state in ["CA", "TX", "WI"]:
        stores = state_groups.get(state, [])
        for s in stores:
            s.position = (620, y)
            y += 55
        y += 20  # Gap between state groups


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--output", default="docs/assets/supply_chain_sim.gif")
    args = parser.parse_args()
    run_and_render(days=args.days, output=args.output)
