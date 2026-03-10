#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate M5-structure sample data for pipeline development.
Matches the real M5 schema exactly so real data is a drop-in replacement.

M5 Structure:
  - sales_train.csv: item_id, dept_id, cat_id, store_id, state_id, d_1...d_1941
  - calendar.csv: date, wm_yr_wk, weekday, wday, month, year, d, event_name_1, event_type_1, snap_CA/TX/WI
  - sell_prices.csv: store_id, item_id, wm_yr_wk, sell_price

We generate a small representative subset:
  - 3 stores (CA_1, TX_1, WI_1) from 3 states
  - 3 departments (FOODS_1, FOODS_2, HOUSEHOLD_1)
  - 50 items total
  - 365 days (d_1 to d_365)
"""
import csv
import os
import random
import math
from datetime import datetime, timedelta

random.seed(42)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

STORES = ["CA_1", "TX_1", "WI_1"]
STATES = {"CA_1": "CA", "TX_1": "TX", "WI_1": "WI"}
DEPTS = ["FOODS_1", "FOODS_2", "HOUSEHOLD_1"]
CATS = {"FOODS_1": "FOODS", "FOODS_2": "FOODS", "HOUSEHOLD_1": "HOUSEHOLD"}

ITEMS_PER_DEPT = 5
DAYS = 365
START_DATE = datetime(2020, 1, 1)

# Events that affect demand
EVENTS = {
    50: ("SuperBowl", "Sporting", 1.8),
    75: ("ValentinesDay", "Cultural", 1.3),
    130: ("MemorialDay", "National", 1.5),
    185: ("IndependenceDay", "National", 1.6),
    250: ("LaborDay", "National", 1.4),
    305: ("Thanksgiving", "National", 2.0),
    320: ("Christmas", "Cultural", 2.2),
    # COVID disruption simulation
    70: ("COVID_Start", "Pandemic", 2.5),   # Panic buying
}

# Supply disruption periods (simulated)
DISRUPTIONS = [
    (75, 95, "COVID supply chain shock"),     # 20-day disruption
    (200, 210, "Hurricane season impact"),    # 10-day disruption
]


def is_disrupted(day):
    for start, end, _ in DISRUPTIONS:
        if start <= day <= end:
            return True
    return False


def generate_base_demand(dept, day):
    """Generate realistic base demand with seasonality."""
    # Base by department
    base = {"FOODS_1": 8, "FOODS_2": 5, "HOUSEHOLD_1": 3}[dept]

    # Weekly seasonality (weekends higher for food)
    weekday = day % 7
    if dept.startswith("FOODS"):
        weekly_factor = 1.3 if weekday in [5, 6] else 1.0
    else:
        weekly_factor = 1.1 if weekday == 6 else 1.0

    # Monthly seasonality
    month = ((day - 1) // 30) % 12
    monthly_factor = 1.0 + 0.1 * math.sin(2 * math.pi * month / 12)

    # Event boost
    event_factor = 1.0
    for event_day, (_, _, boost) in EVENTS.items():
        if abs(day - event_day) <= 2:
            event_factor = max(event_factor, boost)

    demand = base * weekly_factor * monthly_factor * event_factor
    demand = max(0, int(random.gauss(demand, demand * 0.3)))
    return demand


def generate_sales_train():
    """Generate sales_train.csv matching M5 format."""
    filepath = os.path.join(OUT_DIR, "sales_train.csv")
    header = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
    header += [f"d_{d}" for d in range(1, DAYS + 1)]

    rows = []
    for store in STORES:
        state = STATES[store]
        for dept in DEPTS:
            cat = CATS[dept]
            for item_num in range(1, ITEMS_PER_DEPT + 1):
                item_id = f"{dept}_{item_num:03d}"
                row_id = f"{item_id}_{store}_validation"

                row = [row_id, item_id, dept, cat, store, state]
                for d in range(1, DAYS + 1):
                    sales = generate_base_demand(dept, d)
                    # During disruption, some items see supply issues (reduced availability)
                    if is_disrupted(d) and random.random() < 0.3:
                        sales = max(0, sales - random.randint(2, 5))
                    row.append(sales)
                rows.append(row)

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"  ✅ sales_train.csv: {len(rows)} items × {DAYS} days")
    return filepath


def generate_calendar():
    """Generate calendar.csv matching M5 format."""
    filepath = os.path.join(OUT_DIR, "calendar.csv")
    header = ["date", "wm_yr_wk", "weekday", "wday", "month", "year",
              "d", "event_name_1", "event_type_1", "event_name_2", "event_type_2",
              "snap_CA", "snap_TX", "snap_WI"]

    rows = []
    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    for d in range(1, DAYS + 1):
        date = START_DATE + timedelta(days=d - 1)
        wday = date.weekday()
        wm_yr_wk = date.isocalendar()[0] * 100 + date.isocalendar()[1]

        event_name_1 = ""
        event_type_1 = ""
        if d in EVENTS:
            event_name_1 = EVENTS[d][0]
            event_type_1 = EVENTS[d][1]

        # SNAP (food stamps) — roughly every month
        snap_ca = 1 if date.day <= 10 else 0
        snap_tx = 1 if 5 <= date.day <= 15 else 0
        snap_wi = 1 if 1 <= date.day <= 5 else 0

        rows.append([
            date.strftime("%Y-%m-%d"), wm_yr_wk, weekday_names[wday],
            wday + 1, date.month, date.year,
            f"d_{d}", event_name_1, event_type_1, "", "",
            snap_ca, snap_tx, snap_wi
        ])

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"  ✅ calendar.csv: {len(rows)} days")
    return filepath


def generate_sell_prices():
    """Generate sell_prices.csv matching M5 format."""
    filepath = os.path.join(OUT_DIR, "sell_prices.csv")
    header = ["store_id", "item_id", "wm_yr_wk", "sell_price"]

    rows = []
    weeks = set()
    for d in range(1, DAYS + 1):
        date = START_DATE + timedelta(days=d - 1)
        wk = date.isocalendar()[0] * 100 + date.isocalendar()[1]
        weeks.add(wk)

    for store in STORES:
        for dept in DEPTS:
            for item_num in range(1, ITEMS_PER_DEPT + 1):
                item_id = f"{dept}_{item_num:03d}"
                base_price = {"FOODS_1": 3.5, "FOODS_2": 5.0, "HOUSEHOLD_1": 8.0}[dept]
                base_price += random.uniform(-1, 2)

                for wk in sorted(weeks):
                    # Occasional promotions
                    price = base_price
                    if random.random() < 0.1:
                        price *= 0.75  # 25% off
                    rows.append([store, item_id, wk, round(price, 2)])

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"  ✅ sell_prices.csv: {len(rows)} price records")
    return filepath


if __name__ == "__main__":
    print("📦 Generating M5-structure sample data...")
    print(f"   Stores: {STORES}")
    print(f"   Departments: {DEPTS}")
    print(f"   Items per dept: {ITEMS_PER_DEPT}")
    print(f"   Days: {DAYS} ({START_DATE.strftime('%Y-%m-%d')} to {(START_DATE + timedelta(days=DAYS-1)).strftime('%Y-%m-%d')})")
    print()

    generate_sales_train()
    generate_calendar()
    generate_sell_prices()

    print(f"\n✅ Sample data generated in {OUT_DIR}")
    print(f"   Replace with real M5 data from Kaggle for production validation.")
