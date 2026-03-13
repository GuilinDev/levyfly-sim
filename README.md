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
| 🚨 URGENT | Order immediately | < 3 days of stock |
| 📦 RESTOCK | Place order today | < 7 days of stock |
| 📉 REDUCE | Cut next order | > 21 days (overstocked) |
| ✅ OK | No action needed | 7–21 days coverage |

**28-day overview** (real M5 data, 10 stores × 7 products):

| Day | 🚨 Urgent | 📦 Restock | 📉 Reduce | ✅ OK | What's happening |
|-----|-----------|------------|-----------|-------|------------------|
| 1 | 0 | 0 | 48 | 22 | Overstocked everywhere — cut orders |
| 7 | 0 | 0 | 46 | 24 | Still burning through excess inventory |
| 10 | 0 | 4 | 41 | 25 | First restocks needed — stock running low |
| 14 | **1** | 11 | 30 | 28 | 🚨 CA_3 FOODS_2 down to 2.2 days! |
| 18 | **3** | 13 | 24 | 30 | Multiple stores need emergency orders |
| 21 | 1 | 11 | 18 | 40 | System stabilizing after restocks arrive |
| 25 | 3 | 11 | 15 | 41 | New urgencies: TX_2 running low |
| 28 | **2** | 12 | 14 | 42 | TX_2 HOBBIES_1 + TX_3 HOBBIES_2 critical |

**Example: Day 14 action list** — the morning a store manager opens this:

```
📋 DAY 14 — 1 urgent, 11 restock, 30 reduce

📍 CA_3 (California Store #3):
  🚨 FOODS_2     — ORDER 3,586 units NOW     (inv: 1,683 | demand: ~752/day | 2.2 days left)
  📦 FOODS_3     — Restock 10,160 units       (inv: 8,087 | demand: ~2,606/day | 3.1 days left)
  📦 HOUSEHOLD_2 — Restock 912 units          (inv: 994   | demand: ~272/day  | 3.7 days left)
  📦 FOODS_1     — Restock 447 units          (inv: 1,789 | demand: ~319/day  | 5.6 days left)
  📦 HOBBIES_1   — Restock 410 units          (inv: 2,409 | demand: ~402/day  | 6.0 days left)

📍 TX_2 (Texas Store #2):
  📦 HOBBIES_2   — Restock 91 units           (inv: 106   | demand: ~28/day   | 3.8 days left)

📍 WI_3 (Wisconsin Store #3):
  📦 FOODS_2     — Restock 1,936 units        (inv: 2,551 | demand: ~641/day  | 4.0 days left)
  📦 FOODS_3     — Restock 6,316 units        (inv: 10,273| demand: ~2,369/day| 4.3 days left)
```

**Example: Day 21** — different stores, different products:

```
📋 DAY 21 — 1 urgent, 11 restock, 18 reduce

📍 CA_3:
  🚨 HOUSEHOLD_1 — ORDER 2,037 units NOW      (inv: 1,325 | demand: ~480/day | 2.8 days left)

📍 WI_1 (Wisconsin Store #1):
  📦 HOBBIES_1   — Restock 1,232 units        (inv: 1,148 | demand: ~340/day | 3.4 days left)
  📦 FOODS_1     — Restock 543 units          (inv: 1,126 | demand: ~238/day | 4.7 days left)

📍 TX_2:
  📦 FOODS_3     — Restock 4,473 units        (inv: 6,441 | demand: ~1,559/day| 4.1 days left)
  📦 FOODS_2     — Restock 955 units          (inv: 2,563 | demand: ~502/day  | 5.1 days left)
```

**28-day totals**: 32 urgent alerts, 203 restock orders, 867 reduce recommendations. Peak urgency: Day 16 (4 items across CA_1, CA_2, CA_3, WI_3).

30,000 products are too many to review manually — the [anomaly detector](#anomaly-detection) surfaces only items that deviate from expected patterns.

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
