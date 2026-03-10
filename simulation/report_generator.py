# -*- coding: utf-8 -*-
"""
Actionable Report Generator.
Turns simulation results into structured recommendations.
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from .engine import SupplyChainEngine, DaySnapshot, Event, AgentDecision
from .network import SupplyChainNetwork, NodeType


class ReportGenerator:
    """
    Generates end-to-end actionable reports from simulation results.
    """

    def __init__(self, engine: SupplyChainEngine):
        self.engine = engine
        self.network = engine.network

    def generate_full_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive report with:
        1. Executive summary
        2. Risk analysis
        3. Bottleneck identification
        4. Actionable recommendations
        5. What-if scenarios
        """
        report = {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "simulation_days": len(self.engine.history),
                "network_size": {
                    "suppliers": len(self.network.get_suppliers()),
                    "warehouses": len(self.network.get_warehouses()),
                    "stores": len(self.network.get_stores()),
                    "routes": len(self.network.edges),
                },
            },
            "executive_summary": self._executive_summary(),
            "kpi_dashboard": self._kpi_dashboard(),
            "risk_analysis": self._risk_analysis(),
            "bottlenecks": self._identify_bottlenecks(),
            "agent_behavior_analysis": self._agent_analysis(),
            "recommendations": self._generate_recommendations(),
            "disruption_impact": self._disruption_impact(),
        }
        return report

    def _executive_summary(self) -> Dict[str, Any]:
        """One-paragraph executive summary."""
        summary = self.engine.get_summary_report()
        fill_rate = summary.get("avg_fill_rate", 1.0)
        stockouts = summary.get("total_stockout_events", 0)
        disruptions = summary.get("disruption_events", 0)

        if fill_rate >= 0.99:
            health = "HEALTHY"
            health_detail = "Supply chain maintained excellent performance."
        elif fill_rate >= 0.95:
            health = "AT RISK"
            health_detail = "Supply chain showed vulnerability under disruption."
        else:
            health = "CRITICAL"
            health_detail = "Supply chain experienced significant failures."

        narrative = (
            f"Over {summary['total_days']} days of simulation with {disruptions} disruption event(s), "
            f"the supply chain achieved a {fill_rate:.1%} average fill rate with {stockouts} stockout event(s). "
            f"Agents made {summary['total_decisions']} autonomous decisions including "
            f"{summary['decision_breakdown'].get('emergency_reorder', 0)} emergency reorder(s). "
            f"{health_detail}"
        )

        return {
            "health_status": health,
            "narrative": narrative,
            "fill_rate": fill_rate,
            "stockouts": stockouts,
            "disruptions": disruptions,
        }

    def _kpi_dashboard(self) -> Dict[str, Any]:
        """Key performance indicators over time."""
        daily_fill_rates = []
        daily_stockouts = []
        daily_orders = []

        cumulative_stockouts = 0
        for s in self.engine.history:
            daily_fill_rates.append({
                "day": s.day,
                "fill_rate": s.metrics["fill_rate"]
            })
            day_stockouts = sum(1 for e in s.events if e.event_type == "stockout")
            cumulative_stockouts += day_stockouts
            daily_stockouts.append({
                "day": s.day,
                "count": day_stockouts,
                "cumulative": cumulative_stockouts
            })
            day_orders = sum(1 for d in s.decisions if "reorder" in d.action)
            daily_orders.append({
                "day": s.day,
                "orders": day_orders
            })

        return {
            "fill_rate_timeline": daily_fill_rates,
            "stockout_timeline": daily_stockouts,
            "order_timeline": daily_orders,
        }

    def _risk_analysis(self) -> Dict[str, Any]:
        """Identify risk factors and single points of failure."""
        risks = []

        # Check for single-source dependencies
        for wh in self.network.get_warehouses():
            supplier_edges = [
                e for e in self.network.get_edges_to(wh.id)
                if self.network.get_node(e.source_id)
                and self.network.get_node(e.source_id).node_type == NodeType.SUPPLIER
            ]
            if len(supplier_edges) <= 1:
                risks.append({
                    "type": "single_source_dependency",
                    "severity": "HIGH",
                    "node": wh.id,
                    "detail": f"{wh.name} has only {len(supplier_edges)} supplier route(s). "
                              f"A single supplier disruption could halt supply entirely.",
                    "recommendation": "Add backup supplier route."
                })

        # Check for stores with only one warehouse
        for store in self.network.get_stores():
            wh_edges = [
                e for e in self.network.get_edges_to(store.id)
                if self.network.get_node(e.source_id)
                and self.network.get_node(e.source_id).node_type == NodeType.WAREHOUSE
            ]
            primary = [e for e in wh_edges if e.transit_days <= 2]
            if len(primary) <= 1:
                risks.append({
                    "type": "limited_warehouse_access",
                    "severity": "MEDIUM",
                    "node": store.id,
                    "detail": f"{store.name} has only {len(primary)} fast warehouse route(s). "
                              f"Cross-region backup adds {max(e.transit_days for e in wh_edges) if wh_edges else 0} day delay.",
                    "recommendation": "Consider regional inventory pre-positioning."
                })

        # Check for high transit time routes
        slow_routes = [e for e in self.network.edges if e.transit_days >= 4]
        if slow_routes:
            risks.append({
                "type": "long_lead_time",
                "severity": "MEDIUM",
                "detail": f"{len(slow_routes)} route(s) have transit time ≥4 days. "
                          f"Long lead times amplify the bullwhip effect.",
                "recommendation": "Explore regional sourcing or forward stocking."
            })

        return {
            "total_risks": len(risks),
            "high_severity": sum(1 for r in risks if r["severity"] == "HIGH"),
            "risks": risks,
        }

    def _identify_bottlenecks(self) -> List[Dict[str, Any]]:
        """Find bottleneck nodes based on simulation data."""
        bottlenecks = []

        # Nodes that had stockouts
        stockout_counts = {}
        for event in self.engine.events_log:
            if event.event_type == "stockout":
                stockout_counts[event.source_id] = stockout_counts.get(event.source_id, 0) + 1

        for node_id, count in sorted(stockout_counts.items(), key=lambda x: -x[1]):
            node = self.network.get_node(node_id)
            bottlenecks.append({
                "node_id": node_id,
                "name": node.name if node else node_id,
                "issue": "frequent_stockouts",
                "stockout_count": count,
                "recommendation": f"Increase safety stock or reorder point for {node.name if node else node_id}."
            })

        # Warehouses that ran low
        for wh in self.network.get_warehouses():
            min_inv = float('inf')
            min_day = 0
            for s in self.engine.history:
                inv = sum(s.inventories.get(wh.id, {}).values())
                if inv < min_inv:
                    min_inv = inv
                    min_day = s.day
            if min_inv < wh.capacity * 0.1:
                bottlenecks.append({
                    "node_id": wh.id,
                    "name": wh.name,
                    "issue": "critically_low_inventory",
                    "min_inventory": min_inv,
                    "min_day": min_day,
                    "recommendation": f"Increase reorder point for {wh.name}. "
                                      f"Inventory dropped to {min_inv} on Day {min_day}."
                })

        return bottlenecks

    def _agent_analysis(self) -> Dict[str, Any]:
        """Analyze agent decision patterns."""
        agent_decisions = {}
        for d in self.engine.decisions_log:
            if d.agent_id not in agent_decisions:
                agent_decisions[d.agent_id] = {"reorder": 0, "emergency_reorder": 0}
            agent_decisions[d.agent_id][d.action] = agent_decisions[d.agent_id].get(d.action, 0) + 1

        emergency_decisions = [
            d for d in self.engine.decisions_log if d.action == "emergency_reorder"
        ]

        return {
            "agents_active": len(agent_decisions),
            "decision_by_agent": agent_decisions,
            "emergency_decisions": [
                {
                    "day": d.day,
                    "agent": d.agent_id,
                    "reasoning": d.reasoning,
                    "details": d.details,
                }
                for d in emergency_decisions
            ],
            "adaptability_score": min(1.0, len(emergency_decisions) / max(1, sum(
                1 for e in self.engine.events_log if e.event_type == "disruption"
            ))),
        }

    def _disruption_impact(self) -> List[Dict[str, Any]]:
        """Analyze the cascade impact of each disruption."""
        impacts = []

        disruption_events = [e for e in self.engine.events_log if e.event_type == "disruption"]
        for disruption in disruption_events:
            # Find stockouts that happened after this disruption
            post_stockouts = [
                e for e in self.engine.events_log
                if e.event_type == "stockout" and e.day >= disruption.day
            ]

            # Find fill rate dip
            pre_fill = [s.metrics["fill_rate"] for s in self.engine.history if s.day < disruption.day]
            post_fill = [s.metrics["fill_rate"] for s in self.engine.history if s.day >= disruption.day]

            avg_pre = sum(pre_fill) / len(pre_fill) if pre_fill else 1.0
            avg_post = sum(post_fill) / len(post_fill) if post_fill else 1.0

            # Time to first stockout after disruption
            first_stockout_day = None
            for e in post_stockouts:
                if e.day >= disruption.day:
                    first_stockout_day = e.day
                    break

            propagation_delay = (first_stockout_day - disruption.day) if first_stockout_day else None

            impacts.append({
                "disruption": {
                    "day": disruption.day,
                    "node": disruption.source_id,
                    "description": disruption.description,
                },
                "cascade_effect": {
                    "stockouts_after": len(post_stockouts),
                    "fill_rate_before": round(avg_pre, 4),
                    "fill_rate_after": round(avg_post, 4),
                    "fill_rate_impact": round(avg_pre - avg_post, 4),
                    "propagation_delay_days": propagation_delay,
                },
                "insight": (
                    f"Disruption at {disruption.source_id} on Day {disruption.day} "
                    f"{'caused first stockout after {propagation_delay} days' if propagation_delay else 'had no immediate stockout impact'}. "
                    f"Fill rate dropped from {avg_pre:.1%} to {avg_post:.1%}."
                ),
            })

        return impacts

    def _generate_recommendations(self) -> List[Dict[str, Any]]:
        """Generate prioritized, actionable recommendations."""
        recs = []
        summary = self.engine.get_summary_report()
        risks = self._risk_analysis()
        bottlenecks = self._identify_bottlenecks()

        # Rec 1: Safety stock
        if summary.get("total_stockout_events", 0) > 0:
            stockout_nodes = set()
            for e in self.engine.events_log:
                if e.event_type == "stockout":
                    stockout_nodes.add(e.source_id)
            recs.append({
                "priority": "HIGH",
                "category": "Inventory",
                "action": f"Increase safety stock at {', '.join(stockout_nodes)}",
                "rationale": f"{summary['total_stockout_events']} stockout events detected. "
                            f"Current reorder points are insufficient for demand volatility.",
                "estimated_impact": "Reduce stockouts by 60-80%",
            })

        # Rec 2: Supplier diversification
        high_risks = [r for r in risks["risks"] if r["severity"] == "HIGH"]
        if high_risks:
            recs.append({
                "priority": "HIGH",
                "category": "Supplier Strategy",
                "action": "Add backup suppliers for critical routes",
                "rationale": f"{len(high_risks)} single-source dependency risks identified. "
                            f"A single supplier failure can cascade across the network.",
                "estimated_impact": "Reduce disruption vulnerability by 50%",
            })

        # Rec 3: Emergency protocols
        emergency_count = summary.get("decision_breakdown", {}).get("emergency_reorder", 0)
        if emergency_count > 0:
            recs.append({
                "priority": "MEDIUM",
                "category": "Operations",
                "action": "Formalize emergency reorder protocols",
                "rationale": f"Agents triggered {emergency_count} emergency reorder(s). "
                            f"Formalizing this into SOPs ensures consistent response.",
                "estimated_impact": "Faster recovery from disruptions",
            })

        # Rec 4: Lead time reduction
        slow_routes = [e for e in self.network.edges if e.transit_days >= 4]
        if slow_routes:
            recs.append({
                "priority": "MEDIUM",
                "category": "Logistics",
                "action": f"Reduce transit time for {len(slow_routes)} slow routes",
                "rationale": "Long lead times amplify demand uncertainty and delay disruption recovery.",
                "estimated_impact": "Improve responsiveness by 30-40%",
            })

        # Rec 5: Demand forecasting
        recs.append({
            "priority": "LOW",
            "category": "Planning",
            "action": "Implement demand forecasting model",
            "rationale": "Current reorder logic is reactive. Predictive models (world model) "
                        "can anticipate demand spikes and pre-position inventory.",
            "estimated_impact": "Reduce stockouts by additional 20-30%",
        })

        return recs

    def save_report(self, output_path: str) -> str:
        """Generate and save the full report."""
        report = self.generate_full_report()

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return output_path

    def print_report_summary(self):
        """Print a human-readable report to console."""
        report = self.generate_full_report()

        print("\n" + "=" * 70)
        print("📋 LEVYFLY SIMULATION REPORT")
        print("=" * 70)

        # Executive Summary
        es = report["executive_summary"]
        status_emoji = {"HEALTHY": "🟢", "AT RISK": "🟡", "CRITICAL": "🔴"}
        print(f"\n{status_emoji.get(es['health_status'], '⚪')} Status: {es['health_status']}")
        print(f"\n{es['narrative']}")

        # Risks
        ra = report["risk_analysis"]
        print(f"\n⚠️  RISKS ({ra['total_risks']} identified, {ra['high_severity']} HIGH)")
        for r in ra["risks"]:
            severity_color = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
            print(f"   {severity_color.get(r['severity'], '⚪')} [{r['severity']}] {r.get('detail', '')[:80]}")

        # Bottlenecks
        bns = report["bottlenecks"]
        if bns:
            print(f"\n🔍 BOTTLENECKS ({len(bns)} found)")
            for b in bns:
                print(f"   • {b['name']}: {b['issue']} — {b['recommendation']}")

        # Disruption Impact
        impacts = report["disruption_impact"]
        if impacts:
            print(f"\n💥 DISRUPTION CASCADE ANALYSIS")
            for imp in impacts:
                d = imp["disruption"]
                c = imp["cascade_effect"]
                print(f"   Day {d['day']} — {d['description']}")
                print(f"     Propagation delay: {c['propagation_delay_days'] or 'N/A'} days")
                print(f"     Fill rate impact: {c['fill_rate_before']:.1%} → {c['fill_rate_after']:.1%}")

        # Recommendations
        recs = report["recommendations"]
        print(f"\n✅ RECOMMENDATIONS ({len(recs)})")
        for i, r in enumerate(recs, 1):
            priority_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
            print(f"\n   {i}. {priority_icon.get(r['priority'], '⚪')} [{r['priority']}] {r['action']}")
            print(f"      {r['rationale']}")
            print(f"      → Expected impact: {r['estimated_impact']}")

        print("\n" + "=" * 70)
