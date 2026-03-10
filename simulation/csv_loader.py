# -*- coding: utf-8 -*-
"""
CSV data loader — builds a SupplyChainNetwork from CSV files.
This is the "dump your data in" interface.

Expected files:
  - network.csv:    node_id, name, type, capacity, region, x, y
  - routes.csv:     source, target, transit_days, cost_per_unit
  - inventory.csv:  node_id, product, quantity
  - disruptions.csv: day, node_id, duration, description
"""
import csv
import os
from typing import Dict, List, Tuple, Optional
from .network import SupplyChainNetwork, Node, Edge, NodeType


def _parse_node_type(t: str) -> NodeType:
    t = t.strip().lower()
    if t == "supplier":
        return NodeType.SUPPLIER
    elif t == "warehouse":
        return NodeType.WAREHOUSE
    elif t == "store":
        return NodeType.STORE
    raise ValueError(f"Unknown node type: {t}")


def load_network_from_csv(
    network_csv: str,
    routes_csv: str,
    inventory_csv: Optional[str] = None,
) -> SupplyChainNetwork:
    """
    Build a SupplyChainNetwork from CSV files.

    Args:
        network_csv: Path to nodes CSV
        routes_csv: Path to routes/edges CSV
        inventory_csv: Optional path to initial inventory CSV

    Returns:
        SupplyChainNetwork
    """
    net = SupplyChainNetwork()

    # Load nodes
    with open(network_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            node = Node(
                id=row["node_id"].strip(),
                name=row["name"].strip(),
                node_type=_parse_node_type(row["type"]),
                position=(float(row.get("x", 0)), float(row.get("y", 0))),
                capacity=int(row.get("capacity", 1000)),
                inventory={},
                metadata={"region": row.get("region", "")},
            )
            net.add_node(node)

    # Load routes
    with open(routes_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            edge = Edge(
                source_id=row["source"].strip(),
                target_id=row["target"].strip(),
                transit_days=int(row.get("transit_days", 2)),
                cost_per_unit=float(row.get("cost_per_unit", 1.0)),
            )
            net.add_edge(edge)

    # Load inventory
    if inventory_csv and os.path.exists(inventory_csv):
        with open(inventory_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                node_id = row["node_id"].strip()
                product = row["product"].strip()
                quantity = int(row["quantity"])
                node = net.get_node(node_id)
                if node:
                    node.inventory[product] = quantity

    return net


def load_disruptions_from_csv(filepath: str) -> List[Dict]:
    """
    Load disruption scenarios from CSV.

    Args:
        filepath: Path to disruptions CSV

    Returns:
        List of disruption dicts for engine.run()
    """
    disruptions = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            disruptions.append({
                "day": int(row["day"]),
                "node_id": row["node_id"].strip(),
                "duration": int(row["duration"]),
                "description": row.get("description", "").strip(),
            })
    return disruptions


def load_from_directory(data_dir: str) -> Tuple[SupplyChainNetwork, List[Dict]]:
    """
    Load everything from a data directory.
    Looks for: network.csv, routes.csv, inventory.csv, disruptions.csv

    Also accepts: *_network.csv, *_routes.csv, etc.

    Args:
        data_dir: Path to directory containing CSV files

    Returns:
        (network, disruptions)
    """
    files = os.listdir(data_dir)

    def find_file(keyword):
        for f in files:
            if keyword in f.lower() and f.endswith(".csv"):
                return os.path.join(data_dir, f)
        return None

    network_csv = find_file("network")
    routes_csv = find_file("route")
    inventory_csv = find_file("inventory")
    disruptions_csv = find_file("disruption")

    if not network_csv:
        raise FileNotFoundError(f"No *network*.csv found in {data_dir}")
    if not routes_csv:
        raise FileNotFoundError(f"No *route*.csv found in {data_dir}")

    network = load_network_from_csv(network_csv, routes_csv, inventory_csv)

    disruptions = []
    if disruptions_csv:
        disruptions = load_disruptions_from_csv(disruptions_csv)

    print(f"📂 Loaded from {data_dir}:")
    print(f"   Nodes: {len(network.nodes)} ({len(network.get_suppliers())}S / {len(network.get_warehouses())}W / {len(network.get_stores())}R)")
    print(f"   Routes: {len(network.edges)}")
    print(f"   Products: {sum(len(n.inventory) for n in network.nodes.values())} inventory entries")
    print(f"   Disruptions: {len(disruptions)} scheduled")

    return network, disruptions
