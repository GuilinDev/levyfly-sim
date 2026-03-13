#!/usr/bin/env python3
"""
28-Day Daily Action List Generator

Generates a day-by-day operations checklist for store managers:
- Which products need restocking, how many units
- Which products are overstocked, reduce orders
- Based on demand forecast vs current inventory

This is NOT a prediction accuracy report. This is what a logistics person
opens every morning to know what to DO.
"""
import os, sys, argparse
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from validation.walmart.m5_adapter import load_m5_data, build_network_from_m5, M5Dataset


@dataclass
class ActionItem:
    store_id: str
    product: str
    action: str          # "RESTOCK" | "REDUCE" | "URGENT" | "OK"
    current_inventory: int
    predicted_demand: int
    days_of_cover: float
    restock_qty: int     # positive = order this many; negative = reduce order
    supplier_id: str
    reason: str


@dataclass
class DayActionList:
    day: int
    total_actions: int
    urgent_count: int
    restock_count: int
    reduce_count: int
    ok_count: int
    actions_by_store: Dict[str, List[ActionItem]]


def generate_action_lists(data_dir: str = "data/walmart_m5", days: int = 28,
                          safety_days: int = 3, target_days: int = 7) -> List[DayActionList]:
    """
    Generate daily action lists.
    
    Args:
        safety_days: If inventory covers < safety_days of demand → URGENT
        target_days: Restock target — order enough for this many days
    """
    dataset = load_m5_data(data_dir, max_days=days + 30)
    network = build_network_from_m5(dataset)
    
    stores = network.get_stores()
    suppliers = network.get_suppliers()
    
    # Build product → supplier mapping
    product_supplier = {}
    for edge in network.edges:
        src = network.get_node(edge.source_id)
        if src and "supplier" in str(src.node_type).lower():
            for p in src.inventory:
                product_supplier[p] = src.id
    
    # Track demand history for forecasting
    demand_history: Dict[tuple, list] = defaultdict(list)
    # Track current inventory (start from network initial state)
    inventory: Dict[tuple, int] = {}
    for store in stores:
        for product in dataset.products:
            inventory[(store.id, product)] = store.inventory.get(product, 0)
    
    all_days = []
    
    for day in range(1, days + 1):
        actions_by_store = defaultdict(list)
        urgent = restock = reduce = ok = 0
        
        # Get actual demand for today
        real_demands = dataset.daily_demands.get(day, [])
        day_demand = {}
        for d in real_demands:
            day_demand[(d.store_id, d.product)] = d.quantity
            demand_history[(d.store_id, d.product)].append(d.quantity)
        
        # For each store-product, generate action
        for store in stores:
            for product in dataset.products:
                key = (store.id, product)
                current_inv = inventory.get(key, 0)
                
                # Forecast: moving average of recent demand
                hist = demand_history.get(key, [])
                if len(hist) >= 3:
                    window = hist[-7:] if len(hist) >= 7 else hist
                    predicted_daily = sum(window) / len(window)
                else:
                    # Use today's actual or default
                    predicted_daily = day_demand.get(key, 0)
                
                if predicted_daily <= 0:
                    predicted_daily = 1  # avoid div by zero
                
                days_of_cover = current_inv / predicted_daily
                supplier = product_supplier.get(product, "unknown")
                
                if days_of_cover < safety_days:
                    # URGENT — will run out soon
                    needed = int(predicted_daily * target_days - current_inv)
                    needed = max(needed, int(predicted_daily * safety_days))
                    action = ActionItem(
                        store_id=store.id, product=product,
                        action="URGENT", current_inventory=current_inv,
                        predicted_demand=int(predicted_daily),
                        days_of_cover=days_of_cover, restock_qty=needed,
                        supplier_id=supplier,
                        reason=f"Only {days_of_cover:.1f} days of stock left! Order {needed} units immediately."
                    )
                    urgent += 1
                elif days_of_cover < target_days:
                    # RESTOCK — needs replenishment
                    needed = int(predicted_daily * target_days - current_inv)
                    action = ActionItem(
                        store_id=store.id, product=product,
                        action="RESTOCK", current_inventory=current_inv,
                        predicted_demand=int(predicted_daily),
                        days_of_cover=days_of_cover, restock_qty=needed,
                        supplier_id=supplier,
                        reason=f"{days_of_cover:.1f} days coverage. Restock {needed} units to reach {target_days}-day target."
                    )
                    restock += 1
                elif days_of_cover > target_days * 3:
                    # REDUCE — overstocked
                    excess = int(current_inv - predicted_daily * target_days)
                    action = ActionItem(
                        store_id=store.id, product=product,
                        action="REDUCE", current_inventory=current_inv,
                        predicted_demand=int(predicted_daily),
                        days_of_cover=days_of_cover, restock_qty=-excess,
                        supplier_id=supplier,
                        reason=f"{days_of_cover:.1f} days of stock (>{target_days*3} target). Reduce next order. Excess: {excess} units."
                    )
                    reduce += 1
                else:
                    action = ActionItem(
                        store_id=store.id, product=product,
                        action="OK", current_inventory=current_inv,
                        predicted_demand=int(predicted_daily),
                        days_of_cover=days_of_cover, restock_qty=0,
                        supplier_id=supplier,
                        reason=f"{days_of_cover:.1f} days coverage. No action needed."
                    )
                    ok += 1
                
                actions_by_store[store.id].append(action)
        
        # Consume today's demand from inventory
        for (sid, prod), qty in day_demand.items():
            inv = inventory.get((sid, prod), 0)
            inventory[(sid, prod)] = max(0, inv - qty)
            # Simulate restock arriving (simplified: if ordered, arrives in 3 days)
        
        # Simulate restocking for urgent items (they ordered, arrives ~day+3)
        if day >= 4:
            # Check what was urgent 3 days ago and add to inventory
            past_day = all_days[day - 4] if day - 4 < len(all_days) else None
            if past_day:
                for sid, store_actions in past_day.actions_by_store.items():
                    for a in store_actions:
                        if a.action in ("URGENT", "RESTOCK") and a.restock_qty > 0:
                            inventory[(a.store_id, a.product)] += a.restock_qty
        
        total = urgent + restock + reduce
        all_days.append(DayActionList(
            day=day, total_actions=total,
            urgent_count=urgent, restock_count=restock,
            reduce_count=reduce, ok_count=ok,
            actions_by_store=dict(actions_by_store)
        ))
    
    return all_days


def print_action_list(days: List[DayActionList], show_days: List[int] = None,
                      show_ok: bool = False):
    """Print action lists in logistics-friendly format."""
    print("=" * 70)
    print("28-DAY DAILY ACTION LIST — Operations Checklist")
    print("=" * 70)
    
    for day_report in days:
        if show_days and day_report.day not in show_days:
            continue
        
        print(f"\n{'─' * 70}")
        print(f"📋 DAY {day_report.day}")
        print(f"   🚨 Urgent: {day_report.urgent_count} | "
              f"📦 Restock: {day_report.restock_count} | "
              f"📉 Reduce: {day_report.reduce_count} | "
              f"✅ OK: {day_report.ok_count}")
        print(f"{'─' * 70}")
        
        for store_id in sorted(day_report.actions_by_store.keys()):
            store_actions = day_report.actions_by_store[store_id]
            # Only show actionable items (not OK) unless show_ok
            actionable = [a for a in store_actions if a.action != "OK"]
            if not actionable and not show_ok:
                continue
            
            print(f"\n  📍 {store_id}:")
            for a in sorted(store_actions, key=lambda x: {"URGENT": 0, "RESTOCK": 1, "REDUCE": 2, "OK": 3}[x.action]):
                if a.action == "OK" and not show_ok:
                    continue
                    
                icon = {"URGENT": "🚨", "RESTOCK": "📦", "REDUCE": "📉", "OK": "✅"}[a.action]
                
                if a.action == "URGENT":
                    print(f"    {icon} {a.product} — ORDER {a.restock_qty} units NOW")
                    print(f"       Inventory: {a.current_inventory} | Daily demand: ~{a.predicted_demand} | "
                          f"Coverage: {a.days_of_cover:.1f} days | Supplier: {a.supplier_id}")
                elif a.action == "RESTOCK":
                    print(f"    {icon} {a.product} — Restock {a.restock_qty} units")
                    print(f"       Inventory: {a.current_inventory} | Daily demand: ~{a.predicted_demand} | "
                          f"Coverage: {a.days_of_cover:.1f} days")
                elif a.action == "REDUCE":
                    print(f"    {icon} {a.product} — Reduce orders (excess: {-a.restock_qty} units)")
                    print(f"       Inventory: {a.current_inventory} | Daily demand: ~{a.predicted_demand} | "
                          f"Coverage: {a.days_of_cover:.1f} days")
                elif show_ok:
                    print(f"    {icon} {a.product} — No action ({a.days_of_cover:.1f} days coverage)")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("📊 28-DAY SUMMARY")
    total_urgent = sum(d.urgent_count for d in days)
    total_restock = sum(d.restock_count for d in days)
    total_reduce = sum(d.reduce_count for d in days)
    print(f"   Total urgent alerts: {total_urgent}")
    print(f"   Total restock orders: {total_restock}")
    print(f"   Total reduce recommendations: {total_reduce}")
    
    # Find peak action days
    peak_day = max(days, key=lambda d: d.urgent_count)
    print(f"   Peak urgency day: Day {peak_day.day} ({peak_day.urgent_count} urgent items)")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="28-Day Daily Action List")
    parser.add_argument("--data", default="data/walmart_m5", help="Data directory")
    parser.add_argument("--days", type=int, default=28, help="Number of days")
    parser.add_argument("--safety", type=int, default=3, help="Safety stock days")
    parser.add_argument("--target", type=int, default=7, help="Target coverage days")
    parser.add_argument("--show-ok", action="store_true", help="Show OK items too")
    parser.add_argument("--show-days", type=str, default=None,
                        help="Comma-separated days to show (e.g., 1,3,7,14,28)")
    args = parser.parse_args()
    
    show_days = None
    if args.show_days:
        show_days = [int(d) for d in args.show_days.split(",")]
    
    results = generate_action_lists(args.data, args.days, args.safety, args.target)
    print_action_list(results, show_days=show_days, show_ok=args.show_ok)
