#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
28-Day Daily Report Generator

Runs M5 validation for 28 days and generates actionable daily reports:
- Green check: prediction within 15% of actual → accurate
- Red cross: prediction off by >30% AND stockout risk → action needed
- Warning: prediction off by 15-30% → monitor

Output: docs/reports/m5_28day_report.html
"""
import os
import sys
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from validation.walmart.m5_adapter import load_m5_data, build_network_from_m5, M5Dataset, DailyDemand
from validation.walmart.demand_driven_engine import DemandDrivenEngine
from validation.walmart.scoring import evaluate_engine


@dataclass
class PredictionResult:
    """Result of comparing prediction vs actual for a product-store pair."""
    product: str
    store_id: str
    predicted_qty: int
    actual_qty: int
    error_pct: float
    status: str  # "accurate", "monitor", "action"
    recommendation: str
    supplier_id: Optional[str] = None


@dataclass
class DayReport:
    """Report for a single day."""
    day: int
    date_label: str
    accuracy_rate: float
    action_items: int
    critical_alerts: int
    monitor_items: int
    total_items: int
    fill_rate: float
    stockouts: int
    predictions: List[PredictionResult]
    events: List[str]


@dataclass
class FullReport:
    """Complete 28-day report."""
    days: List[DayReport]
    summary: Dict
    generated_at: str


class DailyReportGenerator:
    """
    Generates 28-day actionable reports from M5 validation.
    """

    def __init__(self, data_dir: str = "data/walmart_m5"):
        self.data_dir = data_dir
        self.dataset: Optional[M5Dataset] = None
        self.engine: Optional[DemandDrivenEngine] = None
        self.day_reports: List[DayReport] = []

    def run(self, days: int = 28) -> FullReport:
        """Run simulation and generate reports."""
        print(f"Loading M5 data from {self.data_dir}...")
        self.dataset = load_m5_data(self.data_dir, max_days=days + 30)

        print("Building network...")
        network = build_network_from_m5(self.dataset)

        print(f"Running {days}-day simulation...")
        self.engine = DemandDrivenEngine(network, self.dataset)

        # Track predictions vs actuals
        demand_history = defaultdict(list)  # (store, product) -> [demand, ...]
        inventory_history = defaultdict(list)  # (store, product) -> [inventory, ...]

        for day in range(1, days + 1):
            # Record pre-day inventory
            for store in network.get_stores():
                for product in self.dataset.products:
                    inv = store.inventory.get(product, 0)
                    inventory_history[(store.id, product)].append(inv)

            # Simulate day
            snapshot = self.engine._simulate_day(day)
            self.engine.history.append(snapshot)
            self.engine.metrics.days_simulated = day

            # Record actual demand
            real_demands = self.dataset.daily_demands.get(day, [])
            for demand in real_demands:
                demand_history[(demand.store_id, demand.product)].append(demand.quantity)

            # Generate day report
            day_report = self._generate_day_report(day, demand_history, inventory_history, snapshot)
            self.day_reports.append(day_report)

            if day % 7 == 0:
                print(f"  Day {day}: {day_report.accuracy_rate:.1%} accuracy, "
                      f"{day_report.action_items} actions, {day_report.critical_alerts} critical")

        # Generate full report
        return self._compile_full_report(days)

    def _generate_day_report(
        self,
        day: int,
        demand_history: Dict,
        inventory_history: Dict,
        snapshot
    ) -> DayReport:
        """Generate report for a single day."""
        predictions = []

        # Get actual demands for this day
        real_demands = self.dataset.daily_demands.get(day, [])

        for demand in real_demands:
            store_id = demand.store_id
            product = demand.product
            actual_qty = demand.quantity

            # Predict based on recent history (simple moving average)
            history_key = (store_id, product)
            history = demand_history.get(history_key, [])

            if len(history) >= 3:
                # Use last 7 days average as prediction
                recent = history[-7:] if len(history) >= 7 else history
                predicted_qty = int(sum(recent) / len(recent))
            else:
                # Not enough history, use actual as baseline
                predicted_qty = actual_qty

            # Calculate error
            if actual_qty > 0:
                error_pct = abs(predicted_qty - actual_qty) / actual_qty * 100
            else:
                error_pct = 0 if predicted_qty == 0 else 100

            # Determine status
            inv_history = inventory_history.get(history_key, [])
            current_inv = inv_history[-1] if inv_history else 0

            # Check for stockout risk
            stockout_risk = current_inv < actual_qty

            if error_pct <= 15:
                status = "accurate"
                recommendation = "No action needed"
            elif error_pct <= 30:
                status = "monitor"
                if predicted_qty > actual_qty:
                    recommendation = f"Over-predicted by {error_pct:.0f}% - monitor inventory levels"
                else:
                    recommendation = f"Under-predicted by {error_pct:.0f}% - consider safety stock adjustment"
            else:
                if stockout_risk:
                    status = "action"
                    recommendation = f"CRITICAL: {error_pct:.0f}% error + stockout risk - immediate reorder needed"
                else:
                    status = "action"
                    recommendation = f"High error ({error_pct:.0f}%) - review demand forecast model"

            # Find supplier
            supplier_id = self._find_supplier_for_product(product)

            predictions.append(PredictionResult(
                product=product,
                store_id=store_id,
                predicted_qty=predicted_qty,
                actual_qty=actual_qty,
                error_pct=error_pct,
                status=status,
                recommendation=recommendation,
                supplier_id=supplier_id,
            ))

        # Calculate day statistics
        total_items = len(predictions)
        accurate = sum(1 for p in predictions if p.status == "accurate")
        monitor = sum(1 for p in predictions if p.status == "monitor")
        action = sum(1 for p in predictions if p.status == "action")
        critical = sum(1 for p in predictions if p.status == "action" and "CRITICAL" in p.recommendation)

        accuracy_rate = accurate / max(1, total_items)

        # Get events from snapshot
        events = [e.description for e in snapshot.events if e.event_type in ["stockout", "disruption", "recovery"]]

        return DayReport(
            day=day,
            date_label=f"Day {day}",
            accuracy_rate=accuracy_rate,
            action_items=action,
            critical_alerts=critical,
            monitor_items=monitor,
            total_items=total_items,
            fill_rate=snapshot.metrics.get("fill_rate", 0),
            stockouts=sum(1 for e in snapshot.events if e.event_type == "stockout"),
            predictions=predictions,
            events=events,
        )

    def _find_supplier_for_product(self, product: str) -> str:
        """Find the supplier ID for a product based on category."""
        if product.startswith("FOODS"):
            return "S_FOODS"
        elif product.startswith("HOBBIES"):
            return "S_HOBBIES"
        elif product.startswith("HOUSEHOLD"):
            return "S_HOUSE"
        return "UNKNOWN"

    def _compile_full_report(self, days: int) -> FullReport:
        """Compile all day reports into a full report."""
        total_predictions = sum(r.total_items for r in self.day_reports)
        total_accurate = sum(
            sum(1 for p in r.predictions if p.status == "accurate")
            for r in self.day_reports
        )
        total_actions = sum(r.action_items for r in self.day_reports)
        total_critical = sum(r.critical_alerts for r in self.day_reports)

        # Get final engine evaluation
        eval_result = evaluate_engine(self.engine, days)

        summary = {
            "days_simulated": days,
            "total_predictions": total_predictions,
            "overall_accuracy": total_accurate / max(1, total_predictions),
            "total_action_items": total_actions,
            "total_critical_alerts": total_critical,
            "avg_daily_accuracy": sum(r.accuracy_rate for r in self.day_reports) / len(self.day_reports),
            "final_fill_rate": eval_result["fill_rate"],
            "total_stockouts": eval_result["stockouts"],
            "total_stockout_units": eval_result["stockout_units"],
            "composite_score": eval_result["score"],
        }

        return FullReport(
            days=self.day_reports,
            summary=summary,
            generated_at=datetime.now().isoformat(),
        )

    def generate_html(self, report: FullReport, output_path: str) -> None:
        """Generate HTML report with day-by-day navigation."""
        html = self._render_html(report)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)

        print(f"Report saved to: {output_path}")

    def _render_html(self, report: FullReport) -> str:
        """Render full HTML report."""
        # Day tabs HTML
        day_tabs = []
        for day_report in report.days:
            status_class = "good" if day_report.accuracy_rate > 0.85 else ("warn" if day_report.accuracy_rate > 0.70 else "bad")
            day_tabs.append(f'''
                <button class="day-tab {status_class}" onclick="showDay({day_report.day})">
                    Day {day_report.day}
                </button>
            ''')

        # Day content HTML
        day_contents = []
        for day_report in report.days:
            day_html = self._render_day_html(day_report)
            day_contents.append(f'''
                <div id="day-{day_report.day}" class="day-content" style="display: none;">
                    {day_html}
                </div>
            ''')

        # Summary metrics
        summary = report.summary

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>M5 28-Day Validation Report</title>
    <style>
        :root {{
            --bg-dark: #1a1a2e;
            --bg-card: #16213e;
            --text-primary: #eee;
            --text-secondary: #aaa;
            --green: #00b894;
            --yellow: #fdcb6e;
            --red: #e74c3c;
            --blue: #0984e3;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            line-height: 1.6;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}

        header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 1px solid #333;
        }}

        header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
        }}

        header p {{
            color: var(--text-secondary);
        }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}

        .metric-card {{
            background: var(--bg-card);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }}

        .metric-card h3 {{
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-bottom: 10px;
        }}

        .metric-card .value {{
            font-size: 2rem;
            font-weight: bold;
        }}

        .metric-card .value.good {{ color: var(--green); }}
        .metric-card .value.warn {{ color: var(--yellow); }}
        .metric-card .value.bad {{ color: var(--red); }}

        .day-nav {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin: 20px 0;
            padding: 10px;
            background: var(--bg-card);
            border-radius: 10px;
        }}

        .day-tab {{
            padding: 8px 15px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.2s;
        }}

        .day-tab.good {{ background: var(--green); color: white; }}
        .day-tab.warn {{ background: var(--yellow); color: black; }}
        .day-tab.bad {{ background: var(--red); color: white; }}

        .day-tab:hover {{
            transform: scale(1.05);
            opacity: 0.9;
        }}

        .day-tab.active {{
            outline: 3px solid white;
        }}

        .day-content {{
            background: var(--bg-card);
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
        }}

        .day-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #333;
        }}

        .day-header h2 {{
            font-size: 1.5rem;
        }}

        .day-stats {{
            display: flex;
            gap: 20px;
        }}

        .day-stat {{
            text-align: center;
        }}

        .day-stat .label {{
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}

        .day-stat .value {{
            font-size: 1.3rem;
            font-weight: bold;
        }}

        .predictions-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}

        .predictions-table th,
        .predictions-table td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #333;
        }}

        .predictions-table th {{
            background: rgba(0,0,0,0.2);
            color: var(--text-secondary);
            font-size: 0.85rem;
            text-transform: uppercase;
        }}

        .predictions-table tr:hover {{
            background: rgba(255,255,255,0.05);
        }}

        .status-badge {{
            padding: 4px 10px;
            border-radius: 15px;
            font-size: 0.8rem;
            font-weight: bold;
        }}

        .status-badge.accurate {{
            background: var(--green);
            color: white;
        }}

        .status-badge.monitor {{
            background: var(--yellow);
            color: black;
        }}

        .status-badge.action {{
            background: var(--red);
            color: white;
        }}

        .events-list {{
            margin-top: 20px;
            padding: 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
        }}

        .events-list h4 {{
            margin-bottom: 10px;
            color: var(--text-secondary);
        }}

        .event-item {{
            padding: 8px 0;
            border-bottom: 1px solid #333;
            font-size: 0.9rem;
        }}

        .legend {{
            display: flex;
            gap: 20px;
            margin: 20px 0;
            padding: 15px;
            background: var(--bg-card);
            border-radius: 10px;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .legend-icon {{
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
        }}

        .legend-icon.green {{ background: var(--green); }}
        .legend-icon.yellow {{ background: var(--yellow); color: black; }}
        .legend-icon.red {{ background: var(--red); }}

        footer {{
            text-align: center;
            padding: 30px 0;
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}

        @media (max-width: 768px) {{
            .summary-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
            .day-stats {{
                flex-wrap: wrap;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>M5 28-Day Validation Report</h1>
            <p>Generated: {report.generated_at}</p>
        </header>

        <section class="summary">
            <h2>Summary</h2>
            <div class="summary-grid">
                <div class="metric-card">
                    <h3>Overall Accuracy</h3>
                    <div class="value {'good' if summary['overall_accuracy'] > 0.85 else ('warn' if summary['overall_accuracy'] > 0.70 else 'bad')}">
                        {summary['overall_accuracy']:.1%}
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Fill Rate</h3>
                    <div class="value {'good' if summary['final_fill_rate'] > 0.95 else ('warn' if summary['final_fill_rate'] > 0.85 else 'bad')}">
                        {summary['final_fill_rate']:.1%}
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Total Stockouts</h3>
                    <div class="value {'good' if summary['total_stockouts'] < 50 else ('warn' if summary['total_stockouts'] < 200 else 'bad')}">
                        {summary['total_stockouts']:,}
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Stockout Units</h3>
                    <div class="value {'good' if summary['total_stockout_units'] < 500 else ('warn' if summary['total_stockout_units'] < 2000 else 'bad')}">
                        {summary['total_stockout_units']:,}
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Action Items</h3>
                    <div class="value warn">
                        {summary['total_action_items']:,}
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Critical Alerts</h3>
                    <div class="value bad">
                        {summary['total_critical_alerts']:,}
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Composite Score</h3>
                    <div class="value {'good' if summary['composite_score'] > 80 else ('warn' if summary['composite_score'] > 60 else 'bad')}">
                        {summary['composite_score']:.1f}
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Days Simulated</h3>
                    <div class="value">{summary['days_simulated']}</div>
                </div>
            </div>
        </section>

        <section class="legend">
            <div class="legend-item">
                <div class="legend-icon green">&#10003;</div>
                <span>Accurate (≤15% error)</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon yellow">&#9888;</div>
                <span>Monitor (15-30% error)</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon red">&#10007;</div>
                <span>Action Needed (>30% error)</span>
            </div>
        </section>

        <section class="daily-reports">
            <h2>Daily Reports</h2>
            <div class="day-nav">
                {''.join(day_tabs)}
            </div>

            {''.join(day_contents)}
        </section>

        <footer>
            <p>LevyFly Supply Chain Simulation - M5 Validation Report</p>
        </footer>
    </div>

    <script>
        function showDay(day) {{
            // Hide all day contents
            document.querySelectorAll('.day-content').forEach(el => {{
                el.style.display = 'none';
            }});

            // Remove active class from all tabs
            document.querySelectorAll('.day-tab').forEach(el => {{
                el.classList.remove('active');
            }});

            // Show selected day
            document.getElementById('day-' + day).style.display = 'block';

            // Mark tab as active
            document.querySelectorAll('.day-tab')[day - 1].classList.add('active');
        }}

        // Show day 1 by default
        showDay(1);
    </script>
</body>
</html>
'''
        return html

    def _render_day_html(self, day_report: DayReport) -> str:
        """Render HTML for a single day."""
        # Filter to show only action and monitor items, plus a sample of accurate
        action_items = [p for p in day_report.predictions if p.status == "action"]
        monitor_items = [p for p in day_report.predictions if p.status == "monitor"]
        accurate_items = [p for p in day_report.predictions if p.status == "accurate"][:10]

        # Build table rows
        rows = []
        for p in action_items + monitor_items + accurate_items:
            status_class = p.status
            status_icon = "&#10007;" if p.status == "action" else ("&#9888;" if p.status == "monitor" else "&#10003;")

            rows.append(f'''
                <tr>
                    <td><span class="status-badge {status_class}">{status_icon}</span></td>
                    <td>{p.store_id}</td>
                    <td>{p.product}</td>
                    <td>{p.predicted_qty}</td>
                    <td>{p.actual_qty}</td>
                    <td>{p.error_pct:.1f}%</td>
                    <td>{p.supplier_id}</td>
                    <td>{p.recommendation}</td>
                </tr>
            ''')

        # Events
        events_html = ""
        if day_report.events:
            event_items = "".join(f'<div class="event-item">{e}</div>' for e in day_report.events[:10])
            events_html = f'''
                <div class="events-list">
                    <h4>Day Events</h4>
                    {event_items}
                </div>
            '''

        return f'''
            <div class="day-header">
                <h2>{day_report.date_label}</h2>
                <div class="day-stats">
                    <div class="day-stat">
                        <div class="label">Accuracy</div>
                        <div class="value" style="color: {'var(--green)' if day_report.accuracy_rate > 0.85 else ('var(--yellow)' if day_report.accuracy_rate > 0.70 else 'var(--red)')}">
                            {day_report.accuracy_rate:.1%}
                        </div>
                    </div>
                    <div class="day-stat">
                        <div class="label">Fill Rate</div>
                        <div class="value">{day_report.fill_rate:.1%}</div>
                    </div>
                    <div class="day-stat">
                        <div class="label">Stockouts</div>
                        <div class="value" style="color: var(--red)">{day_report.stockouts}</div>
                    </div>
                    <div class="day-stat">
                        <div class="label">Actions</div>
                        <div class="value" style="color: var(--red)">{day_report.action_items}</div>
                    </div>
                    <div class="day-stat">
                        <div class="label">Monitor</div>
                        <div class="value" style="color: var(--yellow)">{day_report.monitor_items}</div>
                    </div>
                    <div class="day-stat">
                        <div class="label">Total Items</div>
                        <div class="value">{day_report.total_items}</div>
                    </div>
                </div>
            </div>

            <table class="predictions-table">
                <thead>
                    <tr>
                        <th>Status</th>
                        <th>Store</th>
                        <th>Product</th>
                        <th>Predicted</th>
                        <th>Actual</th>
                        <th>Error %</th>
                        <th>Supplier</th>
                        <th>Recommendation</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>

            {events_html}

            <p style="color: var(--text-secondary); margin-top: 15px; font-size: 0.9rem;">
                Showing {len(action_items)} action items, {len(monitor_items)} monitor items,
                and {len(accurate_items)} sample accurate predictions.
            </p>
        '''


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate 28-day M5 validation report")
    parser.add_argument("--data-dir", default="data/walmart_m5", help="Path to M5 data")
    parser.add_argument("--output", default="docs/reports/m5_28day_report.html", help="Output HTML path")
    parser.add_argument("--days", type=int, default=28, help="Number of days to simulate")

    args = parser.parse_args()

    print("=" * 60)
    print("M5 28-Day Validation Report Generator")
    print("=" * 60)

    generator = DailyReportGenerator(args.data_dir)
    report = generator.run(days=args.days)

    print("\n" + "=" * 60)
    print("Report Summary")
    print("=" * 60)
    for key, value in report.summary.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    print("\n" + "=" * 60)
    print("Generating HTML Report")
    print("=" * 60)
    generator.generate_html(report, args.output)

    print("\nReport generation complete!")


if __name__ == "__main__":
    main()
