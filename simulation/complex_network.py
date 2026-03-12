#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complex Supply Chain Network with ~1600 Suppliers

Generates a realistic supply chain network following Walmart's power law distribution:
- 1-5 products: 45% of suppliers (720) → 10% of products (~305)
- 6-15: 28% (448) → 18% (~549)
- 16-40: 17% (272) → 24% (~732)
- 41-100: 7% (112) → 23% (~701)
- 101-300: 2.5% (40) → 17% (~518)
- 300+: 0.5% (8) → 8% (~244)

Total: ~1600 suppliers, 3049 products (from M5 dataset)
"""
import csv
import os
import sys
import random
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.network import SupplyChainNetwork, Node, Edge, NodeType


# Power law supplier tier configuration
# (tier_name, min_products, max_products, pct_suppliers, pct_products)
SUPPLIER_TIERS = [
    ("micro", 1, 5, 0.45, 0.10),       # 720 suppliers, 10% of products
    ("small", 6, 15, 0.28, 0.18),      # 448 suppliers, 18% of products
    ("medium", 16, 40, 0.17, 0.24),    # 272 suppliers, 24% of products
    ("large", 41, 100, 0.07, 0.23),    # 112 suppliers, 23% of products
    ("mega", 101, 300, 0.025, 0.17),   # 40 suppliers, 17% of products
    ("giant", 301, 500, 0.005, 0.08),  # 8 suppliers, 8% of products
]

# Geographic regions for suppliers
REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West", "International"]

# M5 stores
M5_STORES = ["CA_1", "CA_2", "CA_3", "CA_4", "TX_1", "TX_2", "TX_3", "WI_1", "WI_2", "WI_3"]
STORE_REGIONS = {
    "CA_1": "West", "CA_2": "West", "CA_3": "West", "CA_4": "West",
    "TX_1": "Southwest", "TX_2": "Southwest", "TX_3": "Southwest",
    "WI_1": "Midwest", "WI_2": "Midwest", "WI_3": "Midwest",
}


@dataclass
class SupplierMetadata:
    """Supplier information."""
    id: str
    name: str
    tier: str
    product_count: int
    products: List[str]
    region: str
    category: str  # Primary category: FOODS, HOBBIES, HOUSEHOLD


@dataclass
class ComplexNetworkData:
    """Data structure for the complex network."""
    suppliers: List[SupplierMetadata]
    products: List[str]
    stores: List[str]
    supplier_products: Dict[str, List[str]]  # supplier_id -> product list
    product_suppliers: Dict[str, List[str]]  # product -> supplier list
    network: SupplyChainNetwork


def load_m5_items(data_dir: str) -> Tuple[List[str], Dict[str, str]]:
    """
    Load all unique items from M5 sales_train_validation.csv.

    Returns:
        items: List of unique item_ids
        item_categories: Dict mapping item_id to category
    """
    sales_path = os.path.join(data_dir, "sales_train_validation.csv")
    if not os.path.exists(sales_path):
        sales_path = os.path.join(data_dir, "sales_train.csv")

    items = []
    item_categories = {}
    seen = set()

    with open(sales_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_id = row["item_id"]
            if item_id not in seen:
                items.append(item_id)
                item_categories[item_id] = row["cat_id"]
                seen.add(item_id)

    return items, item_categories


def generate_supplier_assignments(
    items: List[str],
    item_categories: Dict[str, str],
    target_suppliers: int = 1600,
    seed: int = 42
) -> Tuple[List[SupplierMetadata], Dict[str, List[str]], Dict[str, List[str]]]:
    """
    Generate suppliers following power law distribution and assign products.

    Algorithm:
    1. Calculate number of suppliers per tier based on percentages
    2. For each tier, calculate product count per supplier
    3. Assign products to suppliers, ensuring each product has at least one supplier
    4. Larger suppliers may supply products also supplied by smaller ones (overlap)
    """
    random.seed(seed)

    n_products = len(items)
    suppliers = []
    supplier_products = {}
    product_suppliers = defaultdict(list)

    # Group items by category
    cat_items = defaultdict(list)
    for item in items:
        cat = item_categories.get(item, "UNKNOWN")
        cat_items[cat].append(item)

    categories = list(cat_items.keys())
    supplier_id = 0

    # Track assigned products for each tier
    all_assigned = set()

    for tier_name, min_prod, max_prod, pct_suppliers, pct_products in SUPPLIER_TIERS:
        n_suppliers = max(1, int(target_suppliers * pct_suppliers))
        target_products = int(n_products * pct_products)

        # Products per supplier in this tier
        avg_products = max(min_prod, min(max_prod, target_products // max(1, n_suppliers)))

        # Select products for this tier - prefer unassigned first
        unassigned = [i for i in items if i not in all_assigned]
        tier_pool = unassigned[:target_products] if len(unassigned) >= target_products else unassigned + random.sample([i for i in items if i in all_assigned], min(target_products - len(unassigned), len(items)))

        for i in range(n_suppliers):
            supplier_id += 1
            sid = f"SUP_{supplier_id:04d}"

            # Vary product count within tier range
            n_prods = random.randint(min_prod, min(max_prod, max(min_prod, avg_products + random.randint(-2, 2))))

            # Select products for this supplier
            # Prefer products from same category, but allow some cross-category
            cat = random.choice(categories)
            cat_pool = [p for p in tier_pool if item_categories.get(p, "") == cat]
            other_pool = [p for p in tier_pool if item_categories.get(p, "") != cat]

            # 70% from primary category, 30% from others
            n_primary = min(len(cat_pool), int(n_prods * 0.7))
            n_other = min(len(other_pool), n_prods - n_primary)

            selected = random.sample(cat_pool, n_primary) if n_primary > 0 else []
            if n_other > 0 and other_pool:
                selected += random.sample(other_pool, n_other)

            # If we still need more, sample from any available
            if len(selected) < n_prods:
                remaining = [p for p in items if p not in selected]
                n_more = min(len(remaining), n_prods - len(selected))
                if n_more > 0:
                    selected += random.sample(remaining, n_more)

            # Record assignments
            supplier_products[sid] = selected
            for prod in selected:
                product_suppliers[prod].append(sid)
                all_assigned.add(prod)

            # Remove selected from tier pool for next supplier
            tier_pool = [p for p in tier_pool if p not in selected]

            # Determine region
            region = random.choice(REGIONS)

            # Create supplier metadata
            supplier = SupplierMetadata(
                id=sid,
                name=f"{tier_name.capitalize()} Supplier {supplier_id}",
                tier=tier_name,
                product_count=len(selected),
                products=selected,
                region=region,
                category=cat,
            )
            suppliers.append(supplier)

    # Ensure every product has at least one supplier
    orphaned = [p for p in items if p not in product_suppliers]
    if orphaned:
        # Assign orphaned products to random existing suppliers
        for prod in orphaned:
            sup = random.choice(suppliers)
            supplier_products[sup.id].append(prod)
            product_suppliers[prod].append(sup.id)
            sup.products.append(prod)
            sup.product_count += 1

    return suppliers, dict(supplier_products), dict(product_suppliers)


def build_complex_network(
    data_dir: str,
    target_suppliers: int = 1600,
    include_warehouses: bool = True,
    seed: int = 42
) -> ComplexNetworkData:
    """
    Build a complex supply chain network with ~1600 suppliers.

    Args:
        data_dir: Path to M5 data directory
        target_suppliers: Target number of suppliers (~1600)
        include_warehouses: If True, include DC layer; if False, direct supplier→store
        seed: Random seed for reproducibility

    Returns:
        ComplexNetworkData with full network information
    """
    print(f"Loading M5 items from {data_dir}...")
    items, item_categories = load_m5_items(data_dir)
    print(f"  Found {len(items)} unique items")

    print(f"Generating {target_suppliers} suppliers with power law distribution...")
    suppliers, supplier_products, product_suppliers = generate_supplier_assignments(
        items, item_categories, target_suppliers, seed
    )
    print(f"  Generated {len(suppliers)} suppliers")

    # Print tier distribution
    tier_counts = defaultdict(int)
    tier_products = defaultdict(int)
    for sup in suppliers:
        tier_counts[sup.tier] += 1
        tier_products[sup.tier] += sup.product_count

    print("\n  Tier Distribution:")
    for tier_name, _, _, _, _ in SUPPLIER_TIERS:
        print(f"    {tier_name:8s}: {tier_counts[tier_name]:4d} suppliers, {tier_products[tier_name]:5d} product assignments")

    # Build network
    net = SupplyChainNetwork()
    random.seed(seed)

    # Add suppliers
    # Position suppliers in a grid/circle layout by tier
    tier_positions = _calculate_supplier_positions(suppliers)

    for sup in suppliers:
        pos = tier_positions[sup.id]

        # Initial inventory based on tier size
        inv = {p: random.randint(50, 200) * (1 + SUPPLIER_TIERS[[t[0] for t in SUPPLIER_TIERS].index(sup.tier)][1] // 5)
               for p in sup.products}

        node = Node(
            id=sup.id,
            name=sup.name,
            node_type=NodeType.SUPPLIER,
            position=pos,
            capacity=1000 * sup.product_count,
            inventory=inv,
            metadata={
                "tier": sup.tier,
                "region": sup.region,
                "category": sup.category,
                "product_count": sup.product_count,
            }
        )
        net.add_node(node)

    # Add warehouses (3 regional DCs) if enabled
    if include_warehouses:
        warehouses = [
            ("DC_WEST", "West Coast DC", (400, 100), ["West"]),
            ("DC_SOUTH", "South DC", (400, 300), ["Southwest"]),
            ("DC_MIDWEST", "Midwest DC", (400, 500), ["Midwest", "Northeast", "Southeast", "International"]),
        ]

        for wid, name, pos, regions in warehouses:
            # Initial warehouse inventory - sample of all products
            inv = {p: random.randint(100, 500) for p in random.sample(items, min(500, len(items)))}

            node = Node(
                id=wid,
                name=name,
                node_type=NodeType.WAREHOUSE,
                position=pos,
                capacity=500000,
                inventory=inv,
                metadata={"regions": regions}
            )
            net.add_node(node)

    # Add stores
    store_positions = {
        "CA_1": (600, 50), "CA_2": (600, 100), "CA_3": (600, 150), "CA_4": (600, 200),
        "TX_1": (600, 250), "TX_2": (600, 300), "TX_3": (600, 350),
        "WI_1": (600, 400), "WI_2": (600, 450), "WI_3": (600, 500),
    }

    for store_id in M5_STORES:
        pos = store_positions.get(store_id, (600, 300))
        inv = {p: random.randint(10, 50) for p in random.sample(items, min(200, len(items)))}

        node = Node(
            id=store_id,
            name=f"Walmart {store_id}",
            node_type=NodeType.STORE,
            position=pos,
            capacity=5000,
            inventory=inv,
            metadata={"region": STORE_REGIONS.get(store_id, "Unknown")}
        )
        net.add_node(node)

    # Add edges
    if include_warehouses:
        # Suppliers → Warehouses (based on region matching)
        warehouse_regions = {
            "DC_WEST": ["West", "International"],
            "DC_SOUTH": ["Southwest", "Southeast"],
            "DC_MIDWEST": ["Midwest", "Northeast", "International"],
        }

        for sup in suppliers:
            # Connect to matching regional warehouse(s)
            for wid, regions in warehouse_regions.items():
                if sup.region in regions:
                    transit = random.randint(2, 5)
                    net.add_edge(Edge(
                        source_id=sup.id,
                        target_id=wid,
                        transit_days=transit,
                        cost_per_unit=1.0 + random.random() * 0.5
                    ))
                elif random.random() < 0.2:  # 20% chance of backup route
                    transit = random.randint(5, 8)
                    net.add_edge(Edge(
                        source_id=sup.id,
                        target_id=wid,
                        transit_days=transit,
                        cost_per_unit=1.5 + random.random() * 0.5
                    ))

        # Warehouses → Stores
        store_warehouse_map = {
            "CA_1": "DC_WEST", "CA_2": "DC_WEST", "CA_3": "DC_WEST", "CA_4": "DC_WEST",
            "TX_1": "DC_SOUTH", "TX_2": "DC_SOUTH", "TX_3": "DC_SOUTH",
            "WI_1": "DC_MIDWEST", "WI_2": "DC_MIDWEST", "WI_3": "DC_MIDWEST",
        }

        for store_id in M5_STORES:
            primary_dc = store_warehouse_map[store_id]
            # Primary route
            net.add_edge(Edge(source_id=primary_dc, target_id=store_id, transit_days=1, cost_per_unit=0.5))
            # Backup routes from other DCs
            for wid in ["DC_WEST", "DC_SOUTH", "DC_MIDWEST"]:
                if wid != primary_dc:
                    net.add_edge(Edge(source_id=wid, target_id=store_id, transit_days=3, cost_per_unit=1.0))
    else:
        # Direct supplier → store connections
        # Only top-tier suppliers connect directly to stores
        for sup in suppliers:
            if sup.tier in ["large", "mega", "giant"]:
                for store_id in M5_STORES:
                    if random.random() < 0.3:  # 30% connection probability
                        transit = random.randint(2, 7)
                        net.add_edge(Edge(
                            source_id=sup.id,
                            target_id=store_id,
                            transit_days=transit,
                            cost_per_unit=2.0
                        ))

    return ComplexNetworkData(
        suppliers=suppliers,
        products=items,
        stores=M5_STORES,
        supplier_products=supplier_products,
        product_suppliers=product_suppliers,
        network=net,
    )


def _calculate_supplier_positions(suppliers: List[SupplierMetadata]) -> Dict[str, Tuple[float, float]]:
    """
    Calculate positions for suppliers based on tier.
    Uses a layered circular layout with tiers at different radii.
    """
    positions = {}

    # Group by tier
    tier_groups = defaultdict(list)
    for sup in suppliers:
        tier_groups[sup.tier].append(sup)

    # Tier radii (inner to outer based on tier size)
    tier_order = ["giant", "mega", "large", "medium", "small", "micro"]
    tier_radii = {
        "giant": 50,
        "mega": 80,
        "large": 110,
        "medium": 140,
        "small": 170,
        "micro": 200,
    }

    center_x, center_y = 150, 300

    for tier in tier_order:
        sups = tier_groups[tier]
        n = len(sups)
        if n == 0:
            continue

        radius = tier_radii[tier]
        for i, sup in enumerate(sups):
            angle = (2 * math.pi * i) / n
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            positions[sup.id] = (x, y)

    return positions


def get_supplier_stats(data: ComplexNetworkData) -> Dict:
    """Get statistics about the supplier network."""
    tier_counts = defaultdict(int)
    tier_products = defaultdict(int)
    region_counts = defaultdict(int)
    category_counts = defaultdict(int)

    for sup in data.suppliers:
        tier_counts[sup.tier] += 1
        tier_products[sup.tier] += sup.product_count
        region_counts[sup.region] += 1
        category_counts[sup.category] += 1

    # Products with multiple suppliers
    multi_supplier_products = sum(1 for p, sups in data.product_suppliers.items() if len(sups) > 1)

    return {
        "total_suppliers": len(data.suppliers),
        "total_products": len(data.products),
        "total_stores": len(data.stores),
        "tier_distribution": dict(tier_counts),
        "tier_product_counts": dict(tier_products),
        "region_distribution": dict(region_counts),
        "category_distribution": dict(category_counts),
        "products_with_multiple_suppliers": multi_supplier_products,
        "avg_suppliers_per_product": sum(len(s) for s in data.product_suppliers.values()) / len(data.products),
        "network_edges": len(data.network.edges),
        "network_nodes": len(data.network.nodes),
    }


def get_top_suppliers(data: ComplexNetworkData, n: int = 20) -> List[SupplierMetadata]:
    """Get the top N suppliers by product count."""
    return sorted(data.suppliers, key=lambda s: s.product_count, reverse=True)[:n]


def get_supplier_by_id(data: ComplexNetworkData, supplier_id: str) -> Optional[SupplierMetadata]:
    """Get supplier metadata by ID."""
    for sup in data.suppliers:
        if sup.id == supplier_id:
            return sup
    return None


def get_products_by_supplier(data: ComplexNetworkData, supplier_id: str) -> List[str]:
    """Get all products supplied by a given supplier."""
    return data.supplier_products.get(supplier_id, [])


def get_suppliers_by_product(data: ComplexNetworkData, product: str) -> List[str]:
    """Get all suppliers for a given product."""
    return data.product_suppliers.get(product, [])


if __name__ == "__main__":
    # Test the module
    data_dir = "data/walmart_m5"

    print("=" * 60)
    print("Building Complex Supply Chain Network")
    print("=" * 60)

    data = build_complex_network(data_dir, target_suppliers=1600, seed=42)

    print("\n" + "=" * 60)
    print("Network Statistics")
    print("=" * 60)

    stats = get_supplier_stats(data)
    for key, value in stats.items():
        if isinstance(value, dict):
            print(f"\n{key}:")
            for k, v in value.items():
                print(f"  {k}: {v}")
        else:
            print(f"{key}: {value}")

    print("\n" + "=" * 60)
    print("Top 10 Suppliers")
    print("=" * 60)

    top = get_top_suppliers(data, 10)
    for i, sup in enumerate(top, 1):
        print(f"{i}. {sup.name} ({sup.tier}): {sup.product_count} products, {sup.region}, {sup.category}")

    print("\nNetwork built successfully!")
