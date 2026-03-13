# ⚡ LevyFly

**AI supply chain optimization you can set up in a day — not six months.**

> Enterprise SCM costs $500K+ and takes a year to deploy. LevyFly gives you AI-powered inventory management with `pip install` and your CSV data.

![LevyFly Network](docs/assets/network_hero_v4.gif)

## The Problem

Mid-size companies are stuck between two bad options: (1) static reorder rules that overstock by 7× to avoid stockouts, or (2) $500K+ enterprise systems (SAP, Oracle SCM) that take 12-18 months to deploy.

## What LevyFly Does

LevyFly runs a team of AI agents on your supply chain data. Each supplier, warehouse, and store is an autonomous agent that forecasts demand, adapts to disruptions, and discovers optimal strategies **automatically**.

| Metric | Standard (s,S) Policy | LevyFly AI |
|---|---|---|
| Fill Rate | 99.85% | **99.95%** |
| Excess Inventory | 736% (untuned) | **65%** |
| Disruption Response | Breaks | Reroutes autonomously |
| Setup Time | Months of consulting | **One command** |
| Cost | $200K+ | **Open source** |

> Validated on **Walmart M5** real demand data (2.26M units, 30,490 SKUs, 10 stores). Compared against standard (s,S) policy — large enterprises with dedicated teams achieve better baselines. LevyFly's value is bringing AI-level optimization to teams without supply chain PhDs.

## Quick Start

```bash
git clone https://github.com/GuilinDev/levyfly-sim.git
cd levyfly-sim && pip install Pillow
python run_demo.py --data ./data/ --days 60
```

## What Makes It Different

### 1,600 Suppliers. Power Law. Real Complexity.

LevyFly models production-scale networks. 8 giant suppliers control 8% of all products — if one goes down, the cascade hits every store.

<img src="docs/assets/network_viz_b.png" width="600" alt="Power Law Distribution"/>

*Chord diagram: supplier tiers (left) → stores (right). Band width = supply volume. The power law is visible — few giants carry disproportionate flow.*

### AI Discovers Strategies Humans Don't

Three levels of intelligence, each building on the last:

| Level | What It Does | Result |
|-------|-------------|--------|
| **Parameter Search** | Grid search over 240 combinations | Score: 82.61 |
| **Demand Forecasting** | Fine-tuned Chronos-2 on your data | 67% fewer stockouts |
| **Code Evolution** | LLM rewrites strategy algorithms | Score: **84.50** (+2.3%) |

Code Evolution is the key: an LLM reads strategy objectives, proposes algorithmic changes, tests against real data, and commits improvements. It discovered "order rounding" — a strategy not in the original search space.

### 28-Day Daily Action List

What should each store do **today**? Not charts — an operations checklist.

```bash
python validation/walmart/action_list.py --days 28
```

| Symbol | Meaning | Trigger |
|--------|---------|---------|
| 🚨 | URGENT — order now | < 3 days of stock left |
| 📦 | RESTOCK — place order | < 7 days of stock left |
| 📉 | REDUCE — cut next order | > 21 days of stock (overstocked) |
| ✅ | OK — no action | 7–21 days of coverage |

**Real output from M5 data** (selected days):

```
📋 DAY 14
  🚨 Urgent: 1 | 📦 Restock: 11 | 📉 Reduce: 30 | ✅ OK: 28

  📍 CA_3:
    🚨 FOODS_2 — ORDER 3,586 units NOW
       Inventory: 1,683 | Daily demand: ~752 | Coverage: 2.2 days
    📦 FOODS_3 — Restock 10,160 units
       Inventory: 8,087 | Daily demand: ~2,606 | Coverage: 3.1 days
    📦 HOUSEHOLD_2 — Restock 912 units
       Inventory: 994 | Daily demand: ~272 | Coverage: 3.7 days

📋 DAY 28
  🚨 Urgent: 2 | 📦 Restock: 12 | 📉 Reduce: 14 | ✅ OK: 42

  📍 TX_2:
    🚨 HOBBIES_1 — ORDER 1,171 units NOW
       Inventory: 752 | Daily demand: ~274 | Coverage: 2.7 days
  📍 TX_3:
    🚨 HOBBIES_2 — ORDER 95 units NOW
       Inventory: 45 | Daily demand: ~20 | Coverage: 2.2 days
```

28-day summary: 32 urgent alerts, 203 restock orders, peak urgency on Day 16 (4 items). Each action shows the specific product, current inventory, forecast demand, and exact quantity to order.

Full reports also available as interactive HTML: [docs/reports/m5_28day_report.html](docs/reports/m5_28day_report.html)

### Survives Chaos

5 disruption scenarios tested. LevyFly wins every one:

- **Single supplier outage**: LevyFly *improves* (+1.8%) by proactively buffering
- **Extended disruption (30 days)**: Industry standard collapses (-101%). LevyFly holds at -46%.

### Cascade Simulator

What happens when the biggest supplier fails? The cascade simulator maps the domino effect across 1,600 suppliers.

```bash
python -m simulation.cascade_simulator --scenario worst_case
# → 8 giant suppliers fail → 244 products at risk → 10 stores impacted
# → 3 secondary failures from capacity overload → 18-day recovery estimate
```

### Anomaly Detection

Can't manually review 30K products daily. The anomaly detector surfaces only items that deviate from expected patterns.

```bash
python -m simulation.anomaly_detector --days 28 --top 50
# → 847 anomalies detected → 23 CRITICAL (>3 std deviation)
# → Top: CA_1/FOODS_3 day 12: +4.2 std spike, demand doubled
```

### 3 Industries, Zero Code Changes

Same engine. Different CSV configs.

```bash
python run_all_domains.py  # Retail 99.9% | Healthcare 98.0% | Finance 100.0%
```

## Architecture

```
Your CSV Data → Multi-Agent Engine → AI Layer → Reports + GIF + JSON
                    │                    │
                    ├─ Supplier agents    ├─ Chronos-2 (demand forecast)
                    ├─ Warehouse agents   ├─ AutoTuning (policy search)
                    └─ Store agents       └─ LLM reasoning (anomalies)
```

## Roadmap

- [x] Real data validation (Walmart M5, 2.26M units)
- [x] 5-policy comparison framework
- [x] AutoTuning + Code Evolution (AI writes strategy code)
- [x] Fine-tuned Chronos-2 demand forecasting
- [x] LLM-powered agent reasoning (auditable decisions)
- [x] 1,600-supplier complex network (power law)
- [x] 28-day daily actionable reports
- [x] Disruption stress testing (5 scenarios)
- [x] Cascade simulator (supplier failure propagation)
- [x] Anomaly detector (noise filtering from 30K products)
- [ ] Interactive web dashboard
- [ ] Monte Carlo counterfactual analysis
- [ ] Agent explainability audit trail

**13/16 complete.** [Full technical details →](docs/README_full.md)

## Team

Built at the intersection of **multi-agent systems**, **supply chain optimization**, and **AI-driven decision support**.

## License

MIT
