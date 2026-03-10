#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demand-Driven Simulation Engine

Unlike the standard engine (synthetic demand), this one uses REAL demand
from M5 data. This lets us measure:
  1. Would the agent's reorder decisions have prevented real stockouts?
  2. How much safety stock does the agent waste?
  3. Does the agent detect disruptions before they cause damage?
"""
import sys
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from simulation.network import SupplyChainNetwork, NodeType
from simulation.engine import DaySnapshot, Event, AgentDecision
from validation.walmart.m5_adapter import M5Dataset, DailyDemand


@dataclass
class ValidationMetrics:
    """Tracks how well agent decisions match reality."""
    total_real_demand: int = 0
    fulfilled_demand: int = 0
    stockout_events: int = 0
    stockout_units: int = 0
    reorder_decisions: int = 0
    emergency_reorders: int = 0
    excess_inventory_days: int = 0   # Days with inventory > 2x average demand
    days_simulated: int = 0

    @property
    def fill_rate(self) -> float:
        return self.fulfilled_demand / max(1, self.total_real_demand)

    @property
    def stockout_rate(self) -> float:
        return self.stockout_events / max(1, self.days_simulated)

    def to_dict(self) -> dict:
        return {
            "fill_rate": round(self.fill_rate, 4),
            "total_demand": self.total_real_demand,
            "fulfilled": self.fulfilled_demand,
            "stockouts": self.stockout_events,
            "stockout_units": self.stockout_units,
            "reorder_decisions": self.reorder_decisions,
            "emergency_reorders": self.emergency_reorders,
            "excess_inventory_days": self.excess_inventory_days,
            "days_simulated": self.days_simulated,
        }


class DemandDrivenEngine:
    """
    Simulation engine that replays real demand data
    and evaluates agent supply decisions.
    """

    def __init__(self, network: SupplyChainNetwork, dataset: M5Dataset, seed: int = 42):
        self.network = network
        self.dataset = dataset
        self.metrics = ValidationMetrics()
        self.history: List[DaySnapshot] = []
        self.events_log: List[Event] = []
        self.decisions_log: List[AgentDecision] = []

        # In-transit shipments: (arrival_day, target_id, product, quantity)
        self.in_transit: List[Tuple[int, str, str, int]] = []

        # Disrupted suppliers
        self.disrupted_nodes = set()

        # Reorder parameters per warehouse
        self.reorder_point = 200
        self.reorder_qty = 600
        self.emergency_threshold = 50

    def run(self, days: Optional[int] = None) -> List[DaySnapshot]:
        """Run simulation with real demand data."""
        sim_days = days or self.dataset.days

        print(f"\n🚀 Running demand-driven simulation ({sim_days} days)...")
        print(f"   Real demand data from M5 dataset")

        for day in range(1, sim_days + 1):
            snapshot = self._simulate_day(day)
            self.history.append(snapshot)
            self.metrics.days_simulated = day

            if day % 30 == 0:
                print(f"   Day {day}: fill rate {self.metrics.fill_rate:.1%}, "
                      f"stockouts {self.metrics.stockout_events}")

        return self.history

    def _simulate_day(self, day: int) -> DaySnapshot:
        """Simulate one day with real demand."""
        day_events = []
        day_decisions = []

        # 1. Process arriving shipments
        arriving = [s for s in self.in_transit if s[0] == day]
        self.in_transit = [s for s in self.in_transit if s[0] != day]

        for _, target_id, product, qty in arriving:
            node = self.network.get_node(target_id)
            if node:
                node.inventory[product] = node.inventory.get(product, 0) + qty
                day_events.append(Event(
                    day=day, event_type="shipment", source_id=target_id,
                    product=product, quantity=qty,
                    description=f"📦 {node.name}: received {qty} {product}"
                ))

        # 2. Check for disruptions from dataset
        for start, end, desc in self.dataset.disruption_periods:
            if day == start:
                # Find a supplier to disrupt
                suppliers = self.network.get_suppliers()
                if suppliers:
                    self.disrupted_nodes.add(suppliers[0].id)
                    day_events.append(Event(
                        day=day, event_type="disruption", source_id=suppliers[0].id,
                        description=f"🔥 {desc}"
                    ))
            elif day == end + 1:
                if self.disrupted_nodes:
                    recovered = self.disrupted_nodes.pop()
                    day_events.append(Event(
                        day=day, event_type="recovery", source_id=recovered,
                        description=f"✅ Supplier recovered"
                    ))

        # 3. Apply REAL demand from M5
        real_demands = self.dataset.daily_demands.get(day, [])

        for demand in real_demands:
            store = self.network.get_node(demand.store_id)
            if not store:
                continue

            product = demand.product
            qty_needed = demand.quantity
            available = store.inventory.get(product, 0)

            self.metrics.total_real_demand += qty_needed

            if available >= qty_needed:
                store.inventory[product] = available - qty_needed
                self.metrics.fulfilled_demand += qty_needed
                day_events.append(Event(
                    day=day, event_type="demand", source_id=store.id,
                    product=product, quantity=qty_needed,
                    description=f"{store.name}: sold {qty_needed} {product}"
                ))
            else:
                # Partial fulfillment
                store.inventory[product] = 0
                self.metrics.fulfilled_demand += available
                shortage = qty_needed - available
                self.metrics.stockout_events += 1
                self.metrics.stockout_units += shortage
                day_events.append(Event(
                    day=day, event_type="stockout", source_id=store.id,
                    product=product, quantity=shortage,
                    description=f"⚠️ {store.name}: STOCKOUT {product} (short {shortage})",
                    severity="warning"
                ))

        # 4. Warehouse agent decisions
        for wh in self.network.get_warehouses():
            for product in self.dataset.products:
                inv = wh.inventory.get(product, 0)

                if inv < self.emergency_threshold:
                    # Emergency reorder
                    best_supplier = self._find_supplier(wh.id, product)
                    if best_supplier and best_supplier not in self.disrupted_nodes:
                        order_qty = self.reorder_qty * 2
                        supplier = self.network.get_node(best_supplier)
                        available = supplier.inventory.get(product, 0) if supplier else 0
                        actual_qty = min(order_qty, available)
                        if actual_qty > 0 and supplier:
                            supplier.inventory[product] = available - actual_qty
                            edge = self._find_edge(best_supplier, wh.id)
                            transit = edge.transit_days if edge else 3
                            self.in_transit.append((day + transit, wh.id, product, actual_qty))
                            self.metrics.emergency_reorders += 1
                            day_decisions.append(AgentDecision(
                                day=day, agent_id=wh.id, action="emergency_reorder",
                                reasoning=f"Critical low: {inv} {product}, emergency order {actual_qty}",
                                details={"product": product, "quantity": actual_qty}
                            ))
                elif inv < self.reorder_point:
                    # Normal reorder
                    best_supplier = self._find_supplier(wh.id, product)
                    if best_supplier and best_supplier not in self.disrupted_nodes:
                        supplier = self.network.get_node(best_supplier)
                        available = supplier.inventory.get(product, 0) if supplier else 0
                        actual_qty = min(self.reorder_qty, available)
                        if actual_qty > 0 and supplier:
                            supplier.inventory[product] = available - actual_qty
                            edge = self._find_edge(best_supplier, wh.id)
                            transit = edge.transit_days if edge else 3
                            self.in_transit.append((day + transit, wh.id, product, actual_qty))
                            self.metrics.reorder_decisions += 1
                            day_decisions.append(AgentDecision(
                                day=day, agent_id=wh.id, action="reorder",
                                reasoning=f"Below reorder point: {inv} {product}, ordered {actual_qty}",
                                details={"product": product, "quantity": actual_qty}
                            ))

        # 5. Store reorder from warehouse
        for store in self.network.get_stores():
            for product in self.dataset.products:
                inv = store.inventory.get(product, 0)
                if inv < 30:
                    # Find nearest warehouse
                    best_wh = self._find_warehouse(store.id)
                    if best_wh:
                        wh = self.network.get_node(best_wh)
                        if wh:
                            wh_inv = wh.inventory.get(product, 0)
                            transfer = min(100, wh_inv)
                            if transfer > 0:
                                wh.inventory[product] = wh_inv - transfer
                                edge = self._find_edge(best_wh, store.id)
                                transit = edge.transit_days if edge else 1
                                self.in_transit.append((day + transit, store.id, product, transfer))
                                self.metrics.reorder_decisions += 1

        self.events_log.extend(day_events)
        self.decisions_log.extend(day_decisions)

        fill_rate = self.metrics.fulfilled_demand / max(1, self.metrics.total_real_demand)

        return DaySnapshot(
            day=day,
            inventories={n.id: dict(n.inventory) for n in self.network.nodes.values()},
            events=day_events,
            decisions=day_decisions,
            metrics={
                "fill_rate": round(fill_rate, 4),
                "stockout_count": self.metrics.stockout_events,
                "total_orders": self.metrics.reorder_decisions,
                "active_disruptions": len(self.disrupted_nodes),
                "in_transit_shipments": len(self.in_transit),
            },
            in_transit=[{"from": "S_FOODS", "to": s[1], "product": s[2], "qty": s[3], "days_left": s[0] - day} for s in self.in_transit[:5]],
            disruptions={n: True for n in self.disrupted_nodes},
        )

    def _find_supplier(self, warehouse_id: str, product: str) -> Optional[str]:
        edges = self.network.get_edges_to(warehouse_id)
        for e in edges:
            node = self.network.get_node(e.source_id)
            if node and node.node_type == NodeType.SUPPLIER:
                if node.inventory.get(product, 0) > 0:
                    return e.source_id
        return None

    def _find_warehouse(self, store_id: str) -> Optional[str]:
        edges = self.network.get_edges_to(store_id)
        best = None
        best_transit = 999
        for e in edges:
            node = self.network.get_node(e.source_id)
            if node and node.node_type == NodeType.WAREHOUSE:
                if e.transit_days < best_transit:
                    best = e.source_id
                    best_transit = e.transit_days
        return best

    def _find_edge(self, source_id: str, target_id: str):
        for e in self.network.edges:
            if e.source_id == source_id and e.target_id == target_id:
                return e
        return None

    def get_summary_report(self) -> dict:
        return self.metrics.to_dict()
