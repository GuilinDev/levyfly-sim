#!/usr/bin/env python3
"""
LLM-Powered Supply Chain Agent — Strategic decision-making with reasoning.

Architecture:
  - Day-to-day: Evolved Policy handles routine reorders (fast, no API calls)
  - Anomaly detected: LLM agent consulted for strategic decisions
  - All strategic decisions include natural language reasoning chain

The LLM agent is NOT called on every tick. It's called when:
  1. Disruption detected (supplier goes down)
  2. Stockout occurs or is imminent
  3. Demand anomaly detected (>2σ from mean)
  4. Weekly strategic review (every 7 days)

Uses local Ollama models — no API costs, low latency (~1-3s per call).
"""
import json
import subprocess
import statistics
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field


@dataclass
class StrategicDecision:
    """A decision made by the LLM agent with full reasoning."""
    day: int
    trigger: str           # What triggered the decision
    context: str           # Situation summary given to LLM
    reasoning: str         # LLM's reasoning chain
    action: str            # What the agent decided to do
    parameters: Dict       # Changed parameters (if any)
    confidence: float      # 0-1, self-assessed by LLM


class LLMAgent:
    """
    LLM-powered strategic agent for supply chain decisions.
    
    Wraps an Evolved Policy for day-to-day operations,
    but consults an LLM for strategic decisions during anomalies.
    """

    def __init__(self, model: str = "mistral-small3.2:24b", 
                 base_policy=None, verbose: bool = True):
        self.model = model
        self.verbose = verbose
        self.decisions: List[StrategicDecision] = []
        self.demand_history: Dict[str, List[float]] = defaultdict(list)
        self.inventory_history: Dict[str, List[float]] = defaultdict(list)
        self.disruption_active: Dict[str, bool] = defaultdict(bool)
        self.last_review_day = 0
        self.review_interval = 14  # Bi-weekly strategic review
        self._daily_llm_calls = 0
        self._max_daily_calls = 3  # Max 3 LLM calls per sim day
        self._current_day = 0
        
        # Dynamic parameters that LLM can adjust
        self.safety_multiplier = 1.0  # Multiplied onto base policy's safety factor
        self.emergency_mode = False
        self.preferred_suppliers: Dict[str, str] = {}  # product → supplier override
        
        # Base policy for day-to-day decisions
        if base_policy is None:
            try:
                from autotuning.evolvable_policy import EvolvablePolicy
                self.base_policy = EvolvablePolicy()
            except ImportError:
                self.base_policy = None
        else:
            self.base_policy = base_policy
        
        # Verify Ollama is available
        self._ollama_available = self._check_ollama()
        if not self._ollama_available and verbose:
            print(f"  ⚠️ Ollama not available, LLM agent will use heuristic fallback")

    def _check_ollama(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, timeout=5
            )
            return self.model.split(":")[0] in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _call_llm(self, prompt: str, max_tokens: int = 500) -> str:
        """Call local LLM via Ollama HTTP API (faster than CLI)."""
        if not self._ollama_available:
            return self._heuristic_fallback(prompt)
        
        try:
            import urllib.request
            import urllib.error
            
            body = json.dumps({
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.3,
                }
            }).encode("utf-8")
            
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("response", "").strip()
        except Exception as e:
            if self.verbose:
                print(f"    ⚠️ LLM call failed: {e}")
            return self._heuristic_fallback(prompt)

    def _heuristic_fallback(self, prompt: str) -> str:
        """Fallback reasoning when LLM is unavailable."""
        if "disruption" in prompt.lower():
            return ("REASONING: Supplier disruption detected. Increasing safety stock "
                    "by 50% and activating emergency reorder protocols. "
                    "ACTION: increase_safety_buffer CONFIDENCE: 0.7")
        elif "stockout" in prompt.lower():
            return ("REASONING: Stockout risk is elevated. Current inventory below "
                    "2-day supply. Emergency reorder needed. "
                    "ACTION: emergency_reorder CONFIDENCE: 0.8")
        elif "review" in prompt.lower():
            return ("REASONING: Weekly review shows stable operations. No parameter "
                    "changes needed. Maintaining current strategy. "
                    "ACTION: maintain CONFIDENCE: 0.6")
        return "REASONING: Nominal conditions. ACTION: maintain CONFIDENCE: 0.5"

    def name(self) -> str:
        return f"LLM Agent ({self.model.split(':')[0]})"

    def _detect_anomaly(self, node_id: str, product: str, 
                         current_inventory: int, day: int,
                         daily_demand: int = 0) -> Optional[str]:
        """Detect if current conditions warrant LLM consultation."""
        key = f"{node_id}:{product}"
        
        # Track demand history
        if daily_demand > 0:
            self.demand_history[key].append(daily_demand)
        self.inventory_history[key].append(current_inventory)
        
        history = self.demand_history.get(key, [])
        if len(history) < 7:
            return None
        
        recent = history[-7:]
        avg = statistics.mean(recent)
        std = statistics.stdev(recent) if len(recent) > 1 else avg * 0.3
        
        # Check for demand spike (>2σ above mean)
        if daily_demand > avg + 2 * std and daily_demand > 0:
            return f"demand_spike: {daily_demand} vs avg {avg:.0f} (>{2*std:.0f} above mean)"
        
        # Check for imminent stockout (<1 day supply)
        if avg > 0 and current_inventory < avg * 1.0:
            return f"stockout_risk: inventory {current_inventory} < 1-day supply ({avg:.0f})"
        
        # Weekly review
        if day - self.last_review_day >= self.review_interval:
            return "weekly_review"
        
        return None

    def _build_context(self, node_id: str, product: str, 
                        current_inventory: int, day: int,
                        trigger: str, daily_demand: int) -> str:
        """Build context string for LLM prompt."""
        key = f"{node_id}:{product}"
        history = self.demand_history.get(key, [])
        recent_demand = history[-7:] if len(history) >= 7 else history
        avg_demand = statistics.mean(recent_demand) if recent_demand else 0
        
        inv_history = self.inventory_history.get(key, [])
        recent_inv = inv_history[-7:] if len(inv_history) >= 7 else inv_history
        inv_trend = "declining" if len(recent_inv) > 2 and recent_inv[-1] < recent_inv[0] else "stable"
        
        return (
            f"Day {day} | Node: {node_id} | Product: {product}\n"
            f"Current inventory: {current_inventory} units\n"
            f"Today's demand: {daily_demand} units\n"
            f"7-day avg demand: {avg_demand:.0f} units/day\n"
            f"Inventory trend: {inv_trend}\n"
            f"Emergency mode: {'YES' if self.emergency_mode else 'NO'}\n"
            f"Safety multiplier: {self.safety_multiplier:.1f}x\n"
            f"Trigger: {trigger}"
        )

    def _make_strategic_decision(self, node_id: str, product: str,
                                   current_inventory: int, day: int,
                                   trigger: str, daily_demand: int) -> StrategicDecision:
        """Consult LLM for a strategic decision."""
        context = self._build_context(
            node_id, product, current_inventory, day, trigger, daily_demand
        )
        
        prompt = f"""You are a supply chain AI agent managing inventory.
Given this situation, decide what action to take.

SITUATION:
{context}

AVAILABLE ACTIONS:
- maintain: Keep current strategy
- increase_safety_buffer: Increase safety stock multiplier (1.0-2.0)
- decrease_safety_buffer: Reduce excess inventory
- emergency_reorder: Trigger immediate large reorder
- switch_supplier: Route orders to backup supplier

Respond in this EXACT format (one line each):
REASONING: [Your analysis in 2-3 sentences]
ACTION: [one of the actions above]
PARAMS: [JSON with any parameter changes, or {{}}]
CONFIDENCE: [0.0-1.0]"""

        response = self._call_llm(prompt)
        
        # Parse response
        reasoning = ""
        action = "maintain"
        params = {}
        confidence = 0.5
        
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("REASONING:"):
                reasoning = line[10:].strip()
            elif line.startswith("ACTION:"):
                action = line[7:].strip().lower()
            elif line.startswith("PARAMS:"):
                try:
                    params = json.loads(line[7:].strip())
                except (json.JSONDecodeError, ValueError):
                    params = {}
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line[11:].strip())
                except ValueError:
                    confidence = 0.5
        
        # Apply decision
        self._apply_decision(action, params)
        
        decision = StrategicDecision(
            day=day,
            trigger=trigger,
            context=context,
            reasoning=reasoning,
            action=action,
            parameters=params,
            confidence=confidence
        )
        self.decisions.append(decision)
        
        if self.verbose:
            print(f"  🧠 Day {day} [{trigger}]: {action} "
                  f"(confidence: {confidence:.0%}) — {reasoning[:80]}")
        
        if trigger == "weekly_review":
            self.last_review_day = day
        
        return decision

    def _apply_decision(self, action: str, params: Dict):
        """Apply LLM's strategic decision to policy parameters."""
        if action == "increase_safety_buffer":
            multiplier = params.get("multiplier", 1.5)
            self.safety_multiplier = min(2.0, max(1.0, multiplier))
            self.emergency_mode = True
        elif action == "decrease_safety_buffer":
            multiplier = params.get("multiplier", 1.0)
            self.safety_multiplier = max(0.8, min(1.5, multiplier))
            self.emergency_mode = False
        elif action == "emergency_reorder":
            self.emergency_mode = True
            self.safety_multiplier = max(self.safety_multiplier, 1.5)
        elif action == "switch_supplier":
            product = params.get("product", "")
            supplier = params.get("supplier", "")
            if product and supplier:
                self.preferred_suppliers[product] = supplier
        elif action == "maintain":
            pass  # No changes

    def should_reorder(self, node_id: str, product: str, 
                        current_inventory: int, day: int, **ctx) -> Tuple[bool, int, str]:
        """
        Main reorder decision function.
        
        Day-to-day: delegates to base policy.
        Anomaly detected: consults LLM for strategic adjustment.
        """
        daily_demand = ctx.get("daily_demand", 0)
        
        # Reset daily call counter on new day
        if day != self._current_day:
            self._current_day = day
            self._daily_llm_calls = 0
        
        # Check for anomaly → LLM consultation (with call budget)
        anomaly = self._detect_anomaly(
            node_id, product, current_inventory, day, daily_demand
        )
        
        if anomaly and self._daily_llm_calls < self._max_daily_calls:
            self._make_strategic_decision(
                node_id, product, current_inventory, day, anomaly, daily_demand
            )
            self._daily_llm_calls += 1
        
        # Delegate to base policy (with modified parameters)
        if self.base_policy:
            should, qty, reason = self.base_policy.should_reorder(
                node_id, product, current_inventory, day, **ctx
            )
            
            # Apply safety multiplier from LLM decisions
            if should and self.safety_multiplier != 1.0:
                qty = int(qty * self.safety_multiplier)
                reason = f"{reason} [LLM: safety×{self.safety_multiplier:.1f}]"
            
            return should, qty, reason
        
        # Fallback: simple threshold
        if current_inventory < 300:
            return True, 600, "fallback_low_inv"
        return False, 0, ""

    def get_decision_log(self) -> List[Dict]:
        """Get all strategic decisions as dicts for reporting."""
        return [
            {
                "day": d.day,
                "trigger": d.trigger,
                "action": d.action,
                "reasoning": d.reasoning,
                "confidence": d.confidence,
                "parameters": d.parameters,
            }
            for d in self.decisions
        ]

    def get_decision_summary(self) -> str:
        """Generate a human-readable summary of all strategic decisions."""
        if not self.decisions:
            return "No strategic decisions were made during this simulation."
        
        lines = [
            f"## 🧠 LLM Agent Decision Log ({len(self.decisions)} strategic decisions)\n"
        ]
        
        for d in self.decisions:
            emoji = {
                "demand_spike": "📈",
                "stockout_risk": "⚠️",
                "weekly_review": "📋",
            }.get(d.trigger.split(":")[0], "🔔")
            
            action_emoji = {
                "maintain": "✅",
                "increase_safety_buffer": "🛡️",
                "decrease_safety_buffer": "📉",
                "emergency_reorder": "🚨",
                "switch_supplier": "🔄",
            }.get(d.action, "❓")
            
            lines.append(
                f"### Day {d.day} {emoji} {d.trigger.split(':')[0]}\n"
                f"- **Action**: {action_emoji} {d.action}\n"
                f"- **Reasoning**: {d.reasoning}\n"
                f"- **Confidence**: {d.confidence:.0%}\n"
            )
        
        # Statistics
        actions = defaultdict(int)
        for d in self.decisions:
            actions[d.action] += 1
        
        lines.append("### Summary\n")
        lines.append(f"| Action | Count |")
        lines.append(f"|--------|-------|")
        for action, count in sorted(actions.items(), key=lambda x: -x[1]):
            lines.append(f"| {action} | {count} |")
        
        avg_confidence = statistics.mean(d.confidence for d in self.decisions)
        lines.append(f"\nAverage confidence: {avg_confidence:.0%}")
        
        return "\n".join(lines)
