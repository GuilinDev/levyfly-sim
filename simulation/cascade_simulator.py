#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supplier Disruption Cascade Simulator

Simulates cascade effects when suppliers fail in the 1600-supplier network.
Tracks direct impacts, capacity strain on alternatives, and domino effects.

Usage:
    python -m simulation.cascade_simulator --supplier SUP_0001 --duration 14
    python -m simulation.cascade_simulator --tier giant --duration 30
    python -m simulation.cascade_simulator --scenario worst_case
"""
import os
import sys
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.complex_network import (
    build_complex_network,
    ComplexNetworkData,
    SupplierMetadata,
    SUPPLIER_TIERS,
    M5_STORES,
)


@dataclass
class MitigationAction:
    """Recommended action to mitigate disruption impact."""
    action_type: str  # "reroute", "emergency_order", "substitute", "accept_stockout"
    product: str
    from_supplier: str
    to_supplier: Optional[str]
    affected_stores: List[str]
    priority: str  # "critical", "high", "medium", "low"
    description: str


@dataclass
class CascadeReport:
    """Report of cascade impact from supplier disruption."""
    # Input parameters
    failed_suppliers: List[str]
    disruption_duration_days: int

    # Direct impact
    affected_products: List[str]
    affected_stores: Dict[str, List[str]]  # store_id -> list of at-risk products

    # Risk assessment
    stockout_risk: Dict[str, float]  # store_id -> probability (0-1)
    single_sourced_products: List[str]  # products with no alternative supplier
    multi_sourced_products: List[str]  # products that can be rerouted

    # Capacity analysis
    supplier_capacity_strain: Dict[str, float]  # supplier_id -> capacity utilization (0-1+)
    overloaded_suppliers: List[str]  # suppliers pushed >100% capacity

    # Recovery
    recovery_time_days: int
    mitigation_actions: List[MitigationAction]

    # Cascade depth
    cascade_depth: int  # how many layers of suppliers affected
    secondary_failures: List[str]  # suppliers that fail due to overload

    # Summary stats
    total_products_at_risk: int
    total_stores_impacted: int
    estimated_revenue_impact_pct: float


class CascadeSimulator:
    """
    Simulates supplier disruption cascades in the complex 1600-supplier network.
    """

    # Capacity thresholds
    STRAIN_WARNING = 0.85  # 85% capacity = warning
    STRAIN_CRITICAL = 0.95  # 95% = critical
    STRAIN_FAILURE = 1.10  # 110% = secondary failure risk

    def __init__(self, data_dir: str = "data/walmart_m5", seed: int = 42):
        self.data_dir = data_dir
        self.seed = seed
        self.network_data: Optional[ComplexNetworkData] = None

        # Store-product mapping (which stores carry which products)
        # For simulation, assume all stores carry all products
        self.store_products: Dict[str, Set[str]] = {}

        # Supplier capacity (products they can supply per day)
        # Simplified: capacity = current_product_count * capacity_factor
        self.supplier_capacity: Dict[str, int] = {}

        # Base demand per product (simplified: uniform demand)
        self.product_daily_demand: Dict[str, int] = {}

    def load_network(self) -> ComplexNetworkData:
        """Load or build the complex network."""
        if self.network_data is None:
            print(f"Building 1600-supplier network from {self.data_dir}...")
            self.network_data = build_complex_network(
                self.data_dir, target_suppliers=1600, seed=self.seed
            )
            self._initialize_capacity_model()
        return self.network_data

    def _initialize_capacity_model(self):
        """Initialize supplier capacities and demand estimates."""
        data = self.network_data

        # Each store carries all products
        for store_id in M5_STORES:
            self.store_products[store_id] = set(data.products)

        # Supplier capacity based on tier
        tier_capacity_factor = {
            "micro": 2,    # Can handle 2x their current load
            "small": 2.5,
            "medium": 3,
            "large": 4,
            "mega": 5,
            "giant": 6,
        }

        for sup in data.suppliers:
            factor = tier_capacity_factor.get(sup.tier, 2)
            # Capacity = number of products * factor (simplified units per day)
            self.supplier_capacity[sup.id] = sup.product_count * factor * 10

        # Demand per product (simplified: 10-50 units per day per store)
        random.seed(self.seed)
        for product in data.products:
            self.product_daily_demand[product] = random.randint(10, 50) * len(M5_STORES)

    def get_supplier_by_tier(self, tier: str) -> Optional[str]:
        """Get a random supplier from the specified tier."""
        data = self.load_network()
        tier_suppliers = [s for s in data.suppliers if s.tier == tier]
        if not tier_suppliers:
            return None
        return random.choice(tier_suppliers).id

    def get_all_suppliers_by_tier(self, tier: str) -> List[str]:
        """Get all suppliers from the specified tier."""
        data = self.load_network()
        return [s.id for s in data.suppliers if s.tier == tier]

    def simulate_disruption(
        self,
        supplier_ids: List[str],
        duration_days: int,
        cascade_enabled: bool = True
    ) -> CascadeReport:
        """
        Simulate the cascade effect of one or more suppliers failing.

        Args:
            supplier_ids: List of supplier IDs that fail
            duration_days: How many days the disruption lasts
            cascade_enabled: If True, simulate secondary supplier failures

        Returns:
            CascadeReport with full impact analysis
        """
        data = self.load_network()

        # Track cascade state
        failed_suppliers = set(supplier_ids)
        secondary_failures = []
        cascade_depth = 0

        # Get directly affected products
        affected_products = set()
        for sup_id in failed_suppliers:
            products = data.supplier_products.get(sup_id, [])
            affected_products.update(products)

        # Categorize products by sourcing
        single_sourced = []
        multi_sourced = []

        for product in affected_products:
            suppliers = data.product_suppliers.get(product, [])
            active_suppliers = [s for s in suppliers if s not in failed_suppliers]
            if not active_suppliers:
                single_sourced.append(product)
            else:
                multi_sourced.append(product)

        # Calculate capacity strain on remaining suppliers
        supplier_load = defaultdict(float)  # supplier -> total demand redirected
        supplier_capacity_utilization = {}

        for product in multi_sourced:
            demand = self.product_daily_demand.get(product, 100)
            suppliers = data.product_suppliers.get(product, [])
            active_suppliers = [s for s in suppliers if s not in failed_suppliers]

            if active_suppliers:
                # Distribute demand among active suppliers
                per_supplier = demand / len(active_suppliers)
                for sup_id in active_suppliers:
                    supplier_load[sup_id] += per_supplier

        # Calculate capacity utilization
        for sup_id, load in supplier_load.items():
            capacity = self.supplier_capacity.get(sup_id, 100)
            utilization = load / capacity if capacity > 0 else 1.0
            supplier_capacity_utilization[sup_id] = utilization

        # Simulate cascade - suppliers at >110% may fail
        if cascade_enabled:
            iterations = 0
            while iterations < 5:  # Max 5 cascade waves
                new_failures = []
                for sup_id, util in supplier_capacity_utilization.items():
                    if util > self.STRAIN_FAILURE and sup_id not in failed_suppliers:
                        # 50% chance of failure per 10% over capacity
                        failure_prob = (util - 1.0) * 5
                        if random.random() < failure_prob:
                            new_failures.append(sup_id)

                if not new_failures:
                    break

                secondary_failures.extend(new_failures)
                failed_suppliers.update(new_failures)
                cascade_depth += 1
                iterations += 1

                # Recalculate with new failures
                for sup_id in new_failures:
                    products = data.supplier_products.get(sup_id, [])
                    affected_products.update(products)

                # Redistribute load again
                supplier_load.clear()
                for product in affected_products:
                    suppliers = data.product_suppliers.get(product, [])
                    active = [s for s in suppliers if s not in failed_suppliers]
                    if active:
                        demand = self.product_daily_demand.get(product, 100)
                        per_supplier = demand / len(active)
                        for s in active:
                            supplier_load[s] += per_supplier

                for sup_id, load in supplier_load.items():
                    capacity = self.supplier_capacity.get(sup_id, 100)
                    supplier_capacity_utilization[sup_id] = load / capacity if capacity > 0 else 1.0

        # Determine affected stores and stockout risk
        affected_stores = {}
        stockout_risk = {}

        for store_id in M5_STORES:
            at_risk = [p for p in affected_products if p in self.store_products.get(store_id, set())]
            if at_risk:
                affected_stores[store_id] = at_risk
                # Stockout risk = % of at-risk products that are single-sourced
                if at_risk:
                    single_sourced_in_store = [p for p in at_risk if p in single_sourced]
                    risk = len(single_sourced_in_store) / len(at_risk)
                    # Increase risk based on duration
                    risk = min(1.0, risk * (1 + duration_days * 0.02))
                    stockout_risk[store_id] = risk

        # Generate mitigation actions
        mitigation_actions = self._generate_mitigations(
            data, list(affected_products), failed_suppliers, single_sourced, multi_sourced
        )

        # Estimate recovery time
        recovery_time = self._estimate_recovery_time(
            duration_days, len(failed_suppliers), cascade_depth
        )

        # Revenue impact estimate (simplified)
        total_demand = sum(self.product_daily_demand.get(p, 0) for p in affected_products)
        single_sourced_demand = sum(self.product_daily_demand.get(p, 0) for p in single_sourced)
        revenue_impact = (single_sourced_demand / max(1, total_demand)) * 0.5  # 50% of single-sourced at risk

        # Overloaded suppliers
        overloaded = [s for s, u in supplier_capacity_utilization.items() if u > 1.0]

        return CascadeReport(
            failed_suppliers=supplier_ids,
            disruption_duration_days=duration_days,
            affected_products=list(affected_products),
            affected_stores=affected_stores,
            stockout_risk=stockout_risk,
            single_sourced_products=single_sourced,
            multi_sourced_products=multi_sourced,
            supplier_capacity_strain=supplier_capacity_utilization,
            overloaded_suppliers=overloaded,
            recovery_time_days=recovery_time,
            mitigation_actions=mitigation_actions,
            cascade_depth=cascade_depth,
            secondary_failures=secondary_failures,
            total_products_at_risk=len(affected_products),
            total_stores_impacted=len(affected_stores),
            estimated_revenue_impact_pct=revenue_impact * 100,
        )

    def _generate_mitigations(
        self,
        data: ComplexNetworkData,
        affected_products: List[str],
        failed_suppliers: Set[str],
        single_sourced: List[str],
        multi_sourced: List[str]
    ) -> List[MitigationAction]:
        """Generate recommended mitigation actions."""
        actions = []

        # For multi-sourced products: reroute to backup suppliers
        for product in multi_sourced[:20]:  # Limit to top 20
            suppliers = data.product_suppliers.get(product, [])
            failed = [s for s in suppliers if s in failed_suppliers]
            active = [s for s in suppliers if s not in failed_suppliers]

            if failed and active:
                actions.append(MitigationAction(
                    action_type="reroute",
                    product=product,
                    from_supplier=failed[0],
                    to_supplier=active[0],
                    affected_stores=list(M5_STORES),
                    priority="high",
                    description=f"Reroute {product} from {failed[0]} to {active[0]}"
                ))

        # For single-sourced products: emergency measures
        for product in single_sourced[:20]:
            suppliers = data.product_suppliers.get(product, [])
            failed = [s for s in suppliers if s in failed_suppliers]

            actions.append(MitigationAction(
                action_type="emergency_order",
                product=product,
                from_supplier=failed[0] if failed else "UNKNOWN",
                to_supplier=None,
                affected_stores=list(M5_STORES),
                priority="critical",
                description=f"CRITICAL: {product} has no backup supplier. Consider spot market purchase or substitute."
            ))

        return actions

    def _estimate_recovery_time(
        self, disruption_days: int, num_failed: int, cascade_depth: int
    ) -> int:
        """Estimate days to full recovery after disruption ends."""
        base_recovery = disruption_days // 2  # Base: half the disruption period
        supplier_factor = num_failed * 2  # Each failed supplier adds 2 days
        cascade_factor = cascade_depth * 5  # Each cascade wave adds 5 days

        return max(1, base_recovery + supplier_factor + cascade_factor)

    def print_report(self, report: CascadeReport) -> str:
        """Print a formatted cascade report."""
        lines = []
        lines.append("=" * 70)
        lines.append("SUPPLIER DISRUPTION CASCADE REPORT")
        lines.append("=" * 70)

        # Summary
        lines.append(f"\nFailed Suppliers: {', '.join(report.failed_suppliers)}")
        lines.append(f"Disruption Duration: {report.disruption_duration_days} days")
        lines.append(f"Cascade Depth: {report.cascade_depth} waves")
        if report.secondary_failures:
            lines.append(f"Secondary Failures: {', '.join(report.secondary_failures)}")

        lines.append(f"\n--- IMPACT SUMMARY ---")
        lines.append(f"Products at Risk: {report.total_products_at_risk}")
        lines.append(f"Stores Impacted: {report.total_stores_impacted}")
        lines.append(f"Single-Sourced (STOCKOUT RISK): {len(report.single_sourced_products)}")
        lines.append(f"Multi-Sourced (can reroute): {len(report.multi_sourced_products)}")
        lines.append(f"Estimated Revenue Impact: {report.estimated_revenue_impact_pct:.1f}%")
        lines.append(f"Recovery Time: {report.recovery_time_days} days")

        # Stockout risk by store
        lines.append(f"\n--- STOCKOUT RISK BY STORE ---")
        for store_id in sorted(report.stockout_risk.keys(), key=lambda x: report.stockout_risk[x], reverse=True):
            risk = report.stockout_risk[store_id]
            bar = "█" * int(risk * 20) + "░" * (20 - int(risk * 20))
            status = "CRITICAL" if risk > 0.5 else ("WARNING" if risk > 0.2 else "OK")
            lines.append(f"  {store_id}: [{bar}] {risk:.0%} {status}")

        # Overloaded suppliers
        if report.overloaded_suppliers:
            lines.append(f"\n--- OVERLOADED SUPPLIERS (>100% capacity) ---")
            for sup_id in report.overloaded_suppliers[:10]:
                util = report.supplier_capacity_strain.get(sup_id, 0)
                lines.append(f"  {sup_id}: {util:.0%} capacity utilization")

        # Top mitigation actions
        if report.mitigation_actions:
            lines.append(f"\n--- TOP MITIGATION ACTIONS ---")
            critical = [a for a in report.mitigation_actions if a.priority == "critical"][:5]
            high = [a for a in report.mitigation_actions if a.priority == "high"][:5]

            for action in critical + high:
                icon = "🚨" if action.priority == "critical" else "⚠️"
                lines.append(f"  {icon} [{action.priority.upper()}] {action.description}")

        lines.append("\n" + "=" * 70)

        return "\n".join(lines)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Simulate supplier disruption cascades in the 1600-supplier network"
    )
    parser.add_argument(
        "--supplier",
        help="Specific supplier ID to fail (e.g., SUP_0001)"
    )
    parser.add_argument(
        "--tier",
        choices=["micro", "small", "medium", "large", "mega", "giant"],
        help="Pick a random supplier from this tier"
    )
    parser.add_argument(
        "--scenario",
        choices=["worst_case", "random_giant", "regional_outage"],
        help="Predefined scenario to run"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=14,
        help="Disruption duration in days (default: 14)"
    )
    parser.add_argument(
        "--data-dir",
        default="data/walmart_m5",
        help="Path to M5 data directory"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--no-cascade",
        action="store_true",
        help="Disable cascade simulation (only direct impact)"
    )

    args = parser.parse_args()

    # Initialize simulator
    random.seed(args.seed)
    simulator = CascadeSimulator(data_dir=args.data_dir, seed=args.seed)
    simulator.load_network()

    # Determine which suppliers fail
    supplier_ids = []

    if args.scenario == "worst_case":
        # All giant suppliers fail simultaneously
        supplier_ids = simulator.get_all_suppliers_by_tier("giant")
        print(f"WORST CASE SCENARIO: All {len(supplier_ids)} giant suppliers fail!")
        args.duration = max(args.duration, 30)

    elif args.scenario == "random_giant":
        # Random giant fails
        sup_id = simulator.get_supplier_by_tier("giant")
        if sup_id:
            supplier_ids = [sup_id]
            print(f"Random giant supplier failure: {sup_id}")

    elif args.scenario == "regional_outage":
        # All suppliers from one region fail
        data = simulator.network_data
        region = random.choice(["Northeast", "Southeast", "Midwest", "Southwest", "West"])
        supplier_ids = [s.id for s in data.suppliers if s.region == region]
        print(f"Regional outage in {region}: {len(supplier_ids)} suppliers affected")

    elif args.tier:
        # Random supplier from tier
        sup_id = simulator.get_supplier_by_tier(args.tier)
        if sup_id:
            supplier_ids = [sup_id]
            print(f"Random {args.tier} supplier failure: {sup_id}")
        else:
            print(f"No suppliers found in tier: {args.tier}")
            return

    elif args.supplier:
        # Specific supplier
        supplier_ids = [args.supplier]
        print(f"Simulating failure of: {args.supplier}")

    else:
        # Default: random giant
        sup_id = simulator.get_supplier_by_tier("giant")
        if sup_id:
            supplier_ids = [sup_id]
            print(f"Default: Random giant supplier failure: {sup_id}")

    if not supplier_ids:
        print("Error: No suppliers to simulate")
        return

    # Run simulation
    print(f"\nSimulating {args.duration}-day disruption...")
    report = simulator.simulate_disruption(
        supplier_ids=supplier_ids,
        duration_days=args.duration,
        cascade_enabled=not args.no_cascade
    )

    # Print report
    output = simulator.print_report(report)
    print(output)

    # Summary for quick reference
    print("\n📊 QUICK SUMMARY:")
    print(f"   Products at risk: {report.total_products_at_risk}")
    print(f"   Stores impacted: {report.total_stores_impacted}")
    print(f"   Single-sourced (stockout likely): {len(report.single_sourced_products)}")
    print(f"   Recovery estimate: {report.recovery_time_days} days")


if __name__ == "__main__":
    main()
