#!/usr/bin/env python3
"""
Unified Scoring Module — Single source of truth for policy evaluation.

ALL evaluation code must use this module. No more inline excess calculations.

Score = fill_rate × 100 − stockouts × 0.5 − excess_ratio × 10

excess_ratio = (final_inventory − ideal_inventory) / ideal_inventory
where ideal_inventory = avg_daily_demand × 7 (7-day supply target)
and final_inventory = sum of all non-supplier node inventory at end of simulation
"""
import sys
import os
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def compute_excess_ratio(engine, days_simulated: Optional[int] = None) -> float:
    """
    Compute excess inventory ratio.
    
    excess = (actual_ending_inventory - ideal_7day_supply) / ideal_7day_supply
    
    Uses ONLY the final day's snapshot.
    Excludes suppliers (they have infinite production capacity).
    """
    from simulation.network import NodeType
    
    if not engine.history:
        return 0.0
    
    # Total ending inventory (non-supplier nodes only)
    total_inv = 0
    last_snapshot = engine.history[-1]
    for node_id, inv in last_snapshot.inventories.items():
        node = engine.network.get_node(node_id)
        if node and node.node_type != NodeType.SUPPLIER:
            total_inv += sum(inv.values())
    
    # Ideal = 7 days of average daily demand
    days = days_simulated or engine.metrics.days_simulated or len(engine.history)
    avg_daily = engine.metrics.total_real_demand / max(1, days)
    ideal_inv = avg_daily * 7
    
    excess_ratio = max(0, (total_inv - ideal_inv) / max(1, ideal_inv))
    return excess_ratio


def compute_score(fill_rate: float, stockouts: int, excess_ratio: float) -> float:
    """
    Unified composite score.
    
    Score = fill_rate × 100 − stockouts × 0.5 − excess_ratio × 10
    
    Higher is better. Balances availability (fill rate), reliability (stockouts),
    and efficiency (excess inventory).
    """
    return fill_rate * 100 - stockouts * 0.5 - excess_ratio * 10


def evaluate_engine(engine, days_simulated: Optional[int] = None) -> Dict[str, Any]:
    """
    Full evaluation of a completed engine run.
    Returns standardized result dict.
    """
    m = engine.metrics
    fill_rate = m.fill_rate
    stockouts = m.stockout_events
    excess_ratio = compute_excess_ratio(engine, days_simulated)
    score = compute_score(fill_rate, stockouts, excess_ratio)
    
    return {
        "score": round(score, 2),
        "fill_rate": round(fill_rate, 4),
        "stockouts": stockouts,
        "stockout_units": m.stockout_units,
        "excess_ratio": round(excess_ratio, 4),
        "reorders": m.reorder_decisions,
        "emergency_reorders": getattr(m, 'emergency_reorders', 0),
        "total_demand": m.total_real_demand,
        "fulfilled": m.fulfilled_demand,
    }
