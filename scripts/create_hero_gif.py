#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create an animated GIF that tells the LevyFly story in ~8 seconds.
24fps, ~200 frames. Uses PIL/Pillow only (ARM64 compatible).
"""
import sys
import os
import math
import random
from PIL import Image, ImageDraw, ImageFont

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.complex_network import build_complex_network, SUPPLIER_TIERS

# Configuration
CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 800
FPS = 20  # Reduced from 24 for smaller file size
TOTAL_FRAMES = 160  # Reduced from 200 for smaller file size (~8 sec at 20fps)

# Colors (Dark theme matching GitHub dark mode)
BG_COLOR = (13, 17, 23)  # #0d1117
TEXT_COLOR = (201, 209, 217)  # #c9d1d9
ACCENT_COLOR = (88, 166, 255)  # #58a6ff
GREEN_COLOR = (63, 185, 80)  # #3fb950
RED_COLOR = (248, 81, 73)  # #f85149
YELLOW_COLOR = (210, 153, 34)  # #d29922
ORANGE_COLOR = (219, 109, 40)  # #db6d28
BLUE_COLOR = (88, 166, 255)  # #58a6ff

# Category colors
CATEGORY_COLORS = {
    "FOODS": (63, 185, 80),       # Green
    "HOBBIES": (88, 166, 255),    # Blue
    "HOUSEHOLD": (219, 109, 40),  # Orange
}

# Tier sizes (radius in pixels)
TIER_SIZES = {
    "micro": 2,
    "small": 4,
    "medium": 6,
    "large": 9,
    "mega": 12,
    "giant": 16,
}

# Phase frame ranges (adjusted for 160 frames)
PHASE_1 = (0, 24)    # Building Network
PHASE_2 = (25, 48)   # Supply Flowing
PHASE_3 = (49, 72)   # DISRUPTION!
PHASE_4 = (73, 104)  # Cascade Impact
PHASE_5 = (105, 136) # AI Agent Responds
PHASE_6 = (137, 160) # Result


def get_font(size: int):
    """Get a font, falling back to default if necessary."""
    try:
        # Try common system fonts
        for font_name in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]:
            if os.path.exists(font_name):
                return ImageFont.truetype(font_name, size)
    except Exception:
        pass
    return ImageFont.load_default()


def lerp(a, b, t):
    """Linear interpolation between a and b."""
    return a + (b - a) * max(0, min(1, t))


def ease_out_cubic(t):
    """Cubic ease-out function."""
    return 1 - pow(1 - t, 3)


def ease_in_out_quad(t):
    """Quadratic ease-in-out function."""
    return 2 * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 2) / 2


def calculate_circular_layout(n_items, center_x, center_y, radius, start_angle=0):
    """Calculate positions in a circular layout."""
    positions = []
    for i in range(n_items):
        angle = start_angle + (2 * math.pi * i) / n_items
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        positions.append((x, y))
    return positions


class NetworkAnimator:
    """Animator for the LevyFly network story."""

    def __init__(self, network_data):
        self.data = network_data
        self.frames = []

        # Center of canvas
        self.center_x = CANVAS_WIDTH // 2
        self.center_y = CANVAS_HEIGHT // 2 + 30  # Slightly down to leave room for title

        # Calculate positions
        self._calculate_positions()

        # Disrupted supplier (pick the largest giant)
        giants = [s for s in self.data.suppliers if s.tier == "giant"]
        self.disrupted_supplier = max(giants, key=lambda s: s.product_count) if giants else self.data.suppliers[0]

        # Fonts
        self.title_font = get_font(36)
        self.subtitle_font = get_font(24)
        self.stat_font = get_font(18)
        self.small_font = get_font(14)

    def _calculate_positions(self):
        """Calculate positions for all nodes in a radial layout."""
        # Stores in center ring (squares)
        self.store_positions = {}
        store_radius = 120
        store_pos_list = calculate_circular_layout(
            len(self.data.stores),
            self.center_x, self.center_y,
            store_radius,
            start_angle=-math.pi/2  # Start from top
        )
        for i, store_id in enumerate(self.data.stores):
            self.store_positions[store_id] = store_pos_list[i]

        # Suppliers in outer rings by tier
        self.supplier_positions = {}
        tier_radii = {
            "giant": 200,
            "mega": 250,
            "large": 300,
            "medium": 340,
            "small": 370,
            "micro": 395,
        }

        # Group suppliers by tier
        tier_groups = {}
        for sup in self.data.suppliers:
            if sup.tier not in tier_groups:
                tier_groups[sup.tier] = []
            tier_groups[sup.tier].append(sup)

        # Position each tier
        for tier, radius in tier_radii.items():
            suppliers = tier_groups.get(tier, [])
            if not suppliers:
                continue

            # Sort suppliers by category for better color clustering
            suppliers.sort(key=lambda s: s.category)

            positions = calculate_circular_layout(
                len(suppliers),
                self.center_x, self.center_y,
                radius,
                start_angle=-math.pi/2 + random.uniform(0, 0.1)  # Slight offset per tier
            )
            for i, sup in enumerate(suppliers):
                self.supplier_positions[sup.id] = positions[i]

    def _get_supplier_color(self, supplier, base_alpha=255):
        """Get color for supplier based on category."""
        cat = supplier.category
        color = CATEGORY_COLORS.get(cat, (100, 100, 100))
        return (*color, base_alpha)

    def _draw_background(self, draw, frame):
        """Draw the dark background with subtle grid."""
        # Background already filled, add subtle radial gradient feel with concentric circles
        for r in range(400, 50, -50):
            alpha = int(10 + (400 - r) * 0.02)
            gray = 15 + (400 - r) // 30
            draw.ellipse(
                [self.center_x - r, self.center_y - r,
                 self.center_x + r, self.center_y + r],
                outline=(gray, gray, gray)
            )

    def _draw_title(self, draw, text, alpha=255):
        """Draw title at the top."""
        color = (TEXT_COLOR[0], TEXT_COLOR[1], TEXT_COLOR[2])
        # Center the text
        bbox = draw.textbbox((0, 0), text, font=self.title_font)
        text_width = bbox[2] - bbox[0]
        x = (CANVAS_WIDTH - text_width) // 2
        draw.text((x, 30), text, fill=color, font=self.title_font)

    def _draw_subtitle(self, draw, text, y=75, color=None):
        """Draw subtitle text."""
        if color is None:
            color = ACCENT_COLOR
        bbox = draw.textbbox((0, 0), text, font=self.subtitle_font)
        text_width = bbox[2] - bbox[0]
        x = (CANVAS_WIDTH - text_width) // 2
        draw.text((x, y), text, fill=color, font=self.subtitle_font)

    def _draw_stats(self, draw, stats_text, y=740):
        """Draw statistics at the bottom."""
        bbox = draw.textbbox((0, 0), stats_text, font=self.stat_font)
        text_width = bbox[2] - bbox[0]
        x = (CANVAS_WIDTH - text_width) // 2
        draw.text((x, y), stats_text, fill=TEXT_COLOR, font=self.stat_font)

    def _draw_store(self, draw, store_id, alpha=255, highlight_color=None):
        """Draw a store as a square."""
        x, y = self.store_positions[store_id]
        size = 14
        color = highlight_color if highlight_color else ACCENT_COLOR
        color = (*color, alpha) if len(color) == 3 else color
        draw.rectangle(
            [x - size, y - size, x + size, y + size],
            fill=color[:3],
            outline=(255, 255, 255)
        )

    def _draw_supplier(self, draw, supplier, alpha=255, highlight_color=None):
        """Draw a supplier as a circle."""
        x, y = self.supplier_positions[supplier.id]
        size = TIER_SIZES[supplier.tier]

        if highlight_color:
            color = highlight_color
        else:
            color = self._get_supplier_color(supplier)[:3]

        # Make larger suppliers more visible with outline
        if supplier.tier in ["giant", "mega", "large"]:
            draw.ellipse(
                [x - size - 1, y - size - 1, x + size + 1, y + size + 1],
                outline=(255, 255, 255)
            )

        draw.ellipse(
            [x - size, y - size, x + size, y + size],
            fill=color
        )

    def _draw_edge(self, draw, from_pos, to_pos, color=(80, 80, 80), width=1, dashed=False):
        """Draw an edge between two positions."""
        x1, y1 = from_pos
        x2, y2 = to_pos

        if dashed:
            # Draw dashed line
            length = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            dash_len = 5
            num_dashes = int(length / (dash_len * 2))
            for i in range(num_dashes):
                t1 = (i * 2 * dash_len) / length
                t2 = ((i * 2 + 1) * dash_len) / length
                if t2 > 1:
                    t2 = 1
                dx1 = lerp(x1, x2, t1)
                dy1 = lerp(y1, y2, t1)
                dx2 = lerp(x1, x2, t2)
                dy2 = lerp(y1, y2, t2)
                draw.line([(dx1, dy1), (dx2, dy2)], fill=color, width=width)
        else:
            draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

    def _draw_pulse_on_edge(self, draw, from_pos, to_pos, progress, color=(255, 255, 255), size=4):
        """Draw a pulsing dot traveling along an edge."""
        x1, y1 = from_pos
        x2, y2 = to_pos
        x = lerp(x1, x2, progress)
        y = lerp(y1, y2, progress)
        draw.ellipse([x - size, y - size, x + size, y + size], fill=color)

    def _draw_flash_ring(self, draw, x, y, radius, color, width=3):
        """Draw a flash/pulse ring effect."""
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            outline=color,
            width=width
        )

    def create_frame(self, frame_num):
        """Create a single frame of the animation."""
        img = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR + (255,))
        draw = ImageDraw.Draw(img)

        self._draw_background(draw, frame_num)

        # Determine which phase we're in
        if frame_num <= PHASE_1[1]:
            self._draw_phase1(draw, frame_num)
        elif frame_num <= PHASE_2[1]:
            self._draw_phase2(draw, frame_num)
        elif frame_num <= PHASE_3[1]:
            self._draw_phase3(draw, frame_num)
        elif frame_num <= PHASE_4[1]:
            self._draw_phase4(draw, frame_num)
        elif frame_num <= PHASE_5[1]:
            self._draw_phase5(draw, frame_num)
        else:
            self._draw_phase6(draw, frame_num)

        return img

    def _draw_phase1(self, draw, frame):
        """Phase 1: Building Network - suppliers appear tier by tier."""
        progress = (frame - PHASE_1[0]) / (PHASE_1[1] - PHASE_1[0])

        # Title fades in
        title_alpha = int(min(255, progress * 3 * 255))
        self._draw_title(draw, "LevyFly - 1,600 Suppliers, 10 Stores")

        # Tier reveal timing
        tier_order = ["micro", "small", "medium", "large", "mega", "giant"]

        # Draw stores first (appear at 20% progress)
        if progress > 0.2:
            store_alpha = int(min(255, (progress - 0.2) * 5 * 255))
            for store_id in self.data.stores:
                self._draw_store(draw, store_id, store_alpha)

        # Reveal suppliers tier by tier
        for i, tier in enumerate(tier_order):
            tier_start = 0.1 + i * 0.12  # Staggered start times
            if progress > tier_start:
                tier_progress = min(1, (progress - tier_start) / 0.15)
                tier_alpha = int(tier_progress * 255)

                for sup in self.data.suppliers:
                    if sup.tier == tier:
                        self._draw_supplier(draw, sup, tier_alpha)

        # Stats
        if progress > 0.7:
            self._draw_stats(draw, "Building complex supply chain network...")

    def _draw_phase2(self, draw, frame):
        """Phase 2: Supply Flowing - animated lines/pulses."""
        progress = (frame - PHASE_2[0]) / (PHASE_2[1] - PHASE_2[0])

        self._draw_title(draw, "LevyFly - Supply Chain in Motion")

        # Draw all suppliers
        for sup in self.data.suppliers:
            self._draw_supplier(draw, sup)

        # Draw stores
        for store_id in self.data.stores:
            self._draw_store(draw, store_id)

        # Draw edges from suppliers to stores (sample for performance)
        # Focus on larger suppliers for visual clarity
        large_suppliers = [s for s in self.data.suppliers if s.tier in ["giant", "mega", "large"]]

        for sup in large_suppliers:
            sup_pos = self.supplier_positions[sup.id]
            # Connect to stores based on category
            for store_id in self.data.stores:
                store_pos = self.store_positions[store_id]

                # Determine line thickness based on tier
                width = {"giant": 3, "mega": 2, "large": 1}.get(sup.tier, 1)

                # Draw edge with some transparency
                edge_color = self._get_supplier_color(sup)[:3]
                self._draw_edge(draw, sup_pos, store_pos,
                               color=tuple(c // 3 for c in edge_color), width=width)

                # Animated pulse dots
                pulse_progress = (progress + sup_pos[0] / 1000 + store_pos[1] / 800) % 1.0
                self._draw_pulse_on_edge(
                    draw, sup_pos, store_pos, pulse_progress,
                    color=edge_color, size=3 if sup.tier == "giant" else 2
                )

        # Stats
        self._draw_subtitle(draw, "3,049 products flowing | Fill Rate: 99.9%", y=110, color=GREEN_COLOR)
        self._draw_stats(draw, "Optimized supply flow across all channels")

    def _draw_phase3(self, draw, frame):
        """Phase 3: DISRUPTION! - one giant supplier turns red."""
        progress = (frame - PHASE_3[0]) / (PHASE_3[1] - PHASE_3[0])

        self._draw_title(draw, "DISRUPTION!")

        disrupted_id = self.disrupted_supplier.id
        disrupted_pos = self.supplier_positions[disrupted_id]

        # Draw all suppliers
        for sup in self.data.suppliers:
            if sup.id == disrupted_id:
                # Flash effect for disrupted supplier
                flash_intensity = abs(math.sin(progress * math.pi * 4))
                red_val = int(200 + 55 * flash_intensity)
                self._draw_supplier(draw, sup, highlight_color=(red_val, 50, 50))

                # Flash ring effect
                ring_radius = 30 + int(progress * 40)
                ring_alpha = int((1 - progress * 0.5) * 255)
                self._draw_flash_ring(draw, disrupted_pos[0], disrupted_pos[1],
                                     ring_radius, RED_COLOR, width=2)
            else:
                self._draw_supplier(draw, sup)

        # Draw stores
        for store_id in self.data.stores:
            self._draw_store(draw, store_id)

        # Draw edges from disrupted supplier as breaking (dashed red)
        large_suppliers = [s for s in self.data.suppliers if s.tier in ["giant", "mega", "large"]]
        for sup in large_suppliers:
            sup_pos = self.supplier_positions[sup.id]
            for store_id in self.data.stores:
                store_pos = self.store_positions[store_id]

                if sup.id == disrupted_id and progress > 0.3:
                    # Breaking edge
                    self._draw_edge(draw, sup_pos, store_pos, color=RED_COLOR, width=2, dashed=True)
                else:
                    edge_color = self._get_supplier_color(sup)[:3]
                    self._draw_edge(draw, sup_pos, store_pos,
                                   color=tuple(c // 3 for c in edge_color), width=1)

        # Warning text
        products_at_risk = self.disrupted_supplier.product_count
        self._draw_subtitle(draw, f"Giant Supplier DOWN - {products_at_risk} products at risk",
                           y=110, color=RED_COLOR)

    def _draw_phase4(self, draw, frame):
        """Phase 4: Cascade Impact - red wave propagates."""
        progress = (frame - PHASE_4[0]) / (PHASE_4[1] - PHASE_4[0])

        self._draw_title(draw, "Cascade Impact")

        disrupted_id = self.disrupted_supplier.id
        disrupted_pos = self.supplier_positions[disrupted_id]

        # Affected stores (3 stores get impacted progressively)
        affected_stores = self.data.stores[:3]  # First 3 stores

        # Draw suppliers
        for sup in self.data.suppliers:
            if sup.id == disrupted_id:
                self._draw_supplier(draw, sup, highlight_color=RED_COLOR)
            elif sup.tier in ["giant", "mega"]:
                # Other large suppliers glow to show increased load
                glow = int(abs(math.sin(progress * math.pi * 2)) * 100)
                base_color = self._get_supplier_color(sup)[:3]
                glow_color = tuple(min(255, c + glow) for c in base_color)
                self._draw_supplier(draw, sup, highlight_color=glow_color)
            else:
                self._draw_supplier(draw, sup)

        # Draw stores with cascade effect
        for i, store_id in enumerate(self.data.stores):
            if store_id in affected_stores:
                cascade_delay = i * 0.2
                if progress > cascade_delay:
                    local_progress = (progress - cascade_delay) / 0.3
                    if local_progress < 0.5:
                        # Yellow flash
                        self._draw_store(draw, store_id, highlight_color=YELLOW_COLOR)
                    else:
                        # Turn red
                        self._draw_store(draw, store_id, highlight_color=RED_COLOR)
            else:
                self._draw_store(draw, store_id)

        # Draw edges
        large_suppliers = [s for s in self.data.suppliers if s.tier in ["giant", "mega", "large"]]
        for sup in large_suppliers:
            sup_pos = self.supplier_positions[sup.id]
            for store_id in self.data.stores:
                store_pos = self.store_positions[store_id]

                if sup.id == disrupted_id:
                    self._draw_edge(draw, sup_pos, store_pos, color=RED_COLOR, width=2, dashed=True)
                elif sup.tier in ["giant", "mega"]:
                    # Show increased load with thicker lines
                    edge_color = self._get_supplier_color(sup)[:3]
                    self._draw_edge(draw, sup_pos, store_pos,
                                   color=edge_color, width=2)
                else:
                    edge_color = self._get_supplier_color(sup)[:3]
                    self._draw_edge(draw, sup_pos, store_pos,
                                   color=tuple(c // 3 for c in edge_color), width=1)

        # Stockout counter
        stockouts = int(progress * 8)
        self._draw_subtitle(draw, f"Cascade: 3 stores impacted, {stockouts}% of products disrupted",
                           y=110, color=YELLOW_COLOR)
        self._draw_stats(draw, "Traditional systems would face stockouts...")

    def _draw_phase5(self, draw, frame):
        """Phase 5: AI Agent Responds - green reroutes appear."""
        progress = (frame - PHASE_5[0]) / (PHASE_5[1] - PHASE_5[0])

        self._draw_title(draw, "AI Agent Responds")

        disrupted_id = self.disrupted_supplier.id
        affected_stores = self.data.stores[:3]

        # Alternative suppliers (other giants and megas)
        alt_suppliers = [s for s in self.data.suppliers
                        if s.tier in ["giant", "mega"] and s.id != disrupted_id][:5]

        # Draw suppliers
        for sup in self.data.suppliers:
            if sup.id == disrupted_id:
                # Faded red (being bypassed)
                self._draw_supplier(draw, sup, alpha=150, highlight_color=(100, 40, 40))
            elif sup in alt_suppliers:
                # Green glow for alternative suppliers
                glow = int(progress * 150)
                self._draw_supplier(draw, sup, highlight_color=(glow, 200, glow))
            else:
                self._draw_supplier(draw, sup)

        # Draw stores with recovery
        for i, store_id in enumerate(self.data.stores):
            if store_id in affected_stores:
                recovery_delay = i * 0.15
                if progress > recovery_delay:
                    local_progress = (progress - recovery_delay) / 0.2
                    if local_progress < 0.5:
                        # Yellow (recovering)
                        self._draw_store(draw, store_id, highlight_color=YELLOW_COLOR)
                    else:
                        # Green (recovered)
                        self._draw_store(draw, store_id, highlight_color=GREEN_COLOR)
            else:
                self._draw_store(draw, store_id)

        # Draw green reroute edges
        for alt_sup in alt_suppliers:
            alt_pos = self.supplier_positions[alt_sup.id]
            for store_id in affected_stores:
                store_pos = self.store_positions[store_id]

                # Green reroute edges appearing progressively
                edge_progress = min(1, progress * 2)
                if edge_progress > 0.3:
                    self._draw_edge(draw, alt_pos, store_pos, color=GREEN_COLOR, width=2)

                    # Animated pulse on reroute
                    pulse_progress = (progress * 3 + alt_pos[0] / 500) % 1.0
                    self._draw_pulse_on_edge(draw, alt_pos, store_pos, pulse_progress,
                                            color=GREEN_COLOR, size=4)

        # Green pulse from center (AI engine)
        if progress < 0.4:
            pulse_radius = int(progress * 300)
            self._draw_flash_ring(draw, self.center_x, self.center_y, pulse_radius, GREEN_COLOR, width=3)

        self._draw_subtitle(draw, "AI reroutes supply in 2.3 days | 0 stockouts",
                           y=110, color=GREEN_COLOR)
        self._draw_stats(draw, "LevyFly AI maintains service continuity")

    def _draw_phase6(self, draw, frame):
        """Phase 6: Result - final stats."""
        progress = (frame - PHASE_6[0]) / (PHASE_6[1] - PHASE_6[0])

        self._draw_title(draw, "LevyFly - Results")

        # Draw all suppliers in stable green-tinted state
        for sup in self.data.suppliers:
            base_color = self._get_supplier_color(sup)[:3]
            # Slight green tint to show stability
            stable_color = tuple(min(255, int(c * 0.8 + 40)) for c in base_color)
            self._draw_supplier(draw, sup, highlight_color=stable_color)

        # Draw all stores in green
        for store_id in self.data.stores:
            self._draw_store(draw, store_id, highlight_color=GREEN_COLOR)

        # Draw stable edges
        large_suppliers = [s for s in self.data.suppliers if s.tier in ["giant", "mega", "large"]]
        for sup in large_suppliers:
            sup_pos = self.supplier_positions[sup.id]
            for store_id in self.data.stores:
                store_pos = self.store_positions[store_id]
                self._draw_edge(draw, sup_pos, store_pos, color=(50, 100, 50), width=1)

        # Fade in final stats
        if progress > 0.2:
            stat_alpha = int(min(255, (progress - 0.2) * 2 * 255))

            # Traditional vs LevyFly comparison
            y_start = 680

            # Draw comparison stats
            trad_text = "Traditional (s,S): 736% excess inventory"
            levy_text = "LevyFly AI: 65% excess | 3.7x better score"
            tagline = "AI agents that learn from your real data"

            # Traditional (red/faded)
            bbox = draw.textbbox((0, 0), trad_text, font=self.stat_font)
            x = (CANVAS_WIDTH - bbox[2] + bbox[0]) // 2
            draw.text((x, y_start), trad_text, fill=(200, 100, 100), font=self.stat_font)

            # LevyFly (green/bright)
            if progress > 0.4:
                bbox = draw.textbbox((0, 0), levy_text, font=self.stat_font)
                x = (CANVAS_WIDTH - bbox[2] + bbox[0]) // 2
                draw.text((x, y_start + 25), levy_text, fill=GREEN_COLOR, font=self.stat_font)

            # Tagline
            if progress > 0.6:
                bbox = draw.textbbox((0, 0), tagline, font=self.subtitle_font)
                x = (CANVAS_WIDTH - bbox[2] + bbox[0]) // 2
                draw.text((x, y_start + 55), tagline, fill=ACCENT_COLOR, font=self.subtitle_font)

    def create_animation(self, output_path):
        """Create the full animation and save as GIF."""
        print(f"Creating {TOTAL_FRAMES} frames at {FPS} fps...")

        frames = []
        for i in range(TOTAL_FRAMES):
            if i % 20 == 0:
                print(f"  Frame {i}/{TOTAL_FRAMES}")
            frame = self.create_frame(i)
            # Convert to P mode for better GIF compression (64 colors for smaller size)
            frames.append(frame.convert('P', palette=Image.ADAPTIVE, colors=64))

        print(f"Saving animation to {output_path}...")

        # Calculate duration per frame in milliseconds
        duration = int(1000 / FPS)  # ~42ms per frame for 24fps

        # Save as GIF
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=0,  # Infinite loop
            optimize=True,
        )

        # Check file size
        file_size = os.path.getsize(output_path)
        print(f"Animation saved: {output_path}")
        print(f"File size: {file_size / 1024 / 1024:.2f} MB")

        if file_size > 2 * 1024 * 1024:
            print("Warning: File size exceeds 2MB target")


def main():
    """Main entry point."""
    data_dir = "data/walmart_m5"
    output_path = "docs/assets/network_hero.gif"

    # Check if data directory exists
    if not os.path.exists(data_dir):
        print(f"Error: Data directory not found: {data_dir}")
        sys.exit(1)

    # Build network
    print("Loading network data...")
    network_data = build_complex_network(data_dir, target_suppliers=1600, seed=42)
    print(f"Loaded {len(network_data.suppliers)} suppliers, {len(network_data.stores)} stores")

    # Create animator
    animator = NetworkAnimator(network_data)

    # Create animation
    animator.create_animation(output_path)

    print("Done!")


if __name__ == "__main__":
    main()
