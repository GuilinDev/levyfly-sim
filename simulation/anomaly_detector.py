#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anomaly/Noise Detection Module

Detects demand anomalies from M5 historical data and predictions.
Surfaces items that deviate from expected patterns - filtering 30K products
down to actionable alerts.

Usage:
    python -m simulation.anomaly_detector --data data/walmart_m5/ --days 28 --top 50
"""
import os
import sys
import csv
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AnomalyType(Enum):
    SPIKE = "SPIKE"              # Sudden demand increase >3 std
    DROP = "DROP"                # Sudden demand decrease >3 std
    TREND_BREAK = "TREND_BREAK"  # Direction change after consistent trend
    SEASONAL_SHIFT = "SEASONAL_SHIFT"  # Pattern deviates from expected seasonal


class Severity(Enum):
    INFO = "INFO"          # Single day outside 95% CI
    WARNING = "WARNING"    # 2 consecutive days outside CI
    CRITICAL = "CRITICAL"  # 3+ days outside CI OR >3 std spike/drop


@dataclass
class Anomaly:
    """Detected anomaly for a product-store combination."""
    product_id: str
    store_id: str
    day: int
    actual: int
    predicted: int
    ci_lower: float
    ci_upper: float
    anomaly_type: AnomalyType
    severity: Severity
    deviation_std: float  # How many std deviations from mean
    suggested_action: str


@dataclass
class ProductStoreStats:
    """Rolling statistics for a product-store combination."""
    product_id: str
    store_id: str
    demand_history: List[int] = field(default_factory=list)
    rolling_mean: float = 0.0
    rolling_std: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    trend: str = "stable"  # "increasing", "decreasing", "stable"
    consecutive_outside_ci: int = 0


@dataclass
class AnomalySummary:
    """Summary statistics for anomaly detection run."""
    total_anomalies: int
    by_type: Dict[str, int]
    by_severity: Dict[str, int]
    by_store: Dict[str, int]
    by_day: Dict[int, int]
    top_anomalies: List[Anomaly]


class AnomalyDetector:
    """
    Detects demand anomalies from historical M5 data.

    Maintains rolling statistics per product-store and flags:
    - Demands outside 95% confidence interval
    - Consecutive anomalous days (change points)
    - Extreme spikes/drops (>3 std)
    """

    WINDOW_SIZE = 14  # Rolling window for mean/std
    CI_FACTOR = 1.96  # 95% confidence interval
    SPIKE_THRESHOLD = 3.0  # Std deviations for SPIKE/DROP
    TREND_WINDOW = 7  # Days to detect trend direction

    def __init__(self, data_dir: str = "data/walmart_m5"):
        self.data_dir = data_dir
        self.stats: Dict[Tuple[str, str], ProductStoreStats] = {}
        self.anomalies: List[Anomaly] = []
        self.stores: List[str] = []
        self.products: List[str] = []

    def load_demand_data(self, max_days: int = 365) -> Dict[int, List[Tuple[str, str, int]]]:
        """
        Load M5 demand data.

        Returns:
            Dict mapping day -> list of (store_id, product_id, quantity)
        """
        sales_path = os.path.join(self.data_dir, "sales_train_validation.csv")
        if not os.path.exists(sales_path):
            sales_path = os.path.join(self.data_dir, "sales_train.csv")

        if not os.path.exists(sales_path):
            raise FileNotFoundError(f"Sales data not found at {sales_path}")

        print(f"Loading demand data from {sales_path}...")

        daily_demands = defaultdict(list)
        stores_set = set()
        products_set = set()

        with open(sales_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        print(f"  Processing {len(rows)} item-store rows...")

        # Find day columns (d_1, d_2, ...)
        sample_row = rows[0] if rows else {}
        day_cols = [c for c in sample_row.keys() if c.startswith("d_")]
        day_cols = sorted(day_cols, key=lambda x: int(x.split("_")[1]))[:max_days]

        for row in rows:
            store_id = row.get("store_id", "")
            item_id = row.get("item_id", "")
            dept_id = row.get("dept_id", "")  # Use dept_id as product aggregation

            if not store_id or not dept_id:
                continue

            stores_set.add(store_id)
            products_set.add(dept_id)

            for day_col in day_cols:
                day = int(day_col.split("_")[1])
                try:
                    qty = int(row.get(day_col, 0) or 0)
                except ValueError:
                    qty = 0

                if qty > 0:
                    daily_demands[day].append((store_id, dept_id, qty))

        self.stores = sorted(stores_set)
        self.products = sorted(products_set)

        print(f"  Loaded {len(self.stores)} stores, {len(self.products)} products, {len(daily_demands)} days")

        return dict(daily_demands)

    def detect_anomalies(self, max_days: int = 28, top_n: int = 50) -> AnomalySummary:
        """
        Run anomaly detection on M5 demand data.

        Args:
            max_days: Number of days to analyze
            top_n: Return top N most significant anomalies

        Returns:
            AnomalySummary with detected anomalies and statistics
        """
        # Load data with enough history for rolling stats
        history_days = max_days + self.WINDOW_SIZE + 10
        daily_demands = self.load_demand_data(max_days=history_days)

        if not daily_demands:
            print("No demand data found!")
            return AnomalySummary(
                total_anomalies=0,
                by_type={},
                by_severity={},
                by_store={},
                by_day={},
                top_anomalies=[]
            )

        # Aggregate demands by (store, product, day)
        aggregated = defaultdict(lambda: defaultdict(int))
        for day, demands in daily_demands.items():
            for store_id, product_id, qty in demands:
                aggregated[(store_id, product_id)][day] += qty

        print(f"Analyzing {len(aggregated)} store-product combinations...")

        # Process each day in order
        all_days = sorted(daily_demands.keys())
        analysis_start = self.WINDOW_SIZE + 1  # Start after we have enough history

        for day in all_days:
            if day < analysis_start:
                # Build up history
                for (store_id, product_id), day_demands in aggregated.items():
                    qty = day_demands.get(day, 0)
                    self._update_stats(store_id, product_id, qty, build_history=True)
            elif day <= max_days + self.WINDOW_SIZE:
                # Detect anomalies
                for (store_id, product_id), day_demands in aggregated.items():
                    qty = day_demands.get(day, 0)
                    anomaly = self._check_anomaly(store_id, product_id, day, qty)
                    if anomaly:
                        self.anomalies.append(anomaly)
                    self._update_stats(store_id, product_id, qty, build_history=False)

        # Compile summary
        summary = self._compile_summary(top_n)

        return summary

    def _get_or_create_stats(self, store_id: str, product_id: str) -> ProductStoreStats:
        """Get or create stats for a store-product pair."""
        key = (store_id, product_id)
        if key not in self.stats:
            self.stats[key] = ProductStoreStats(
                product_id=product_id,
                store_id=store_id
            )
        return self.stats[key]

    def _update_stats(self, store_id: str, product_id: str, qty: int, build_history: bool = False):
        """Update rolling statistics for a store-product pair."""
        stats = self._get_or_create_stats(store_id, product_id)
        stats.demand_history.append(qty)

        # Keep only window size
        if len(stats.demand_history) > self.WINDOW_SIZE:
            stats.demand_history = stats.demand_history[-self.WINDOW_SIZE:]

        if len(stats.demand_history) >= 3:
            # Calculate rolling mean and std
            n = len(stats.demand_history)
            mean = sum(stats.demand_history) / n
            variance = sum((x - mean) ** 2 for x in stats.demand_history) / n
            std = math.sqrt(variance) if variance > 0 else 1.0

            stats.rolling_mean = mean
            stats.rolling_std = max(std, 1.0)  # Avoid division by zero
            stats.ci_lower = mean - self.CI_FACTOR * std
            stats.ci_upper = mean + self.CI_FACTOR * std

            # Detect trend using last TREND_WINDOW days
            if len(stats.demand_history) >= self.TREND_WINDOW:
                recent = stats.demand_history[-self.TREND_WINDOW:]
                diffs = [recent[i+1] - recent[i] for i in range(len(recent)-1)]
                avg_diff = sum(diffs) / len(diffs) if diffs else 0

                if avg_diff > std * 0.2:
                    stats.trend = "increasing"
                elif avg_diff < -std * 0.2:
                    stats.trend = "decreasing"
                else:
                    stats.trend = "stable"

    def _check_anomaly(self, store_id: str, product_id: str, day: int, qty: int) -> Optional[Anomaly]:
        """Check if current demand is anomalous."""
        stats = self._get_or_create_stats(store_id, product_id)

        if stats.rolling_std == 0 or len(stats.demand_history) < 3:
            return None

        # Calculate deviation
        deviation = (qty - stats.rolling_mean) / stats.rolling_std
        predicted = int(stats.rolling_mean)

        # Check if outside 95% CI
        outside_ci = qty < stats.ci_lower or qty > stats.ci_upper

        if outside_ci:
            stats.consecutive_outside_ci += 1
        else:
            stats.consecutive_outside_ci = 0
            return None  # Not anomalous

        # Determine anomaly type and severity
        anomaly_type = None
        severity = Severity.INFO
        action = ""

        if abs(deviation) > self.SPIKE_THRESHOLD:
            # Extreme spike or drop
            if deviation > 0:
                anomaly_type = AnomalyType.SPIKE
                action = f"Demand spike ({deviation:.1f} std) - verify inventory, check for promotion/event"
            else:
                anomaly_type = AnomalyType.DROP
                action = f"Demand drop ({abs(deviation):.1f} std) - check for supply issues or competitor activity"
            severity = Severity.CRITICAL

        elif stats.consecutive_outside_ci >= 3:
            # Change point - 3+ consecutive days
            anomaly_type = AnomalyType.TREND_BREAK
            severity = Severity.CRITICAL
            if qty > stats.rolling_mean:
                action = "Sustained demand increase - update forecast model upward"
            else:
                action = "Sustained demand decrease - investigate root cause"

        elif stats.consecutive_outside_ci == 2:
            # 2 consecutive days
            severity = Severity.WARNING
            if qty > stats.rolling_mean:
                anomaly_type = AnomalyType.SPIKE
                action = "Consecutive high demand - monitor for trend change"
            else:
                anomaly_type = AnomalyType.DROP
                action = "Consecutive low demand - monitor for trend change"

        else:
            # Single day outside CI
            severity = Severity.INFO
            if qty > stats.rolling_mean:
                anomaly_type = AnomalyType.SPIKE
                action = "Single-day spike - likely noise, continue monitoring"
            else:
                anomaly_type = AnomalyType.DROP
                action = "Single-day drop - likely noise, continue monitoring"

        return Anomaly(
            product_id=product_id,
            store_id=store_id,
            day=day,
            actual=qty,
            predicted=predicted,
            ci_lower=stats.ci_lower,
            ci_upper=stats.ci_upper,
            anomaly_type=anomaly_type,
            severity=severity,
            deviation_std=deviation,
            suggested_action=action
        )

    def _compile_summary(self, top_n: int) -> AnomalySummary:
        """Compile anomaly summary statistics."""
        by_type = defaultdict(int)
        by_severity = defaultdict(int)
        by_store = defaultdict(int)
        by_day = defaultdict(int)

        for anomaly in self.anomalies:
            by_type[anomaly.anomaly_type.value] += 1
            by_severity[anomaly.severity.value] += 1
            by_store[anomaly.store_id] += 1
            by_day[anomaly.day] += 1

        # Sort by severity (CRITICAL > WARNING > INFO) then by deviation
        severity_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
        sorted_anomalies = sorted(
            self.anomalies,
            key=lambda a: (severity_order[a.severity], -abs(a.deviation_std))
        )

        return AnomalySummary(
            total_anomalies=len(self.anomalies),
            by_type=dict(by_type),
            by_severity=dict(by_severity),
            by_store=dict(by_store),
            by_day=dict(by_day),
            top_anomalies=sorted_anomalies[:top_n]
        )

    def print_summary(self, summary: AnomalySummary) -> str:
        """Print formatted anomaly summary."""
        lines = []
        lines.append("=" * 70)
        lines.append("ANOMALY DETECTION REPORT")
        lines.append("=" * 70)

        lines.append(f"\nTotal Anomalies Detected: {summary.total_anomalies}")

        # By severity
        lines.append("\n--- BY SEVERITY ---")
        for sev in ["CRITICAL", "WARNING", "INFO"]:
            count = summary.by_severity.get(sev, 0)
            icon = "🚨" if sev == "CRITICAL" else ("⚠️" if sev == "WARNING" else "ℹ️")
            lines.append(f"  {icon} {sev}: {count}")

        # By type
        lines.append("\n--- BY TYPE ---")
        for atype, count in sorted(summary.by_type.items(), key=lambda x: -x[1]):
            lines.append(f"  {atype}: {count}")

        # By store (top 5)
        lines.append("\n--- TOP STORES WITH ANOMALIES ---")
        store_sorted = sorted(summary.by_store.items(), key=lambda x: -x[1])[:5]
        for store_id, count in store_sorted:
            lines.append(f"  {store_id}: {count} anomalies")

        # Top anomalies
        lines.append("\n--- TOP ANOMALIES (need attention) ---")
        critical = [a for a in summary.top_anomalies if a.severity == Severity.CRITICAL][:10]
        warning = [a for a in summary.top_anomalies if a.severity == Severity.WARNING][:10]

        for anomaly in critical[:5] + warning[:5]:
            icon = "🚨" if anomaly.severity == Severity.CRITICAL else "⚠️"
            lines.append(f"\n  {icon} [{anomaly.severity.value}] Day {anomaly.day} | {anomaly.store_id} | {anomaly.product_id}")
            lines.append(f"     Actual: {anomaly.actual} | Predicted: {anomaly.predicted} | Deviation: {anomaly.deviation_std:+.1f} std")
            lines.append(f"     Type: {anomaly.anomaly_type.value}")
            lines.append(f"     Action: {anomaly.suggested_action}")

        lines.append("\n" + "=" * 70)

        return "\n".join(lines)

    def get_anomalies_for_report(self, max_anomalies: int = 20) -> List[Dict]:
        """Get anomalies formatted for daily report integration."""
        result = []
        for anomaly in self.anomalies[:max_anomalies]:
            result.append({
                "day": anomaly.day,
                "store_id": anomaly.store_id,
                "product_id": anomaly.product_id,
                "actual": anomaly.actual,
                "predicted": anomaly.predicted,
                "ci_lower": round(anomaly.ci_lower, 1),
                "ci_upper": round(anomaly.ci_upper, 1),
                "type": anomaly.anomaly_type.value,
                "severity": anomaly.severity.value,
                "deviation": round(anomaly.deviation_std, 2),
                "action": anomaly.suggested_action
            })
        return result


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect demand anomalies from M5 data"
    )
    parser.add_argument(
        "--data",
        default="data/walmart_m5",
        help="Path to M5 data directory"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=28,
        help="Number of days to analyze (default: 28)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="Number of top anomalies to show (default: 50)"
    )
    parser.add_argument(
        "--severity",
        choices=["INFO", "WARNING", "CRITICAL"],
        help="Filter by minimum severity level"
    )
    parser.add_argument(
        "--store",
        help="Filter by specific store ID"
    )
    parser.add_argument(
        "--product",
        help="Filter by specific product ID"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("ANOMALY DETECTOR - M5 Demand Analysis")
    print("=" * 60)

    detector = AnomalyDetector(data_dir=args.data)
    summary = detector.detect_anomalies(max_days=args.days, top_n=args.top)

    # Apply filters if specified
    if args.severity or args.store or args.product:
        filtered = summary.top_anomalies
        if args.severity:
            sev_map = {"INFO": Severity.INFO, "WARNING": Severity.WARNING, "CRITICAL": Severity.CRITICAL}
            min_sev = sev_map[args.severity]
            sev_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
            filtered = [a for a in filtered if sev_order[a.severity] <= sev_order[min_sev]]
        if args.store:
            filtered = [a for a in filtered if a.store_id == args.store]
        if args.product:
            filtered = [a for a in filtered if a.product_id == args.product]
        summary.top_anomalies = filtered

    output = detector.print_summary(summary)
    print(output)

    # Quick stats
    print("\n📊 QUICK SUMMARY:")
    print(f"   Total anomalies: {summary.total_anomalies}")
    print(f"   Critical: {summary.by_severity.get('CRITICAL', 0)}")
    print(f"   Warning: {summary.by_severity.get('WARNING', 0)}")
    print(f"   Info: {summary.by_severity.get('INFO', 0)}")

    if summary.top_anomalies:
        top = summary.top_anomalies[0]
        print(f"\n   Top anomaly: {top.store_id}/{top.product_id} on day {top.day}")
        print(f"   → {top.deviation_std:+.1f} std deviation ({top.anomaly_type.value})")


if __name__ == "__main__":
    main()
