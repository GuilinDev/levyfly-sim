#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Walmart M5 → LevyFly Adapter

Converts M5 demand data into a supply chain simulation with:
- Real demand patterns (from M5 sales data)
- Simulated supply network (suppliers → DCs → stores)
- Agent decisions evaluated against actual demand reality

The key insight: we know the REAL demand. So we can measure whether
the agent's reorder decisions would have prevented stockouts.
"""
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from simulation.network import SupplyChainNetwork, Node, Edge, NodeType


@dataclass
class DailyDemand:
    """Real demand for a store-product pair on a given day."""
    day: int
    store_id: str
    product: str
    quantity: int


@dataclass
class M5Dataset:
    """Parsed M5 dataset ready for simulation."""
    stores: List[str]
    products: List[str]
    days: int
    daily_demands: Dict[int, List[DailyDemand]]  # day → list of demands
    events: Dict[int, str]                         # day → event name
    disruption_periods: List[Tuple[int, int, str]] # (start, end, description)
    prices: Dict[str, Dict[str, float]]            # store → product → avg price


def load_m5_data(data_dir: str, max_days: int = 365) -> M5Dataset:
    """
    Load M5 data and convert to simulation-ready format.

    Args:
        data_dir: Path to directory with sales_train.csv, calendar.csv, sell_prices.csv
        max_days: Maximum number of days to load

    Returns:
        M5Dataset
    """
    print(f"📦 Loading M5 data from {data_dir}...")

    # ── Load calendar ──
    events = {}
    calendar_path = os.path.join(data_dir, "calendar.csv")
    if os.path.exists(calendar_path):
        with open(calendar_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d_col = row.get("d", "")
                day_num = int(d_col.replace("d_", "")) if d_col.startswith("d_") else 0
                event = row.get("event_name_1", "").strip()
                if event and day_num > 0:
                    events[day_num] = event

    # ── Load sales ──
    # Support both M5 naming conventions
    sales_path = os.path.join(data_dir, "sales_train_validation.csv")
    if not os.path.exists(sales_path):
        sales_path = os.path.join(data_dir, "sales_train.csv")
    daily_demands = defaultdict(list)
    stores_set = set()
    products_set = set()

    with open(sales_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            store_id = row["store_id"]
            # Use dept_id as product category (aggregated)
            product = row["dept_id"]
            stores_set.add(store_id)
            products_set.add(product)

            for d in range(1, min(max_days + 1, 2000)):
                col = f"d_{d}"
                if col not in row:
                    break
                qty = int(row[col])
                if qty > 0:
                    daily_demands[d].append(DailyDemand(
                        day=d, store_id=store_id,
                        product=product, quantity=qty
                    ))

    # Aggregate demands by store+product+day
    agg_demands = defaultdict(list)
    for day, demands in daily_demands.items():
        # Group by store+product
        grouped = defaultdict(int)
        for d in demands:
            grouped[(d.store_id, d.product)] += d.quantity
        for (store_id, product), qty in grouped.items():
            agg_demands[day].append(DailyDemand(
                day=day, store_id=store_id,
                product=product, quantity=qty
            ))

    # ── Load prices ──
    prices = defaultdict(lambda: defaultdict(list))
    prices_path = os.path.join(data_dir, "sell_prices.csv")
    if os.path.exists(prices_path):
        with open(prices_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                store = row["store_id"]
                # Map item to dept
                item = row["item_id"]
                dept = "_".join(item.split("_")[:2])
                price = float(row["sell_price"])
                prices[store][dept].append(price)

    # Average prices
    avg_prices = {}
    for store, products in prices.items():
        avg_prices[store] = {}
        for product, price_list in products.items():
            avg_prices[store][product] = sum(price_list) / len(price_list)

    # ── Detect disruption periods ──
    # Look for sustained demand drops (>30% below rolling average)
    disruptions = detect_disruptions(agg_demands, max_days)

    actual_days = min(max_days, max(agg_demands.keys()) if agg_demands else 0)
    stores = sorted(stores_set)
    products = sorted(products_set)

    print(f"   Stores: {len(stores)} {stores}")
    print(f"   Products: {len(products)} {products}")
    print(f"   Days: {actual_days}")
    print(f"   Events: {len(events)}")
    print(f"   Detected disruptions: {len(disruptions)}")

    return M5Dataset(
        stores=stores,
        products=products,
        days=actual_days,
        daily_demands=dict(agg_demands),
        events=events,
        disruption_periods=disruptions,
        prices=avg_prices,
    )


def detect_disruptions(
    daily_demands: Dict[int, List[DailyDemand]],
    max_days: int,
    window: int = 14,
    threshold: float = 0.3,
) -> List[Tuple[int, int, str]]:
    """
    Detect supply disruption periods by finding sustained demand anomalies.
    """
    # Calculate daily total demand
    daily_totals = {}
    for d in range(1, max_days + 1):
        demands = daily_demands.get(d, [])
        daily_totals[d] = sum(dd.quantity for dd in demands)

    # Rolling average
    disruptions = []
    in_disruption = False
    disruption_start = 0

    for d in range(window + 1, max_days + 1):
        avg = sum(daily_totals.get(d - i, 0) for i in range(1, window + 1)) / window
        current = daily_totals.get(d, 0)

        if avg > 0 and current < avg * (1 - threshold):
            if not in_disruption:
                in_disruption = True
                disruption_start = d
        else:
            if in_disruption and d - disruption_start >= 3:
                disruptions.append((
                    disruption_start, d - 1,
                    f"Demand anomaly detected (Day {disruption_start}-{d-1})"
                ))
            in_disruption = False

    return disruptions


def build_network_from_m5(dataset: M5Dataset) -> SupplyChainNetwork:
    """
    Build a supply chain network matching the M5 store structure.
    Adds synthetic suppliers and warehouses.
    """
    net = SupplyChainNetwork()

    # Map states to regions
    state_regions = {"CA": "West", "TX": "South", "WI": "Midwest"}

    # Add suppliers (one per product category)
    # Calculate per-product demand for supplier sizing
    from collections import defaultdict as _dd
    _product_demand = _dd(int)
    _demand_days = 0
    for day, demands in dataset.daily_demands.items():
        _demand_days += 1
        for d in demands:
            _product_demand[d.product] += d.quantity
    _avg_per_product = {p: max(100, q // max(1, _demand_days)) for p, q in _product_demand.items()}

    # Suppliers with 30-day production capacity
    supplier_map = {
        "FOODS": ("S_FOODS", "Food Supplier Co.", (50, 150)),
        "HOBBIES": ("S_HOBBIES", "Hobbies Supplier", (50, 250)),
        "HOUSEHOLD": ("S_HOUSE", "Household Goods Inc.", (50, 350)),
    }

    for cat, (sid, name, pos) in supplier_map.items():
        cat_products = [p for p in dataset.products if p.startswith(cat)]
        inv = {p: _avg_per_product.get(p, 100) * 30 for p in cat_products}
        node = Node(
            id=sid, name=name,
            node_type=NodeType.SUPPLIER,
            position=pos,
            capacity=1000000,
            inventory=inv,
        )
        net.add_node(node)

    # Add regional warehouses — sized to real demand
    # Average daily demand ~25K across all stores, so warehouses need ~5-7 days buffer
    warehouses = {
        "W_WEST": ("West Coast DC", (300, 100), ["CA"]),
        "W_SOUTH": ("South DC", (300, 250), ["TX"]),
        "W_MIDWEST": ("Midwest DC", (300, 400), ["WI"]),
    }

    # Calculate per-product average daily demand for sizing
    from collections import defaultdict
    product_demand = defaultdict(int)
    demand_days = 0
    for day, demands in dataset.daily_demands.items():
        demand_days += 1
        for d in demands:
            product_demand[d.product] += d.quantity
    avg_per_product = {p: max(100, q // max(1, demand_days)) for p, q in product_demand.items()}

    for wid, (name, pos, states) in warehouses.items():
        # 7-day buffer per product
        inv = {p: avg * 7 for p, avg in avg_per_product.items()}
        node = Node(
            id=wid, name=name,
            node_type=NodeType.WAREHOUSE,
            position=pos,
            capacity=500000,
            inventory=inv,
        )
        net.add_node(node)

    # Add stores
    store_positions = {
        "CA_1": (600, 50), "CA_2": (600, 100), "CA_3": (600, 150), "CA_4": (600, 200),
        "TX_1": (600, 250), "TX_2": (600, 300), "TX_3": (600, 350),
        "WI_1": (600, 400), "WI_2": (600, 450), "WI_3": (600, 500),
    }

    for store_id in dataset.stores:
        pos = store_positions.get(store_id, (600, 300))
        state = store_id.split("_")[0]
        # 3-day buffer per product for stores
        inv = {p: avg * 3 for p, avg in avg_per_product.items()}
        node = Node(
            id=store_id, name=f"Walmart {store_id}",
            node_type=NodeType.STORE,
            position=pos,
            capacity=5000,
            inventory=inv,
            metadata={"state": state},
        )
        net.add_node(node)

    # Add edges: Supplier → Warehouse
    for cat, (sid, _, _) in supplier_map.items():
        for wid in warehouses:
            net.add_edge(Edge(source_id=sid, target_id=wid, transit_days=3, cost_per_unit=1.0))

    # Add edges: Warehouse → Store (based on region)
    for wid, (_, _, states) in warehouses.items():
        for store_id in dataset.stores:
            state = store_id.split("_")[0]
            if state in states:
                net.add_edge(Edge(source_id=wid, target_id=store_id, transit_days=1, cost_per_unit=0.5))
            else:
                net.add_edge(Edge(source_id=wid, target_id=store_id, transit_days=3, cost_per_unit=1.5))

    return net


if __name__ == "__main__":
    dataset = load_m5_data("data/walmart_m5/", max_days=90)
    network = build_network_from_m5(dataset)
    print(f"\n🏗️ Network: {len(network.get_suppliers())}S → {len(network.get_warehouses())}W → {len(network.get_stores())}R")
    print(f"   Edges: {len(network.edges)}")
