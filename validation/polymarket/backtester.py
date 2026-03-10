#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polymarket Backtester — Agent Credibility Validation

Tests agent prediction accuracy against real Polymarket outcomes.
Key metric: Brier Score (lower = better, 0 = perfect, 1 = worst).

Pipeline:
  1. Load resolved market with price history
  2. Simulate information flow (hourly price snapshots)
  3. Agent processes info and outputs probability estimate
  4. Compare to ground truth → Brier Score
"""
import json
import os
import math
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass, field


@dataclass
class PredictionSnapshot:
    """A single prediction at a point in time."""
    timestamp: int              # Unix timestamp
    market_price: float         # What the market thinks (consensus)
    agent_prediction: float     # What our agent predicts
    info_available: str         # Summary of info available at this time
    reasoning: str = ""         # Agent's reasoning


@dataclass
class BacktestResult:
    """Full backtest result for one market."""
    market_id: str
    question: str
    ground_truth: float          # 1.0 = YES, 0.0 = NO
    outcome: str                 # "Yes" or "No"
    volume: float
    num_snapshots: int
    agent_brier_score: float     # Agent's Brier Score
    market_brier_score: float    # Market's Brier Score (baseline)
    agent_beats_market: bool
    snapshots: List[PredictionSnapshot]
    final_agent_prediction: float
    final_market_price: float


class SimpleAgent:
    """
    A simple rule-based prediction agent.
    This is our baseline — to be replaced with LLM-powered agent.

    Strategy: Momentum + Mean Reversion
    - If price trending up strongly → follow trend
    - If price stable → slight mean reversion toward 0.5
    - Incorporates price velocity and volatility
    """

    def __init__(self, lookback: int = 5):
        self.lookback = lookback
        self.history: List[float] = []

    def reset(self):
        self.history = []

    def predict(self, current_price: float, timestamp: int, market_info: Dict) -> Tuple[float, str]:
        """
        Make a prediction given current market price and info.

        Args:
            current_price: Current market probability
            timestamp: Current time
            market_info: Additional context

        Returns:
            (probability, reasoning)
        """
        self.history.append(current_price)

        if len(self.history) < 3:
            # Not enough data, follow market with slight uncertainty adjustment
            pred = current_price * 0.9 + 0.05  # Shrink toward 0.5
            return pred, "Insufficient history, following market with uncertainty shrinkage"

        # Calculate momentum
        recent = self.history[-self.lookback:]
        velocity = (recent[-1] - recent[0]) / len(recent)

        # Volatility
        diffs = [abs(recent[i] - recent[i-1]) for i in range(1, len(recent))]
        volatility = sum(diffs) / len(diffs) if diffs else 0

        # Trend strength
        trend_strength = abs(velocity) / max(volatility, 0.001)

        if trend_strength > 2.0:
            # Strong trend — follow it
            pred = current_price + velocity * 2
            reasoning = f"Strong trend detected (v={velocity:.3f}, σ={volatility:.3f}), extrapolating"
        elif current_price > 0.85 or current_price < 0.15:
            # Extreme price — slight mean reversion
            pred = current_price * 0.95 + 0.025
            reasoning = f"Extreme price ({current_price:.2f}), applying mean reversion"
        else:
            # Moderate — blend market with slight independent view
            pred = current_price * 0.85 + 0.5 * 0.15  # Slight shrinkage toward 0.5
            reasoning = f"Moderate regime (v={velocity:.3f}), market-following with uncertainty"

        # Clamp
        pred = max(0.01, min(0.99, pred))
        return pred, reasoning


def calculate_brier_score(predictions: List[float], outcome: float) -> float:
    """
    Brier Score = mean((prediction - outcome)^2)
    Lower is better. 0 = perfect, 1 = worst.
    """
    if not predictions:
        return 1.0
    return sum((p - outcome) ** 2 for p in predictions) / len(predictions)


def run_backtest(
    event_data: Dict,
    agent: Optional[SimpleAgent] = None,
) -> Optional[BacktestResult]:
    """
    Run a backtest on a single resolved event.

    Args:
        event_data: Enriched event data from fetcher (new format)
        agent: Prediction agent (default: SimpleAgent)

    Returns:
        BacktestResult or None if insufficient data
    """
    if agent is None:
        agent = SimpleAgent()
    agent.reset()

    market = event_data["market"]
    price_history = event_data.get("price_history", [])

    if len(price_history) < 10:
        return None

    ground_truth = market["ground_truth"]
    winner = market.get("winner", "N/A")

    # Run agent through time series
    snapshots = []
    agent_predictions = []
    market_prices = []

    for point in price_history:
        ts = point.get("t", 0)
        price = float(point.get("p", 0.5))

        market_prices.append(price)

        pred, reasoning = agent.predict(price, ts, {"question": market.get("question", "")})
        agent_predictions.append(pred)

        snapshots.append(PredictionSnapshot(
            timestamp=ts,
            market_price=price,
            agent_prediction=pred,
            info_available=f"Market price: {price:.3f}",
            reasoning=reasoning,
        ))

    # Calculate scores
    agent_brier = calculate_brier_score(agent_predictions, ground_truth)
    market_brier = calculate_brier_score(market_prices, ground_truth)

    return BacktestResult(
        market_id=str(market.get("id", "")),
        question=market.get("question", ""),
        ground_truth=ground_truth,
        outcome=winner,
        volume=float(market.get("volume", 0)),
        num_snapshots=len(snapshots),
        agent_brier_score=round(agent_brier, 4),
        market_brier_score=round(market_brier, 4),
        agent_beats_market=agent_brier < market_brier,
        snapshots=snapshots,
        final_agent_prediction=agent_predictions[-1] if agent_predictions else 0.5,
        final_market_price=market_prices[-1] if market_prices else 0.5,
    )


def run_full_backtest(
    dataset: List[Dict],
    agent: Optional[SimpleAgent] = None,
) -> Dict:
    """
    Run backtest across all markets in dataset.
    Returns summary with aggregate metrics.
    """
    if agent is None:
        agent = SimpleAgent()

    results = []
    for market_data in dataset:
        result = run_backtest(market_data, agent)
        if result:
            results.append(result)

    if not results:
        return {"error": "No valid results"}

    # Aggregate metrics
    avg_agent_brier = sum(r.agent_brier_score for r in results) / len(results)
    avg_market_brier = sum(r.market_brier_score for r in results) / len(results)
    wins = sum(1 for r in results if r.agent_beats_market)

    return {
        "summary": {
            "markets_tested": len(results),
            "agent_avg_brier": round(avg_agent_brier, 4),
            "market_avg_brier": round(avg_market_brier, 4),
            "agent_wins": wins,
            "market_wins": len(results) - wins,
            "win_rate": round(wins / len(results), 2),
            "improvement": round((avg_market_brier - avg_agent_brier) / max(avg_market_brier, 0.001), 4),
        },
        "results": [
            {
                "question": r.question[:60],
                "outcome": r.outcome,
                "volume": f"${r.volume:,.0f}",
                "snapshots": r.num_snapshots,
                "agent_brier": r.agent_brier_score,
                "market_brier": r.market_brier_score,
                "winner": "🤖 Agent" if r.agent_beats_market else "📊 Market",
            }
            for r in results
        ],
    }
