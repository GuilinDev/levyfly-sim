#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complex Network Visualizations

Creates 4 visualizations for the ~1600 supplier network:
A) Force-directed graph with clustering
B) Chord diagram (suppliers ↔ stores)
C) Hierarchical ring/radial layout
D) Heatmap matrix (suppliers × stores)

All outputs saved to docs/assets/network_viz_{a,b,c,d}.png
"""
import os
import sys
import math
import random
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.complex_network import (
    build_complex_network, ComplexNetworkData, SupplierMetadata,
    get_supplier_stats, get_top_suppliers, SUPPLIER_TIERS
)


# Color schemes
CATEGORY_COLORS = {
    "FOODS": "#2ecc71",      # Green
    "HOBBIES": "#3498db",    # Blue
    "HOUSEHOLD": "#e67e22",  # Orange
    "UNKNOWN": "#95a5a6",    # Gray
}

TIER_COLORS = {
    "giant": "#9b59b6",     # Purple
    "mega": "#e74c3c",      # Red
    "large": "#f39c12",     # Orange
    "medium": "#3498db",    # Blue
    "small": "#2ecc71",     # Green
    "micro": "#95a5a6",     # Gray
}

STORE_COLORS = {
    "CA": "#3498db",
    "TX": "#e74c3c",
    "WI": "#2ecc71",
}


def viz_force_directed(data: ComplexNetworkData, output_path: str) -> None:
    """
    A) Force-directed graph with clustering.

    - Large circles = mega suppliers (300+ products)
    - Medium circles = mid-tier
    - Small dots = small suppliers
    - Line thickness = number of products supplied
    - Color by category (FOODS=green, HOBBIES=blue, HOUSEHOLD=orange)
    """
    print("Generating force-directed graph visualization...")

    fig, ax = plt.subplots(1, 1, figsize=(16, 16), dpi=100)
    ax.set_aspect('equal')
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.5, 1.5)
    ax.set_facecolor('#1a1a2e')
    ax.axis('off')

    # Group suppliers by tier for layered layout
    tier_groups = defaultdict(list)
    for sup in data.suppliers:
        tier_groups[sup.tier].append(sup)

    # Calculate positions using a force-directed-like layout
    # (simplified: concentric circles by tier)
    positions = {}
    tier_radii = {"giant": 0.2, "mega": 0.35, "large": 0.5, "medium": 0.7, "small": 0.9, "micro": 1.1}

    random.seed(42)
    for tier, radius in tier_radii.items():
        sups = tier_groups[tier]
        n = len(sups)
        for i, sup in enumerate(sups):
            angle = (2 * math.pi * i) / max(1, n) + random.uniform(-0.1, 0.1)
            r = radius + random.uniform(-0.05, 0.05)
            x = r * math.cos(angle)
            y = r * math.sin(angle)
            positions[sup.id] = (x, y)

    # Store positions at center
    store_positions = {}
    n_stores = len(data.stores)
    for i, store_id in enumerate(data.stores):
        angle = 2 * math.pi * i / n_stores
        x = 0.08 * math.cos(angle)
        y = 0.08 * math.sin(angle)
        store_positions[store_id] = (x, y)

    # Draw edges (sample for visibility - draw edges from top suppliers to stores)
    top_suppliers = get_top_suppliers(data, 100)
    edge_lines = []
    edge_colors = []

    for sup in top_suppliers:
        sx, sy = positions[sup.id]
        for store_id in data.stores:
            tx, ty = store_positions[store_id]
            # Number of products this supplier supplies
            n_products = sup.product_count
            alpha = min(0.5, 0.1 + n_products / 500)
            edge_lines.append([(sx, sy), (tx, ty)])
            edge_colors.append((0.5, 0.5, 0.5, alpha * 0.3))

    if edge_lines:
        lc = LineCollection(edge_lines, colors=edge_colors, linewidths=0.3)
        ax.add_collection(lc)

    # Draw suppliers
    for sup in data.suppliers:
        x, y = positions[sup.id]
        color = CATEGORY_COLORS.get(sup.category, "#95a5a6")

        # Size based on tier
        size_map = {"giant": 300, "mega": 150, "large": 80, "medium": 40, "small": 15, "micro": 5}
        size = size_map.get(sup.tier, 10)

        ax.scatter(x, y, s=size, c=color, alpha=0.8, edgecolors='white', linewidths=0.3, zorder=3)

    # Draw stores at center
    for store_id, (x, y) in store_positions.items():
        state = store_id.split("_")[0]
        color = STORE_COLORS.get(state, "#ffffff")
        ax.scatter(x, y, s=200, c=color, marker='s', edgecolors='white', linewidths=2, zorder=5)
        ax.text(x, y - 0.03, store_id, ha='center', va='top', fontsize=6, color='white', zorder=6)

    # Label top 10 suppliers
    for sup in get_top_suppliers(data, 10):
        x, y = positions[sup.id]
        ax.annotate(
            f"{sup.name.split()[0]}\n{sup.product_count}p",
            (x, y), textcoords="offset points", xytext=(0, 8),
            ha='center', fontsize=6, color='white',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.7)
        )

    # Legend
    legend_elements = [
        mpatches.Patch(color=CATEGORY_COLORS["FOODS"], label='FOODS'),
        mpatches.Patch(color=CATEGORY_COLORS["HOBBIES"], label='HOBBIES'),
        mpatches.Patch(color=CATEGORY_COLORS["HOUSEHOLD"], label='HOUSEHOLD'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fancybox=True, fontsize=10)

    # Title
    stats = get_supplier_stats(data)
    ax.set_title(
        f"Force-Directed Supply Chain Network\n"
        f"{stats['total_suppliers']} Suppliers → {stats['total_stores']} Stores | {stats['total_products']} Products",
        fontsize=14, color='white', pad=20
    )

    # Size legend
    for i, (tier, size) in enumerate([("Giant (300+)", 300), ("Mega (100-300)", 150),
                                        ("Large (40-100)", 80), ("Medium (16-40)", 40),
                                        ("Small (6-15)", 15), ("Micro (1-5)", 5)]):
        ax.scatter(-1.3, 1.2 - i * 0.1, s=size, c='white', alpha=0.7)
        ax.text(-1.2, 1.2 - i * 0.1, tier, fontsize=8, color='white', va='center')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor='#1a1a2e', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"  Saved: {output_path}")


def viz_chord_diagram(data: ComplexNetworkData, output_path: str) -> None:
    """
    B) Chord diagram.

    - Suppliers grouped by size tier on left arc
    - Stores on right arc
    - Chord width = supply volume (products × suppliers in tier)
    """
    print("Generating chord diagram visualization...")

    fig, ax = plt.subplots(1, 1, figsize=(14, 14), dpi=100)
    ax.set_aspect('equal')
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.5, 1.5)
    ax.set_facecolor('#1a1a2e')
    ax.axis('off')

    # Group suppliers by tier
    tier_groups = defaultdict(list)
    for sup in data.suppliers:
        tier_groups[sup.tier].append(sup)

    # Calculate arc segments
    # Left arc (top-left to bottom-left): suppliers by tier
    # Right arc (top-right to bottom-right): stores

    tier_order = ["giant", "mega", "large", "medium", "small", "micro"]
    total_suppliers = len(data.suppliers)

    # Left arc: from 120° to 240° (bottom-left quadrant)
    left_start = math.radians(120)
    left_end = math.radians(240)
    left_range = left_end - left_start

    # Right arc: from -60° to 60° (right side)
    right_start = math.radians(-60)
    right_end = math.radians(60)
    right_range = right_end - right_start

    radius = 1.0

    # Calculate tier arcs on left
    tier_arcs = {}
    current_angle = left_start
    for tier in tier_order:
        n = len(tier_groups[tier])
        arc_size = left_range * (n / total_suppliers)
        tier_arcs[tier] = (current_angle, current_angle + arc_size)
        current_angle += arc_size

    # Calculate store arcs on right
    store_arcs = {}
    n_stores = len(data.stores)
    arc_per_store = right_range / n_stores
    current_angle = right_start
    for store_id in data.stores:
        store_arcs[store_id] = (current_angle, current_angle + arc_per_store)
        current_angle += arc_per_store

    # Draw tier arcs on left
    for tier in tier_order:
        start, end = tier_arcs[tier]
        color = TIER_COLORS.get(tier, "#95a5a6")

        # Draw arc
        arc_angles = np.linspace(start, end, 50)
        arc_x = radius * np.cos(arc_angles)
        arc_y = radius * np.sin(arc_angles)

        # Draw as thick line
        ax.plot(arc_x, arc_y, color=color, linewidth=20, solid_capstyle='butt', alpha=0.9)

        # Label
        mid_angle = (start + end) / 2
        label_x = 1.2 * math.cos(mid_angle)
        label_y = 1.2 * math.sin(mid_angle)
        n = len(tier_groups[tier])
        ax.text(label_x, label_y, f"{tier.capitalize()}\n({n})",
                ha='center', va='center', fontsize=9, color='white',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.7))

    # Draw store arcs on right
    for store_id in data.stores:
        start, end = store_arcs[store_id]
        state = store_id.split("_")[0]
        color = STORE_COLORS.get(state, "#ffffff")

        # Draw arc
        arc_angles = np.linspace(start, end, 50)
        arc_x = radius * np.cos(arc_angles)
        arc_y = radius * np.sin(arc_angles)

        ax.plot(arc_x, arc_y, color=color, linewidth=20, solid_capstyle='butt', alpha=0.9)

        # Label
        mid_angle = (start + end) / 2
        label_x = 1.15 * math.cos(mid_angle)
        label_y = 1.15 * math.sin(mid_angle)
        ax.text(label_x, label_y, store_id, ha='center', va='center', fontsize=8, color='white')

    # Draw chords between tiers and stores
    # Thickness based on tier size and store connection probability
    for tier in tier_order:
        n_suppliers = len(tier_groups[tier])
        tier_start, tier_end = tier_arcs[tier]
        tier_mid = (tier_start + tier_end) / 2

        for store_id in data.stores:
            store_start, store_end = store_arcs[store_id]
            store_mid = (store_start + store_end) / 2

            # Chord control points
            p0 = (radius * 0.95 * math.cos(tier_mid), radius * 0.95 * math.sin(tier_mid))
            p3 = (radius * 0.95 * math.cos(store_mid), radius * 0.95 * math.sin(store_mid))
            p1 = (0.3 * p0[0], 0.3 * p0[1])
            p2 = (0.3 * p3[0], 0.3 * p3[1])

            # Bezier curve
            t = np.linspace(0, 1, 50)
            bezier_x = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
            bezier_y = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]

            # Width based on tier size
            width = 0.5 + (n_suppliers / total_suppliers) * 5
            alpha = 0.2 + (n_suppliers / total_suppliers) * 0.5

            ax.plot(bezier_x, bezier_y, color=TIER_COLORS.get(tier, "#95a5a6"),
                   linewidth=width, alpha=alpha)

    # Title
    stats = get_supplier_stats(data)
    ax.set_title(
        f"Supply Chain Chord Diagram\n"
        f"Supplier Tiers ← → Store Regions | {stats['total_products']} Products",
        fontsize=14, color='white', pad=20
    )

    # Legend for stores
    for i, (state, color) in enumerate(STORE_COLORS.items()):
        ax.scatter(1.3, 1.2 - i * 0.1, s=100, c=color, marker='s')
        ax.text(1.35, 1.2 - i * 0.1, f"{state} Stores", fontsize=9, color='white', va='center')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor='#1a1a2e', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"  Saved: {output_path}")


def viz_hierarchical_ring(data: ComplexNetworkData, output_path: str) -> None:
    """
    C) Hierarchical ring/radial layout.

    - Center = stores
    - Middle ring = DCs (if present)
    - Outer ring = suppliers
    - Size = number of products
    - Line width = supply volume
    - Top 20 suppliers labeled
    """
    print("Generating hierarchical ring visualization...")

    fig, ax = plt.subplots(1, 1, figsize=(16, 16), dpi=100)
    ax.set_aspect('equal')
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.5, 1.5)
    ax.set_facecolor('#1a1a2e')
    ax.axis('off')

    # Define rings
    store_radius = 0.15
    dc_radius = 0.4
    supplier_radius_inner = 0.7
    supplier_radius_outer = 1.2

    # Draw rings
    for r in [store_radius, dc_radius, supplier_radius_inner]:
        circle = plt.Circle((0, 0), r, fill=False, color='#333333', linewidth=1, linestyle='--')
        ax.add_patch(circle)

    # Store positions (center ring)
    store_positions = {}
    n_stores = len(data.stores)
    for i, store_id in enumerate(data.stores):
        angle = 2 * math.pi * i / n_stores - math.pi / 2
        x = store_radius * math.cos(angle)
        y = store_radius * math.sin(angle)
        store_positions[store_id] = (x, y)

        state = store_id.split("_")[0]
        color = STORE_COLORS.get(state, "#ffffff")
        ax.scatter(x, y, s=300, c=color, marker='o', edgecolors='white', linewidths=2, zorder=5)
        ax.text(x, y, store_id.replace("_", "\n"), ha='center', va='center', fontsize=6, color='white', zorder=6)

    # DC positions (middle ring)
    dcs = [n for n in data.network.nodes.values() if 'DC' in n.id]
    dc_positions = {}
    if dcs:
        n_dcs = len(dcs)
        for i, dc in enumerate(dcs):
            angle = 2 * math.pi * i / n_dcs - math.pi / 2
            x = dc_radius * math.cos(angle)
            y = dc_radius * math.sin(angle)
            dc_positions[dc.id] = (x, y)

            ax.scatter(x, y, s=400, c='#9b59b6', marker='s', edgecolors='white', linewidths=2, zorder=4)
            ax.text(x, y - 0.05, dc.name.replace(" ", "\n"), ha='center', va='top', fontsize=7, color='white', zorder=6)

    # Supplier positions (outer rings, sorted by tier)
    tier_order = ["giant", "mega", "large", "medium", "small", "micro"]
    tier_radii = {
        "giant": supplier_radius_inner,
        "mega": supplier_radius_inner + 0.08,
        "large": supplier_radius_inner + 0.16,
        "medium": supplier_radius_inner + 0.24,
        "small": supplier_radius_inner + 0.35,
        "micro": supplier_radius_outer,
    }

    tier_groups = defaultdict(list)
    for sup in data.suppliers:
        tier_groups[sup.tier].append(sup)

    supplier_positions = {}
    random.seed(42)

    for tier in tier_order:
        sups = tier_groups[tier]
        n = len(sups)
        radius = tier_radii[tier]

        for i, sup in enumerate(sups):
            angle = 2 * math.pi * i / max(1, n) + random.uniform(-0.02, 0.02)
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            supplier_positions[sup.id] = (x, y)

    # Draw connections (sample for visibility)
    top_sups = get_top_suppliers(data, 50)

    # Suppliers → DCs
    for sup in top_sups:
        sx, sy = supplier_positions[sup.id]
        for dc_id, (dx, dy) in dc_positions.items():
            alpha = min(0.5, sup.product_count / 300)
            ax.plot([sx, dx], [sy, dy], color='#555555', linewidth=0.5, alpha=alpha * 0.5, zorder=1)

    # DCs → Stores
    for dc_id, (dx, dy) in dc_positions.items():
        for store_id, (sx, sy) in store_positions.items():
            ax.plot([dx, sx], [dy, sy], color='#7f8c8d', linewidth=1.5, alpha=0.4, zorder=2)

    # Draw suppliers
    for sup in data.suppliers:
        x, y = supplier_positions[sup.id]
        color = CATEGORY_COLORS.get(sup.category, "#95a5a6")

        # Size based on product count
        size = 5 + (sup.product_count / 10)
        size = min(size, 100)

        ax.scatter(x, y, s=size, c=color, alpha=0.8, edgecolors='none', zorder=3)

    # Label top 20 suppliers
    for sup in get_top_suppliers(data, 20):
        x, y = supplier_positions[sup.id]
        # Offset label outward
        angle = math.atan2(y, x)
        label_x = x + 0.08 * math.cos(angle)
        label_y = y + 0.08 * math.sin(angle)

        ax.annotate(
            f"{sup.product_count}",
            (x, y), textcoords="offset points",
            xytext=(5 * math.cos(angle), 5 * math.sin(angle)),
            ha='center', va='center', fontsize=6, color='white',
            bbox=dict(boxstyle='round,pad=0.1', facecolor=TIER_COLORS.get(sup.tier, '#333'), alpha=0.8)
        )

    # Legend
    ax.text(-1.35, 1.3, "Supplier Tiers:", fontsize=10, color='white', fontweight='bold')
    for i, (tier, color) in enumerate(TIER_COLORS.items()):
        ax.scatter(-1.3, 1.2 - i * 0.08, s=50, c=color)
        ax.text(-1.22, 1.2 - i * 0.08, tier.capitalize(), fontsize=8, color='white', va='center')

    ax.text(-1.35, 0.7, "Categories:", fontsize=10, color='white', fontweight='bold')
    for i, (cat, color) in enumerate(CATEGORY_COLORS.items()):
        if cat != "UNKNOWN":
            ax.scatter(-1.3, 0.6 - i * 0.08, s=50, c=color)
            ax.text(-1.22, 0.6 - i * 0.08, cat, fontsize=8, color='white', va='center')

    # Ring labels
    ax.text(0, -store_radius - 0.05, "Stores", ha='center', fontsize=9, color='#aaaaaa')
    ax.text(0, -dc_radius - 0.05, "Distribution Centers", ha='center', fontsize=9, color='#aaaaaa')
    ax.text(0, -supplier_radius_outer - 0.05, "Suppliers (1,600)", ha='center', fontsize=9, color='#aaaaaa')

    # Title
    stats = get_supplier_stats(data)
    ax.set_title(
        f"Hierarchical Ring Layout\n"
        f"Stores (center) ← DCs ← {stats['total_suppliers']} Suppliers (outer)",
        fontsize=14, color='white', pad=20
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor='#1a1a2e', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"  Saved: {output_path}")


def viz_heatmap_matrix(data: ComplexNetworkData, output_path: str) -> None:
    """
    D) Heatmap matrix.

    - Rows = top 50 suppliers (sorted by size)
    - Columns = 10 stores
    - Cell color = number of products supplied to that store
    - Supplier tier labels on left
    """
    print("Generating heatmap matrix visualization...")

    # Get top 50 suppliers
    top_sups = get_top_suppliers(data, 50)
    n_suppliers = len(top_sups)
    n_stores = len(data.stores)

    # Build matrix: how many products does each supplier supply to each store region?
    # Since we don't have direct supplier→store mapping, we use regional affinity

    matrix = np.zeros((n_suppliers, n_stores))

    # Region-store mapping
    store_regions = {
        "CA_1": "West", "CA_2": "West", "CA_3": "West", "CA_4": "West",
        "TX_1": "Southwest", "TX_2": "Southwest", "TX_3": "Southwest",
        "WI_1": "Midwest", "WI_2": "Midwest", "WI_3": "Midwest",
    }

    region_affinity = {
        "West": {"West": 1.0, "Southwest": 0.6, "Midwest": 0.3, "Northeast": 0.2, "Southeast": 0.3, "International": 0.5},
        "Southwest": {"West": 0.6, "Southwest": 1.0, "Midwest": 0.5, "Northeast": 0.3, "Southeast": 0.7, "International": 0.4},
        "Midwest": {"West": 0.4, "Southwest": 0.5, "Midwest": 1.0, "Northeast": 0.8, "Southeast": 0.6, "International": 0.4},
        "Northeast": {"West": 0.3, "Southwest": 0.3, "Midwest": 0.7, "Northeast": 1.0, "Southeast": 0.8, "International": 0.6},
        "Southeast": {"West": 0.3, "Southwest": 0.6, "Midwest": 0.5, "Northeast": 0.7, "Southeast": 1.0, "International": 0.5},
        "International": {"West": 0.5, "Southwest": 0.5, "Midwest": 0.5, "Northeast": 0.5, "Southeast": 0.5, "International": 1.0},
    }

    for i, sup in enumerate(top_sups):
        for j, store_id in enumerate(data.stores):
            store_region = store_regions.get(store_id, "Midwest")
            affinity = region_affinity.get(sup.region, {}).get(store_region, 0.3)
            # Products supplied = product_count × affinity
            matrix[i, j] = sup.product_count * affinity

    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=(14, 18), dpi=100)

    # Custom colormap
    colors = ['#1a1a2e', '#2d3436', '#0984e3', '#00cec9', '#00b894', '#55efc4']
    cmap = LinearSegmentedColormap.from_list('supply', colors, N=256)

    # Plot heatmap
    im = ax.imshow(matrix, aspect='auto', cmap=cmap)

    # Labels
    ax.set_xticks(range(n_stores))
    ax.set_xticklabels(data.stores, fontsize=10, rotation=45, ha='right')

    supplier_labels = []
    for sup in top_sups:
        label = f"{sup.tier[0].upper()} | {sup.product_count:3d}p | {sup.category[:4]}"
        supplier_labels.append(label)

    ax.set_yticks(range(n_suppliers))
    ax.set_yticklabels(supplier_labels, fontsize=8, family='monospace')

    # Add tier color bar on left
    for i, sup in enumerate(top_sups):
        color = TIER_COLORS.get(sup.tier, "#95a5a6")
        rect = plt.Rectangle((-1.5, i - 0.5), 0.4, 1, color=color, clip_on=False)
        ax.add_patch(rect)

    # Category color bar on right
    for i, sup in enumerate(top_sups):
        color = CATEGORY_COLORS.get(sup.category, "#95a5a6")
        rect = plt.Rectangle((n_stores + 0.1, i - 0.5), 0.4, 1, color=color, clip_on=False)
        ax.add_patch(rect)

    # Add text annotations for high values
    for i in range(n_suppliers):
        for j in range(n_stores):
            value = matrix[i, j]
            if value > 100:
                ax.text(j, i, f'{int(value)}', ha='center', va='center',
                       fontsize=6, color='white' if value > 200 else 'black')

    # Colorbar
    cbar = plt.colorbar(im, ax=ax, shrink=0.6)
    cbar.set_label('Supply Volume (products × affinity)', fontsize=10)

    # Grid
    ax.set_xticks(np.arange(-.5, n_stores, 1), minor=True)
    ax.set_yticks(np.arange(-.5, n_suppliers, 1), minor=True)
    ax.grid(which='minor', color='#333333', linestyle='-', linewidth=0.5)

    # Title
    ax.set_title(
        f"Supplier-Store Supply Matrix\n"
        f"Top 50 Suppliers × 10 Stores | Cell = Products × Regional Affinity",
        fontsize=14, pad=20
    )

    ax.set_xlabel("Stores", fontsize=12)
    ax.set_ylabel("Suppliers (Tier | Products | Category)", fontsize=12)

    # Legend for tiers
    ax.text(-2.5, -2, "Tiers:", fontsize=9, fontweight='bold')
    for i, (tier, color) in enumerate(list(TIER_COLORS.items())[:6]):
        ax.add_patch(plt.Rectangle((-2.5 + i * 1.5, -3.5), 1.2, 0.8, color=color, clip_on=False))
        ax.text(-2.5 + i * 1.5 + 0.6, -3.1, tier[0].upper(), ha='center', fontsize=8, color='white')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor='white', edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"  Saved: {output_path}")


def generate_all_visualizations(data_dir: str, output_dir: str, seed: int = 42) -> None:
    """Generate all 4 visualizations."""
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("Building Complex Network for Visualization")
    print("=" * 60)

    data = build_complex_network(data_dir, target_suppliers=1600, seed=seed)

    print("\n" + "=" * 60)
    print("Generating Visualizations")
    print("=" * 60)

    viz_force_directed(data, os.path.join(output_dir, "network_viz_a.png"))
    viz_chord_diagram(data, os.path.join(output_dir, "network_viz_b.png"))
    viz_hierarchical_ring(data, os.path.join(output_dir, "network_viz_c.png"))
    viz_heatmap_matrix(data, os.path.join(output_dir, "network_viz_d.png"))

    print("\n" + "=" * 60)
    print("All visualizations generated successfully!")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate complex network visualizations")
    parser.add_argument("--data-dir", default="data/walmart_m5", help="Path to M5 data")
    parser.add_argument("--output-dir", default="docs/assets", help="Output directory for PNGs")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")

    args = parser.parse_args()
    generate_all_visualizations(args.data_dir, args.output_dir, args.seed)
