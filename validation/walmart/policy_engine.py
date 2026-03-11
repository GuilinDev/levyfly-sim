#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Policy-Driven Simulation Engine

Like DemandDrivenEngine but accepts any InventoryPolicy,
enabling fair A/B comparison between strategies.
"""
import sys
import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from simulation.network import SupplyChainNetwork, NodeType
from simulation.engine import DaySnapshot, Event, AgentDecision
from validation.walmart.m5_adapter import M5Dataset
from validation.walmart.policies import InventoryPolicy


class ValidationMetrics:
    def __init__(self):
        self.total_real_demand = 0
        self.fulfilled_demand = 0
        self.stockout_events = 0
        self.stockout_units = 0
        self.reorder_decisions = 0
        self.emergency_reorders = 0
        self.days_simulated = 0

    @property
    def fill_rate(self):
        return self.fulfilled_demand / max(1, self.total_real_demand)


class PolicyDrivenEngine:
    """Runs simulation with a pluggable inventory policy."""

    def __init__(self, network: SupplyChainNetwork, dataset: M5Dataset, policy: InventoryPolicy):
        self.network = network
        self.dataset = dataset
        self.policy = policy
        self.metrics = ValidationMetrics()
        self.history = []
        self.events_log = []
        self.decisions_log = []
        self.in_transit = []
        self.disrupted_nodes = set()

        # Track per-store per-product daily demand for policy context
        self.daily_demand_tracker = defaultdict(lambda: defaultdict(int))

    def run(self, days: Optional[int] = None, quiet: bool = False) -> List[DaySnapshot]:
        sim_days = days or self.dataset.days
        for day in range(1, sim_days + 1):
            snapshot = self._simulate_day(day)
            self.history.append(snapshot)
            self.metrics.days_simulated = day
            if not quiet and day % 30 == 0:
                print(f"   Day {day}: fill rate {self.metrics.fill_rate:.1%}")
        return self.history

    def _simulate_day(self, day):
        day_events = []
        day_decisions = []

        # Supplier production
        for supplier in self.network.get_suppliers():
            for product in list(supplier.inventory.keys()):
                # Daily production scaled to demand
                daily_prod = 5000
                supplier.inventory[product] = supplier.inventory.get(product, 0) + daily_prod

        # Arriving shipments
        arriving = [s for s in self.in_transit if s[0] == day]
        self.in_transit = [s for s in self.in_transit if s[0] != day]
        for _, target_id, product, qty in arriving:
            node = self.network.get_node(target_id)
            if node:
                node.inventory[product] = node.inventory.get(product, 0) + qty

        # Disruptions
        for start, end, desc in self.dataset.disruption_periods:
            if day == start:
                suppliers = self.network.get_suppliers()
                if suppliers:
                    self.disrupted_nodes.add(suppliers[0].id)
            elif day == end + 1 and self.disrupted_nodes:
                self.disrupted_nodes.pop()

        # Apply REAL demand
        real_demands = self.dataset.daily_demands.get(day, [])
        for demand in real_demands:
            store = self.network.get_node(demand.store_id)
            if not store:
                continue
            product = demand.product
            qty_needed = demand.quantity
            available = store.inventory.get(product, 0)
            self.metrics.total_real_demand += qty_needed
            self.daily_demand_tracker[demand.store_id][product] = qty_needed

            if available >= qty_needed:
                store.inventory[product] = available - qty_needed
                self.metrics.fulfilled_demand += qty_needed
            else:
                store.inventory[product] = 0
                self.metrics.fulfilled_demand += available
                self.metrics.stockout_events += 1
                self.metrics.stockout_units += (qty_needed - available)

        # Warehouse reorder using policy
        for wh in self.network.get_warehouses():
            for product in self.dataset.products:
                inv = wh.inventory.get(product, 0)
                should, qty, reasoning = self.policy.should_reorder(
                    wh.id, product, inv, day,
                    daily_demand=self.daily_demand_tracker.get(wh.id, {}).get(product, 0)
                )
                if should and qty > 0:
                    supplier_id = self._find_supplier(wh.id, product)
                    if supplier_id and supplier_id not in self.disrupted_nodes:
                        supplier = self.network.get_node(supplier_id)
                        if supplier:
                            avail = supplier.inventory.get(product, 0)
                            actual = min(qty, avail)
                            if actual > 0:
                                supplier.inventory[product] = avail - actual
                                self.in_transit.append((day + 3, wh.id, product, actual))
                                self.metrics.reorder_decisions += 1

        # Store reorder from warehouse using policy
        for store in self.network.get_stores():
            for product in self.dataset.products:
                inv = store.inventory.get(product, 0)
                daily_d = self.daily_demand_tracker.get(store.id, {}).get(product, 0)
                should, qty, reasoning = self.policy.should_reorder(
                    store.id, product, inv, day,
                    daily_demand=daily_d
                )
                if should and qty > 0:
                    wh_id = self._find_warehouse(store.id)
                    if wh_id:
                        wh = self.network.get_node(wh_id)
                        if wh:
                            wh_inv = wh.inventory.get(product, 0)
                            actual = min(qty, wh_inv)
                            if actual > 0:
                                wh.inventory[product] = wh_inv - actual
                                self.in_transit.append((day + 1, store.id, product, actual))
                                self.metrics.reorder_decisions += 1

        fill_rate = self.metrics.fulfilled_demand / max(1, self.metrics.total_real_demand)
        return DaySnapshot(
            day=day,
            inventories={n.id: dict(n.inventory) for n in self.network.nodes.values()},
            events=day_events, decisions=day_decisions,
            metrics={"fill_rate": round(fill_rate, 4), "stockout_count": self.metrics.stockout_events,
                     "total_orders": self.metrics.reorder_decisions,
                     "active_disruptions": len(self.disrupted_nodes),
                     "in_transit_shipments": len(self.in_transit)},
            in_transit=[], disruptions={n: True for n in self.disrupted_nodes},
        )

    def _find_supplier(self, wh_id, product):
        for e in self.network.get_edges_to(wh_id):
            n = self.network.get_node(e.source_id)
            if n and n.node_type == NodeType.SUPPLIER and n.inventory.get(product, 0) > 0:
                return e.source_id
        return None

    def _find_warehouse(self, store_id):
        best, best_t = None, 999
        for e in self.network.get_edges_to(store_id):
            n = self.network.get_node(e.source_id)
            if n and n.node_type == NodeType.WAREHOUSE and e.transit_days < best_t:
                best, best_t = e.source_id, e.transit_days
        return best
