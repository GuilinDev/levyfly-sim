# -*- coding: utf-8 -*-
"""
Supply chain network visualization renderer.
Generates PIL frames for animation.
"""
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Tuple, Optional
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simulation.network import SupplyChainNetwork, NodeType, Node
from simulation.engine import DaySnapshot


# Colors
BG_COLOR = (15, 20, 35)
GRID_COLOR = (25, 35, 55)
SUPPLIER_COLOR = (46, 204, 113)      # Green
WAREHOUSE_COLOR = (52, 152, 219)     # Blue
STORE_COLOR = (231, 76, 60)          # Red
STORE_OK_COLOR = (155, 89, 182)      # Purple
DISRUPTED_COLOR = (255, 50, 50)
EDGE_COLOR = (60, 80, 110)
EDGE_ACTIVE_COLOR = (100, 180, 255)
TRANSIT_COLOR = (241, 196, 15)       # Yellow
TEXT_COLOR = (220, 225, 235)
MUTED_TEXT = (120, 130, 150)
PANEL_BG = (20, 28, 48)
PANEL_BORDER = (40, 55, 85)
STOCKOUT_FLASH = (255, 80, 80)
METRIC_GREEN = (46, 204, 113)
METRIC_YELLOW = (241, 196, 15)
METRIC_RED = (231, 76, 60)


class SupplyChainRenderer:
    """
    Renders supply chain simulation frames.
    """

    WIDTH = 1200
    HEIGHT = 700
    NETWORK_AREA = (30, 80, 750, 620)  # left, top, right, bottom
    DASHBOARD_X = 770
    NODE_RADIUS = 28

    def __init__(self, network: SupplyChainNetwork):
        self.network = network
        self._scale_positions()

        # Try to load font
        self.font_sm = ImageFont.load_default()
        self.font_md = ImageFont.load_default()
        self.font_lg = ImageFont.load_default()
        try:
            for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                       "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
                if os.path.exists(fp):
                    self.font_sm = ImageFont.truetype(fp, 11)
                    self.font_md = ImageFont.truetype(fp, 13)
                    self.font_lg = ImageFont.truetype(fp, 18)
                    self.font_title = ImageFont.truetype(fp, 22)
                    break
        except Exception:
            self.font_title = self.font_lg

    def _scale_positions(self):
        """Scale node positions to fit in the network area."""
        area = self.NETWORK_AREA
        w = area[2] - area[0]
        h = area[3] - area[1]

        xs = [n.position[0] for n in self.network.nodes.values()]
        ys = [n.position[1] for n in self.network.nodes.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        range_x = max_x - min_x or 1
        range_y = max_y - min_y or 1

        self.scaled_pos = {}
        for node in self.network.nodes.values():
            sx = area[0] + 50 + (node.position[0] - min_x) / range_x * (w - 100)
            sy = area[1] + 30 + (node.position[1] - min_y) / range_y * (h - 60)
            self.scaled_pos[node.id] = (int(sx), int(sy))

    def render_frame(self, snapshot: DaySnapshot) -> Image.Image:
        """Render a single frame for the given simulation state."""
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Grid background
        for x in range(0, self.WIDTH, 40):
            draw.line([(x, 0), (x, self.HEIGHT)], fill=GRID_COLOR, width=1)
        for y in range(0, self.HEIGHT, 40):
            draw.line([(0, y), (self.WIDTH, y)], fill=GRID_COLOR, width=1)

        # Title bar
        draw.rectangle([(0, 0), (self.WIDTH, 60)], fill=PANEL_BG)
        draw.line([(0, 60), (self.WIDTH, 60)], fill=PANEL_BORDER, width=2)
        draw.text((20, 12), "⚡ LevyFly", fill=(100, 180, 255), font=self.font_title)
        draw.text((165, 16), "Supply Chain Simulation", fill=MUTED_TEXT, font=self.font_md)
        draw.text((20, 38), f"Day {snapshot.day:>3d}/30", fill=TEXT_COLOR, font=self.font_md)

        # Disruption alert
        if snapshot.disruptions:
            alert_text = f"🚨 DISRUPTION: {', '.join(snapshot.disruptions.keys())}"
            draw.text((250, 38), alert_text, fill=DISRUPTED_COLOR, font=self.font_md)

        # Draw edges
        self._draw_edges(draw, snapshot)

        # Draw in-transit indicators
        self._draw_transit(draw, snapshot)

        # Draw nodes
        self._draw_nodes(draw, snapshot)

        # Dashboard panel
        self._draw_dashboard(draw, img, snapshot)

        # Event feed
        self._draw_event_feed(draw, snapshot)

        return img

    def _draw_edges(self, draw: ImageDraw.Draw, snapshot: DaySnapshot):
        """Draw edges between nodes."""
        for edge in self.network.edges:
            if edge.source_id in self.scaled_pos and edge.target_id in self.scaled_pos:
                p1 = self.scaled_pos[edge.source_id]
                p2 = self.scaled_pos[edge.target_id]

                # Check if edge has in-transit items
                has_transit = len(edge.in_transit) > 0
                color = EDGE_ACTIVE_COLOR if has_transit else EDGE_COLOR
                width = 2 if has_transit else 1

                # Disrupted source
                if edge.source_id in snapshot.disruptions:
                    color = (80, 30, 30)

                draw.line([p1, p2], fill=color, width=width)

                # Arrow
                self._draw_arrow(draw, p1, p2, color)

    def _draw_arrow(self, draw, p1, p2, color, size=8):
        """Draw an arrowhead at the midpoint of a line."""
        mx = (p1[0] + p2[0]) / 2
        my = (p1[1] + p2[1]) / 2
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.sqrt(dx*dx + dy*dy)
        if length == 0:
            return
        dx /= length
        dy /= length

        # Arrow triangle
        tip = (int(mx + dx * size), int(my + dy * size))
        left = (int(mx - dx * size/2 - dy * size/2), int(my - dy * size/2 + dx * size/2))
        right = (int(mx - dx * size/2 + dy * size/2), int(my - dy * size/2 - dx * size/2))
        draw.polygon([tip, left, right], fill=color)

    def _draw_transit(self, draw: ImageDraw.Draw, snapshot: DaySnapshot):
        """Draw in-transit shipment indicators."""
        for item in snapshot.in_transit:
            src = item["from"]
            dst = item["to"]
            if src in self.scaled_pos and dst in self.scaled_pos:
                p1 = self.scaled_pos[src]
                p2 = self.scaled_pos[dst]
                # Position along the route based on days_left
                # This is approximate
                total_transit = 3  # approximate
                progress = max(0.2, 1.0 - item["days_left"] / max(1, total_transit))
                tx = int(p1[0] + (p2[0] - p1[0]) * progress)
                ty = int(p1[1] + (p2[1] - p1[1]) * progress)

                # Package icon
                draw.rectangle([(tx-6, ty-6), (tx+6, ty+6)], fill=TRANSIT_COLOR, outline=(200, 160, 0))
                draw.text((tx-3, ty-5), "📦", font=self.font_sm)

    def _draw_nodes(self, draw: ImageDraw.Draw, snapshot: DaySnapshot):
        """Draw network nodes."""
        for node in self.network.nodes.values():
            pos = self.scaled_pos[node.id]
            r = self.NODE_RADIUS
            is_disrupted = node.id in snapshot.disruptions

            # Choose color
            if is_disrupted:
                color = DISRUPTED_COLOR
                # Pulsing effect
                pulse = int(abs(math.sin(snapshot.day * 0.5)) * 15)
                r += pulse
            elif node.node_type == NodeType.SUPPLIER:
                color = SUPPLIER_COLOR
            elif node.node_type == NodeType.WAREHOUSE:
                color = WAREHOUSE_COLOR
            else:
                # Store: color by stockout status
                inv = snapshot.inventories.get(node.id, {})
                total_inv = sum(inv.values())
                if total_inv < 20:
                    color = STOCKOUT_FLASH
                elif total_inv < 50:
                    color = METRIC_YELLOW
                else:
                    color = STORE_OK_COLOR

            # Glow effect
            for i in range(3, 0, -1):
                glow_r = r + i * 4
                alpha = 40 - i * 10
                glow_color = tuple(min(255, c + alpha) for c in BG_COLOR)
                draw.ellipse(
                    [(pos[0]-glow_r, pos[1]-glow_r), (pos[0]+glow_r, pos[1]+glow_r)],
                    outline=(*color[:3],)
                )

            # Main circle
            draw.ellipse(
                [(pos[0]-r, pos[1]-r), (pos[0]+r, pos[1]+r)],
                fill=color, outline=(255, 255, 255)
            )

            # Node label
            label = node.id
            if is_disrupted:
                label = "⚠️" + label
            bbox = draw.textbbox((0, 0), label, font=self.font_md)
            tw = bbox[2] - bbox[0]
            draw.text((pos[0] - tw//2, pos[1] - 7), label, fill=(255, 255, 255), font=self.font_md)

            # Name below
            bbox = draw.textbbox((0, 0), node.name, font=self.font_sm)
            tw = bbox[2] - bbox[0]
            draw.text((pos[0] - tw//2, pos[1] + r + 4), node.name, fill=MUTED_TEXT, font=self.font_sm)

            # Inventory bar (for warehouses and stores)
            if node.node_type in (NodeType.WAREHOUSE, NodeType.STORE):
                inv = snapshot.inventories.get(node.id, {})
                total = sum(inv.values())
                capacity = node.capacity
                fill_pct = min(1.0, total / max(1, capacity))

                bar_w = 50
                bar_h = 6
                bar_x = pos[0] - bar_w // 2
                bar_y = pos[1] + r + 18

                # Background
                draw.rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)],
                              fill=(40, 40, 60), outline=PANEL_BORDER)
                # Fill
                bar_color = METRIC_GREEN if fill_pct > 0.3 else METRIC_YELLOW if fill_pct > 0.1 else METRIC_RED
                draw.rectangle([(bar_x, bar_y), (bar_x + int(bar_w * fill_pct), bar_y + bar_h)],
                              fill=bar_color)

    def _draw_dashboard(self, draw: ImageDraw.Draw, img: Image.Image, snapshot: DaySnapshot):
        """Draw the dashboard panel on the right side."""
        x = self.DASHBOARD_X
        panel_w = self.WIDTH - x - 10

        # Panel background
        draw.rectangle([(x, 70), (self.WIDTH - 10, self.HEIGHT - 10)],
                      fill=PANEL_BG, outline=PANEL_BORDER, width=2)

        y = 82

        # Title
        draw.text((x + 10, y), "📊 Dashboard", fill=TEXT_COLOR, font=self.font_lg)
        y += 30

        # Metrics
        metrics = snapshot.metrics
        fill_rate = metrics.get("fill_rate", 1.0)
        fr_color = METRIC_GREEN if fill_rate > 0.95 else METRIC_YELLOW if fill_rate > 0.85 else METRIC_RED

        metric_items = [
            ("Fill Rate", f"{fill_rate:.1%}", fr_color),
            ("Stockouts", str(metrics.get("stockout_count", 0)),
             METRIC_RED if metrics.get("stockout_count", 0) > 0 else METRIC_GREEN),
            ("Orders", str(metrics.get("total_orders", 0)), TEXT_COLOR),
            ("In Transit", str(metrics.get("in_transit_shipments", 0)), TRANSIT_COLOR),
            ("Disruptions", str(metrics.get("active_disruptions", 0)),
             DISRUPTED_COLOR if metrics.get("active_disruptions", 0) > 0 else METRIC_GREEN),
        ]

        for label, value, color in metric_items:
            draw.text((x + 15, y), label, fill=MUTED_TEXT, font=self.font_sm)
            draw.text((x + panel_w - 70, y), value, fill=color, font=self.font_md)
            y += 22

        y += 10
        draw.line([(x + 10, y), (self.WIDTH - 20, y)], fill=PANEL_BORDER)
        y += 10

        # Inventory levels
        draw.text((x + 10, y), "📦 Inventory", fill=TEXT_COLOR, font=self.font_md)
        y += 22

        for node_id in ["W1", "W2", "R1", "R2", "R3", "R4", "R5"]:
            inv = snapshot.inventories.get(node_id, {})
            total = sum(inv.values())
            node = self.network.get_node(node_id)
            capacity = node.capacity if node else 1000
            pct = total / max(1, capacity)

            name = node.name[:15] if node else node_id
            bar_color = METRIC_GREEN if pct > 0.3 else METRIC_YELLOW if pct > 0.1 else METRIC_RED

            draw.text((x + 15, y), name, fill=MUTED_TEXT, font=self.font_sm)

            # Mini bar
            bar_x = x + 120
            bar_w = panel_w - 140
            draw.rectangle([(bar_x, y+2), (bar_x + bar_w, y + 12)],
                          fill=(30, 35, 50), outline=PANEL_BORDER)
            draw.rectangle([(bar_x, y+2), (bar_x + int(bar_w * min(1, pct)), y + 12)],
                          fill=bar_color)

            # Value
            draw.text((bar_x + bar_w + 5, y), str(total), fill=TEXT_COLOR, font=self.font_sm)
            y += 18

        y += 10
        draw.line([(x + 10, y), (self.WIDTH - 20, y)], fill=PANEL_BORDER)
        y += 10

        # Agent decisions
        draw.text((x + 10, y), "🤖 Agent Decisions", fill=TEXT_COLOR, font=self.font_md)
        y += 22

        for dec in snapshot.decisions[-5:]:  # last 5
            action_color = METRIC_YELLOW if dec.action == "emergency_reorder" else (100, 180, 255)
            text = f"{dec.agent_id}: {dec.action}"
            draw.text((x + 15, y), text[:35], fill=action_color, font=self.font_sm)
            y += 15
            if y > self.HEIGHT - 40:
                break

    def _draw_event_feed(self, draw: ImageDraw.Draw, snapshot: DaySnapshot):
        """Draw scrolling event feed at the bottom."""
        # Bottom bar
        bar_y = self.HEIGHT - 30
        draw.rectangle([(0, bar_y), (self.DASHBOARD_X - 5, self.HEIGHT)], fill=PANEL_BG)

        critical_events = [e for e in snapshot.events if e.severity in ("warning", "critical")]
        if critical_events:
            text = critical_events[-1].description[:80]
            color = DISRUPTED_COLOR if critical_events[-1].severity == "critical" else METRIC_YELLOW
        else:
            text = f"Day {snapshot.day} — All systems nominal"
            color = METRIC_GREEN

        draw.text((15, bar_y + 6), text, fill=color, font=self.font_sm)

    # Legend
    def _draw_legend(self, draw):
        """Draw legend."""
        y = self.HEIGHT - 60
        items = [
            ("🟢 Supplier", SUPPLIER_COLOR),
            ("🔵 Warehouse", WAREHOUSE_COLOR),
            ("🟣 Store", STORE_OK_COLOR),
            ("📦 In Transit", TRANSIT_COLOR),
        ]
        x = 30
        for label, color in items:
            draw.rectangle([(x, y), (x+10, y+10)], fill=color)
            draw.text((x + 14, y - 1), label, fill=MUTED_TEXT, font=self.font_sm)
            x += 120
