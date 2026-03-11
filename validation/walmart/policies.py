#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inventory Policies — Industry Standard Baselines

Implements classic inventory management policies for fair comparison:
  1. Naive: fixed periodic reorder (lower bound)
  2. (s, Q): reorder Q units when inventory drops below s
  3. (s, S): reorder up to S when inventory drops below s
  4. AI-powered: learned demand forecast + dynamic decisions

All policies implement the same interface so they can be swapped
into the DemandDrivenEngine for apples-to-apples comparison.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple, List
from collections import defaultdict


class InventoryPolicy(ABC):
    """Base class for inventory policies."""

    @abstractmethod
    def should_reorder(
        self,
        node_id: str,
        product: str,
        current_inventory: int,
        day: int,
        **context
    ) -> Tuple[bool, int, str]:
        """
        Decide whether to reorder and how much.

        Returns:
            (should_reorder, quantity, reasoning)
        """
        pass

    @abstractmethod
    def name(self) -> str:
        pass


class NaivePolicy(InventoryPolicy):
    """
    Naive: Fixed periodic reorder.
    Every N days, order a fixed quantity regardless of inventory.
    This is the lower bound — any real system should beat this.
    """

    def __init__(self, period: int = 7, fixed_qty: int = 500):
        self.period = period
        self.fixed_qty = fixed_qty

    def name(self) -> str:
        return f"Naive (every {self.period}d, qty={self.fixed_qty})"

    def should_reorder(self, node_id, product, current_inventory, day, **ctx):
        if day % self.period == 0:
            return True, self.fixed_qty, f"Periodic reorder (every {self.period} days)"
        return False, 0, ""


class SQPolicy(InventoryPolicy):
    """
    (s, Q) Policy — Reorder Point, Fixed Quantity.
    When inventory drops below s, order exactly Q units.
    This is the most common policy in ERP systems (SAP, Oracle).
    """

    def __init__(self, s: int = 200, Q: int = 600):
        self.s = s
        self.Q = Q

    def name(self) -> str:
        return f"(s,Q) s={self.s}, Q={self.Q}"

    def should_reorder(self, node_id, product, current_inventory, day, **ctx):
        if current_inventory < self.s:
            return True, self.Q, f"Below reorder point (inv={current_inventory} < s={self.s})"
        return False, 0, ""


class SSPolicy(InventoryPolicy):
    """
    (s, S) Policy — Reorder Point, Order-Up-To.
    When inventory drops below s, order enough to reach S.
    More sophisticated than (s,Q) — adjusts order size to current level.
    """

    def __init__(self, s: int = 200, S: int = 800):
        self.s = s
        self.S = S

    def name(self) -> str:
        return f"(s,S) s={self.s}, S={self.S}"

    def should_reorder(self, node_id, product, current_inventory, day, **ctx):
        if current_inventory < self.s:
            qty = self.S - current_inventory
            return True, qty, f"Order-up-to (inv={current_inventory}, target={self.S}, ordering={qty})"
        return False, 0, ""


class AdaptiveSQPolicy(InventoryPolicy):
    """
    Adaptive (s, Q) — learns s and Q from demand history.
    Adjusts reorder point based on observed demand volatility.
    Better than fixed (s,Q) but still rule-based.
    """

    def __init__(self, service_level: float = 0.95, lead_time: int = 3):
        self.service_level = service_level
        self.lead_time = lead_time
        self.demand_history: Dict[str, list] = defaultdict(list)  # product → [daily demands]

    def name(self) -> str:
        return f"Adaptive (s,Q) SL={self.service_level}"

    def should_reorder(self, node_id, product, current_inventory, day, **ctx):
        # Record demand if available
        daily_demand = ctx.get("daily_demand", 0)
        if daily_demand > 0:
            self.demand_history[product].append(daily_demand)

        history = self.demand_history.get(product, [])
        if len(history) < 7:
            # Not enough data, use conservative fixed policy
            if current_inventory < 300:
                return True, 600, "Insufficient history, conservative reorder"
            return False, 0, ""

        # Calculate adaptive parameters
        import statistics
        recent = history[-30:] if len(history) >= 30 else history
        avg_demand = statistics.mean(recent)
        std_demand = statistics.stdev(recent) if len(recent) > 1 else avg_demand * 0.3

        # Safety stock = z * σ * √L (where z ≈ 1.65 for 95% service level)
        z = {0.90: 1.28, 0.95: 1.65, 0.99: 2.33}.get(self.service_level, 1.65)
        safety_stock = z * std_demand * (self.lead_time ** 0.5)

        # Reorder point = average demand during lead time + safety stock
        s = int(avg_demand * self.lead_time + safety_stock)
        Q = int(avg_demand * 7)  # 7-day supply

        if current_inventory < s:
            return True, Q, f"Adaptive: s={s} (μ={avg_demand:.0f}, σ={std_demand:.0f}), Q={Q}"
        return False, 0, ""


class AIPolicy(InventoryPolicy):
    """
    AI-Powered Policy — uses a learned forecast model.
    Caches forecasts to avoid redundant inference calls.
    """

    def __init__(self, forecast_model=None, forecast_interval: int = 7):
        self.forecast_model = forecast_model
        self.forecast_interval = forecast_interval
        self.demand_history: Dict[str, list] = defaultdict(list)
        # Cache: (node_id, product) → (last_forecast_day, forecast)
        self._forecast_cache: Dict[tuple, tuple] = {}
        self._fallback = AdaptiveSQPolicy()

    def name(self) -> str:
        model_name = getattr(self.forecast_model, 'name', 'pending') if self.forecast_model else 'pending'
        return f"AI Agent (model={model_name})"

    def _get_forecast(self, node_id: str, product: str, day: int) -> Optional[list]:
        """Get or compute cached forecast."""
        cache_key = (node_id, product)
        cached = self._forecast_cache.get(cache_key)
        if cached and day - cached[0] < self.forecast_interval:
            return cached[1]

        history = self.demand_history.get(product, [])
        if len(history) < 14 or self.forecast_model is None:
            return None

        forecast = self.forecast_model.predict(history[-60:], horizon=7)
        self._forecast_cache[cache_key] = (day, forecast)
        return forecast

    def should_reorder(self, node_id, product, current_inventory, day, **ctx):
        daily_demand = ctx.get("daily_demand", 0)
        if daily_demand > 0:
            self.demand_history[product].append(daily_demand)

        if self.forecast_model is None:
            return self._fallback.should_reorder(
                node_id, product, current_inventory, day, **ctx
            )

        forecast = self._get_forecast(node_id, product, day)
        if forecast is None:
            if current_inventory < 300:
                return True, 600, "AI: insufficient history, conservative"
            return False, 0, ""

        total_forecast = sum(forecast)
        peak_forecast = max(forecast)

        safety_buffer = peak_forecast * 1.5
        reorder_point = int(total_forecast * 0.5 + safety_buffer)

        if current_inventory < reorder_point:
            order_qty = int(total_forecast * 1.2)
            return True, order_qty, (
                f"AI forecast: next 7d demand={total_forecast:.0f}, "
                f"peak={peak_forecast:.0f}, ordering={order_qty}"
            )
        return False, 0, ""
