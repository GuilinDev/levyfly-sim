# -*- coding: utf-8 -*-
"""
Supply chain network topology definition.
Defines nodes (suppliers, warehouses, stores) and edges (transport links).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from enum import Enum


class NodeType(Enum):
    SUPPLIER = "supplier"
    WAREHOUSE = "warehouse"
    STORE = "store"


@dataclass
class Node:
    id: str
    name: str
    node_type: NodeType
    position: Tuple[float, float]  # (x, y) for visualization
    capacity: int = 1000
    inventory: Dict[str, int] = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)


@dataclass
class Edge:
    source_id: str
    target_id: str
    transit_days: int = 2
    cost_per_unit: float = 1.0
    active: bool = True
    in_transit: List[Dict] = field(default_factory=list)


class SupplyChainNetwork:
    """
    Defines the supply chain network topology.
    """

    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []

    def add_node(self, node: Node):
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge):
        self.edges.append(edge)

    def get_node(self, node_id: str) -> Node:
        return self.nodes.get(node_id)

    def get_suppliers(self) -> List[Node]:
        return [n for n in self.nodes.values() if n.node_type == NodeType.SUPPLIER]

    def get_warehouses(self) -> List[Node]:
        return [n for n in self.nodes.values() if n.node_type == NodeType.WAREHOUSE]

    def get_stores(self) -> List[Node]:
        return [n for n in self.nodes.values() if n.node_type == NodeType.STORE]

    def get_edges_from(self, node_id: str) -> List[Edge]:
        return [e for e in self.edges if e.source_id == node_id]

    def get_edges_to(self, node_id: str) -> List[Edge]:
        return [e for e in self.edges if e.target_id == node_id]


def build_demo_network() -> SupplyChainNetwork:
    """
    Build the demo supply chain network:
    3 Suppliers → 2 Warehouses → 5 Retail Stores
    """
    net = SupplyChainNetwork()

    # Suppliers (left side)
    net.add_node(Node(
        id="S1", name="Sichuan Spice Co.", node_type=NodeType.SUPPLIER,
        position=(50, 100), capacity=5000,
        inventory={"spice_base": 3000, "chili_oil": 2000},
        metadata={"region": "Chengdu", "specialty": "hot pot base"}
    ))
    net.add_node(Node(
        id="S2", name="Yunnan Fresh Foods", node_type=NodeType.SUPPLIER,
        position=(50, 300), capacity=3000,
        inventory={"vegetables": 2000, "mushrooms": 1500},
        metadata={"region": "Kunming", "specialty": "fresh produce"}
    ))
    net.add_node(Node(
        id="S3", name="Guangdong Packaging", node_type=NodeType.SUPPLIER,
        position=(50, 500), capacity=8000,
        inventory={"containers": 5000, "labels": 6000},
        metadata={"region": "Shenzhen", "specialty": "packaging"}
    ))

    # Warehouses (center)
    net.add_node(Node(
        id="W1", name="East Coast DC", node_type=NodeType.WAREHOUSE,
        position=(350, 180), capacity=10000,
        inventory={"spice_base": 500, "chili_oil": 300, "vegetables": 200,
                   "mushrooms": 150, "containers": 800, "labels": 1000},
        metadata={"region": "New Jersey"}
    ))
    net.add_node(Node(
        id="W2", name="West Coast DC", node_type=NodeType.WAREHOUSE,
        position=(350, 420), capacity=8000,
        inventory={"spice_base": 400, "chili_oil": 200, "vegetables": 150,
                   "mushrooms": 100, "containers": 600, "labels": 800},
        metadata={"region": "Los Angeles"}
    ))

    # Retail Stores (right side)
    stores = [
        ("R1", "NYC Flagship", (650, 60), "Manhattan"),
        ("R2", "NJ Edison", (650, 180), "Edison, NJ"),
        ("R3", "Philly Store", (650, 300), "Philadelphia"),
        ("R4", "LA Downtown", (650, 420), "Los Angeles"),
        ("R5", "SF Mission", (650, 540), "San Francisco"),
    ]
    for sid, name, pos, region in stores:
        net.add_node(Node(
            id=sid, name=name, node_type=NodeType.STORE,
            position=pos, capacity=500,
            inventory={"spice_base": 50, "chili_oil": 30,
                       "vegetables": 40, "mushrooms": 20},
            metadata={"region": region, "daily_demand": 25}
        ))

    # Edges: Suppliers → Warehouses
    for s_id in ["S1", "S2", "S3"]:
        for w_id in ["W1", "W2"]:
            transit = 3 if w_id == "W1" else 5  # East coast closer to Asia shipping
            net.add_edge(Edge(source_id=s_id, target_id=w_id, transit_days=transit))

    # Edges: Warehouses → Stores
    # W1 (East Coast) serves R1, R2, R3
    for r_id in ["R1", "R2", "R3"]:
        net.add_edge(Edge(source_id="W1", target_id=r_id, transit_days=1))
    # W2 (West Coast) serves R4, R5
    for r_id in ["R4", "R5"]:
        net.add_edge(Edge(source_id="W2", target_id=r_id, transit_days=1))
    # Cross-region backup routes (slower)
    net.add_edge(Edge(source_id="W1", target_id="R4", transit_days=4))
    net.add_edge(Edge(source_id="W1", target_id="R5", transit_days=5))
    net.add_edge(Edge(source_id="W2", target_id="R1", transit_days=4))
    net.add_edge(Edge(source_id="W2", target_id="R2", transit_days=4))
    net.add_edge(Edge(source_id="W2", target_id="R3", transit_days=4))

    return net
