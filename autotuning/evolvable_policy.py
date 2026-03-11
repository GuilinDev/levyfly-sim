#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evolvable Inventory Policy — The code that the autotuning agent modifies.

This is the "train.py" equivalent from Karpathy's autoresearch.
The autotuning loop reads strategy.md, modifies THIS file, runs eval,
and commits if score improves.

~200 lines. Fits in any LLM context window.
"""
import statistics
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

# ============================================================
# EVOLVABLE PARAMETERS — Agent can modify these
# ============================================================

# Reorder point calculation
REORDER_WINDOW = 14          # Days of history to consider
SAFETY_FACTOR = 1.2          # Multiplier on std dev for safety stock (grid search optimal: 1.2)
LEAD_TIME = 3                # Expected days for delivery
SERVICE_LEVEL_Z = 1.65       # Z-score for 95% service level

# Order quantity calculation
ORDER_HORIZON = 10           # Days of supply to order (grid search optimal: 10)
ORDER_BUFFER = 0.9           # Buffer multiplier (grid search optimal: 0.9)

# Emergency detection
EMERGENCY_THRESHOLD = 0.5    # Trigger emergency when inv < threshold * avg_daily (grid search: 0.5)
EMERGENCY_MULTIPLIER = 1.5   # Order this much more in emergency (grid search: 1.5)

# Demand forecasting
USE_WEIGHTED_AVG = True      # Use exponential weighted average
EWA_ALPHA = 0.3              # Exponential weight (higher = more recent bias)
TREND_DETECTION = True       # Detect upward/downward trends
TREND_WINDOW = 7             # Window for trend detection
TREND_ADJUSTMENT = 0.1       # How much to adjust for trend (fraction)

# Disruption response
DISRUPTION_BUFFER = 1.3      # Extra buffer when any supplier is disrupted (was 1.5)
PRE_DISRUPTION_DAYS = 2      # Start buffering this many days before typical disruption

# ============================================================
# POLICY LOGIC — Agent can modify this too
# ============================================================

class EvolvablePolicy:
    """Inventory policy with evolvable parameters and logic."""

    def __init__(self):
        self.demand_history: Dict[str, List[float]] = defaultdict(list)
        self.reorder_history: Dict[str, List[int]] = defaultdict(list)  # days when reordered

    def name(self) -> str:
        return "Evolved Policy"

    def _get_demand_estimate(self, product: str) -> Tuple[float, float]:
        """Estimate daily demand (mean, std) from history."""
        history = self.demand_history.get(product, [])
        if len(history) < 3:
            return 100.0, 30.0  # Conservative default

        recent = history[-REORDER_WINDOW:]

        if USE_WEIGHTED_AVG and len(recent) > 1:
            # Exponential weighted average
            weights = [(1 - EWA_ALPHA) ** (len(recent) - 1 - i) for i in range(len(recent))]
            w_sum = sum(weights)
            avg = sum(v * w for v, w in zip(recent, weights)) / w_sum
        else:
            avg = statistics.mean(recent)

        std = statistics.stdev(recent) if len(recent) > 1 else avg * 0.3

        # Trend adjustment
        if TREND_DETECTION and len(history) >= TREND_WINDOW * 2:
            old_avg = statistics.mean(history[-TREND_WINDOW * 2:-TREND_WINDOW])
            new_avg = statistics.mean(history[-TREND_WINDOW:])
            trend = (new_avg - old_avg) / max(old_avg, 1)
            avg *= (1 + trend * TREND_ADJUSTMENT)

        return max(avg, 1.0), max(std, 0.1)

    def _calculate_reorder_point(self, product: str) -> int:
        """Calculate when to reorder."""
        avg, std = self._get_demand_estimate(product)

        # Reorder point = demand during lead time + safety stock
        demand_during_lt = avg * LEAD_TIME
        safety_stock = SERVICE_LEVEL_Z * std * (LEAD_TIME ** 0.5) * SAFETY_FACTOR

        return int(demand_during_lt + safety_stock)

    def _calculate_order_qty(self, product: str, current_inv: int) -> int:
        """Calculate how much to order."""
        avg, std = self._get_demand_estimate(product)
        target = avg * ORDER_HORIZON * ORDER_BUFFER
        qty = int(target - current_inv + self._calculate_reorder_point(product))
        return max(qty, int(avg * 3))  # At least 3 days supply

    def _is_emergency(self, product: str, current_inv: int) -> bool:
        """Detect if we're in an emergency low-stock situation."""
        avg, _ = self._get_demand_estimate(product)
        return current_inv < avg * EMERGENCY_THRESHOLD

    def should_reorder(self, node_id: str, product: str,
                       current_inventory: int, day: int, **ctx) -> Tuple[bool, int, str]:
        """Main decision function."""
        daily_demand = ctx.get("daily_demand", 0)
        if daily_demand > 0:
            self.demand_history[product].append(daily_demand)

        history = self.demand_history.get(product, [])
        if len(history) < 3:
            if current_inventory < 300:
                return True, 600, "Insufficient history, conservative reorder"
            return False, 0, ""

        # Emergency check
        if self._is_emergency(product, current_inventory):
            avg, _ = self._get_demand_estimate(product)
            qty = int(avg * ORDER_HORIZON * EMERGENCY_MULTIPLIER)
            return True, qty, f"EMERGENCY: inv={current_inventory}, avg_daily={avg:.0f}"

        # Normal reorder check
        reorder_point = self._calculate_reorder_point(product)
        if current_inventory < reorder_point:
            qty = self._calculate_order_qty(product, current_inventory)
            return True, qty, (
                f"Below reorder point: inv={current_inventory} < s={reorder_point}, "
                f"ordering {qty}"
            )

        return False, 0, ""
