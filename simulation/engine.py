# -*- coding: utf-8 -*-
"""
Core simulation engine for supply chain multi-agent simulation.
Discrete time-step engine (1 step = 1 day).
"""
import random
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from .network import SupplyChainNetwork, NodeType, Edge


@dataclass
class Event:
    day: int
    event_type: str  # "demand", "disruption", "reorder", "shipment", "stockout", "recovery"
    source_id: str
    target_id: str = ""
    product: str = ""
    quantity: int = 0
    description: str = ""
    severity: str = "info"  # "info", "warning", "critical"


@dataclass
class AgentDecision:
    day: int
    agent_id: str
    action: str
    reasoning: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DaySnapshot:
    day: int
    inventories: Dict[str, Dict[str, int]]  # node_id -> {product: qty}
    events: List[Event]
    decisions: List[AgentDecision]
    metrics: Dict[str, float]
    in_transit: List[Dict]
    disruptions: Dict[str, bool]  # node_id -> is_disrupted


class SupplyChainEngine:
    """
    Multi-agent supply chain simulation engine.
    Each node acts as an autonomous agent with its own decision logic.
    """

    def __init__(self, network: SupplyChainNetwork, seed: int = 42):
        self.network = network
        self.rng = random.Random(seed)
        self.day = 0
        self.history: List[DaySnapshot] = []
        self.events_log: List[Event] = []
        self.decisions_log: List[AgentDecision] = []

        # Disruption state
        self.disrupted_nodes: Dict[str, int] = {}  # node_id -> days_remaining

        # Metrics tracking
        self.total_demand = 0
        self.fulfilled_demand = 0
        self.stockout_count = 0
        self.total_orders = 0

        # Reorder points (agent parameters)
        self.reorder_points: Dict[str, int] = {}
        self.reorder_quantities: Dict[str, int] = {}
        for node in network.get_warehouses():
            self.reorder_points[node.id] = 300
            self.reorder_quantities[node.id] = 600
        for node in network.get_stores():
            self.reorder_points[node.id] = 40
            self.reorder_quantities[node.id] = 100

    def inject_disruption(self, node_id: str, duration_days: int, description: str = ""):
        """Schedule a disruption for a node."""
        self.disrupted_nodes[node_id] = duration_days
        self.events_log.append(Event(
            day=self.day, event_type="disruption", source_id=node_id,
            description=description or f"Disruption at {node_id} for {duration_days} days",
            severity="critical"
        ))

    def step(self) -> DaySnapshot:
        """Advance simulation by one day."""
        self.day += 1
        day_events = []
        day_decisions = []

        # 1. Process disruptions
        expired = []
        for node_id, remaining in self.disrupted_nodes.items():
            if remaining <= 1:
                expired.append(node_id)
                day_events.append(Event(
                    day=self.day, event_type="recovery", source_id=node_id,
                    description=f"{node_id} recovered from disruption",
                    severity="info"
                ))
            else:
                self.disrupted_nodes[node_id] = remaining - 1
        for node_id in expired:
            del self.disrupted_nodes[node_id]

        # 2. Process in-transit shipments
        for edge in self.network.edges:
            arrived = []
            for shipment in edge.in_transit:
                shipment["days_left"] -= 1
                if shipment["days_left"] <= 0:
                    arrived.append(shipment)
            for shipment in arrived:
                edge.in_transit.remove(shipment)
                target = self.network.get_node(edge.target_id)
                if target:
                    product = shipment["product"]
                    qty = shipment["quantity"]
                    target.inventory[product] = target.inventory.get(product, 0) + qty
                    day_events.append(Event(
                        day=self.day, event_type="shipment", source_id=edge.source_id,
                        target_id=edge.target_id, product=product, quantity=qty,
                        description=f"Shipment arrived: {qty} {product} → {target.name}"
                    ))

        # 3. Store agents: generate demand & check inventory
        for store in self.network.get_stores():
            base_demand = store.metadata.get("daily_demand", 25)
            # Add demand variation
            demand = max(0, int(self.rng.gauss(base_demand, base_demand * 0.3)))

            # Weekend boost
            if self.day % 7 in [5, 6]:
                demand = int(demand * 1.5)

            for product in ["spice_base", "chili_oil"]:
                product_demand = demand if product == "spice_base" else int(demand * 0.6)
                self.total_demand += product_demand
                available = store.inventory.get(product, 0)

                if available >= product_demand:
                    store.inventory[product] = available - product_demand
                    self.fulfilled_demand += product_demand
                    day_events.append(Event(
                        day=self.day, event_type="demand", source_id=store.id,
                        product=product, quantity=product_demand,
                        description=f"{store.name}: sold {product_demand} {product}"
                    ))
                else:
                    # Partial fulfillment
                    store.inventory[product] = 0
                    self.fulfilled_demand += available
                    shortage = product_demand - available
                    self.stockout_count += 1
                    day_events.append(Event(
                        day=self.day, event_type="stockout", source_id=store.id,
                        product=product, quantity=shortage,
                        description=f"⚠️ {store.name}: STOCKOUT {product} (short {shortage})",
                        severity="warning"
                    ))

            # Store agent: reorder decision
            for product in store.inventory:
                if store.inventory[product] < self.reorder_points.get(store.id, 30):
                    qty = self.reorder_quantities.get(store.id, 80)
                    # Find supplying warehouse
                    edges = self.network.get_edges_to(store.id)
                    best_edge = None
                    for e in edges:
                        wh = self.network.get_node(e.source_id)
                        if wh and wh.node_type == NodeType.WAREHOUSE:
                            if wh.inventory.get(product, 0) >= qty:
                                if best_edge is None or e.transit_days < best_edge.transit_days:
                                    best_edge = e
                    if best_edge:
                        wh = self.network.get_node(best_edge.source_id)
                        wh.inventory[product] = wh.inventory.get(product, 0) - qty
                        best_edge.in_transit.append({
                            "product": product, "quantity": qty,
                            "days_left": best_edge.transit_days
                        })
                        self.total_orders += 1
                        day_decisions.append(AgentDecision(
                            day=self.day, agent_id=store.id, action="reorder",
                            reasoning=f"Inventory below reorder point ({store.inventory[product]}<{self.reorder_points.get(store.id, 30)})",
                            details={"product": product, "qty": qty, "from": wh.id,
                                     "transit_days": best_edge.transit_days}
                        ))

        # 4. Warehouse agents: reorder from suppliers
        for wh in self.network.get_warehouses():
            for product in wh.inventory:
                if wh.inventory[product] < self.reorder_points.get(wh.id, 200):
                    qty = self.reorder_quantities.get(wh.id, 500)
                    # Find best supplier
                    edges = self.network.get_edges_to(wh.id)
                    best_edge = None
                    for e in edges:
                        supplier = self.network.get_node(e.source_id)
                        if (supplier and supplier.node_type == NodeType.SUPPLIER
                            and supplier.id not in self.disrupted_nodes):
                            if supplier.inventory.get(product, 0) >= qty:
                                if best_edge is None or e.transit_days < best_edge.transit_days:
                                    best_edge = e
                    if best_edge:
                        supplier = self.network.get_node(best_edge.source_id)
                        supplier.inventory[product] = supplier.inventory.get(product, 0) - qty
                        best_edge.in_transit.append({
                            "product": product, "quantity": qty,
                            "days_left": best_edge.transit_days
                        })
                        self.total_orders += 1
                        day_decisions.append(AgentDecision(
                            day=self.day, agent_id=wh.id, action="reorder",
                            reasoning=f"Warehouse inventory low ({wh.inventory[product]}<{self.reorder_points.get(wh.id, 200)}). "
                                      f"{'Switched supplier due to disruption' if len(self.disrupted_nodes) > 0 else 'Normal reorder'}",
                            details={"product": product, "qty": qty, "from": supplier.id}
                        ))
                    elif len(self.disrupted_nodes) > 0:
                        # Try alternative supplier (adaptive behavior)
                        for e in edges:
                            supplier = self.network.get_node(e.source_id)
                            if (supplier and supplier.node_type == NodeType.SUPPLIER
                                and supplier.id not in self.disrupted_nodes
                                and supplier.inventory.get(product, 0) > 0):
                                actual_qty = min(qty, supplier.inventory.get(product, 0))
                                supplier.inventory[product] -= actual_qty
                                e.in_transit.append({
                                    "product": product, "quantity": actual_qty,
                                    "days_left": e.transit_days
                                })
                                day_decisions.append(AgentDecision(
                                    day=self.day, agent_id=wh.id, action="emergency_reorder",
                                    reasoning=f"Primary supplier disrupted. Emergency order from {supplier.name} (partial: {actual_qty}/{qty})",
                                    details={"product": product, "qty": actual_qty, "from": supplier.id}
                                ))
                                break

        # 5. Supplier agents: produce (replenish inventory)
        for supplier in self.network.get_suppliers():
            if supplier.id not in self.disrupted_nodes:
                for product in supplier.inventory:
                    production_rate = supplier.metadata.get("production_rate", 200)
                    supplier.inventory[product] = min(
                        supplier.capacity,
                        supplier.inventory[product] + production_rate
                    )

        # Build snapshot
        in_transit_summary = []
        for edge in self.network.edges:
            for s in edge.in_transit:
                in_transit_summary.append({
                    "from": edge.source_id, "to": edge.target_id,
                    "product": s["product"], "quantity": s["quantity"],
                    "days_left": s["days_left"]
                })

        fill_rate = self.fulfilled_demand / max(1, self.total_demand)
        snapshot = DaySnapshot(
            day=self.day,
            inventories={
                n.id: dict(n.inventory) for n in self.network.nodes.values()
            },
            events=day_events,
            decisions=day_decisions,
            metrics={
                "fill_rate": round(fill_rate, 4),
                "stockout_count": self.stockout_count,
                "total_orders": self.total_orders,
                "active_disruptions": len(self.disrupted_nodes),
                "in_transit_shipments": len(in_transit_summary),
            },
            in_transit=in_transit_summary,
            disruptions={nid: True for nid in self.disrupted_nodes}
        )

        self.history.append(snapshot)
        self.events_log.extend(day_events)
        self.decisions_log.extend(day_decisions)

        return snapshot

    def run(self, days: int, disruptions: Optional[List[Dict]] = None) -> List[DaySnapshot]:
        """
        Run simulation for N days with optional scheduled disruptions.

        disruptions: [{"day": 12, "node_id": "S1", "duration": 8, "description": "..."}]
        """
        disruptions = disruptions or []
        disruption_map = {}
        for d in disruptions:
            disruption_map[d["day"]] = d

        results = []
        for _ in range(days):
            # Check for scheduled disruptions
            next_day = self.day + 1
            if next_day in disruption_map:
                d = disruption_map[next_day]
                self.inject_disruption(d["node_id"], d["duration"], d.get("description", ""))

            snapshot = self.step()
            results.append(snapshot)

        return results

    def get_summary_report(self) -> Dict[str, Any]:
        """Generate a summary report of the simulation."""
        if not self.history:
            return {}

        fill_rates = [s.metrics["fill_rate"] for s in self.history]
        stockout_days = sum(1 for s in self.history if any(
            e.event_type == "stockout" for e in s.events
        ))

        # Find worst day
        worst_day = min(self.history, key=lambda s: s.metrics["fill_rate"])

        # Count decisions by type
        decision_types = {}
        for d in self.decisions_log:
            decision_types[d.action] = decision_types.get(d.action, 0) + 1

        return {
            "total_days": len(self.history),
            "avg_fill_rate": round(sum(fill_rates) / len(fill_rates), 4),
            "min_fill_rate": round(min(fill_rates), 4),
            "min_fill_rate_day": worst_day.day,
            "stockout_days": stockout_days,
            "total_stockout_events": self.stockout_count,
            "total_orders": self.total_orders,
            "total_events": len(self.events_log),
            "total_decisions": len(self.decisions_log),
            "decision_breakdown": decision_types,
            "disruption_events": sum(1 for e in self.events_log if e.event_type == "disruption"),
        }
