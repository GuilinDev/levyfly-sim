#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polymarket Data Fetcher
Pulls resolved events with price history from Gamma API + CLOB API.
No API key needed for read-only access.
"""
import httpx
import json
import os
import time
from typing import List, Dict, Optional
from datetime import datetime


GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"


class PolymarketFetcher:
    """Fetches market data from Polymarket's public APIs."""

    def __init__(self, cache_dir: str = "validation/polymarket/cache"):
        self.gamma_url = GAMMA_URL
        self.clob_url = CLOB_URL
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.client = httpx.Client(timeout=30.0)

    def get_resolved_events(self, limit: int = 20, offset: int = 0) -> List[Dict]:
        """Fetch high-volume resolved events."""
        params = {
            "closed": True,
            "limit": limit,
            "offset": offset,
            "order": "volume",
            "ascending": False,
        }
        response = self.client.get(f"{self.gamma_url}/events", params=params)
        response.raise_for_status()
        return response.json()

    def get_price_history(self, token_id: str, fidelity: int = 1440) -> List[Dict]:
        """
        Fetch price history for a CLOB token.

        Args:
            token_id: The CLOB token ID
            fidelity: Minutes per point (1440=daily, 60=hourly)
        """
        params = {
            "market": token_id,
            "interval": "max",
            "fidelity": fidelity,
        }
        response = self.client.get(f"{self.clob_url}/prices-history", params=params)
        response.raise_for_status()
        return response.json().get("history", [])

    def _resolve_outcome(self, market: Dict) -> Dict:
        """Determine the winning outcome from outcomePrices."""
        outcome_prices = market.get("outcomePrices", "[]")
        if isinstance(outcome_prices, str):
            outcome_prices = json.loads(outcome_prices)

        outcomes = market.get("outcomes", "[]")
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)

        winner = None
        winner_idx = None
        for i, p in enumerate(outcome_prices):
            if float(p) == 1.0 and i < len(outcomes):
                winner = outcomes[i]
                winner_idx = i
                break

        return {
            "winner": winner,
            "winner_idx": winner_idx,
            "outcomes": outcomes,
            "outcome_prices": [float(p) for p in outcome_prices],
        }

    def fetch_event_data(self, event: Dict) -> Optional[Dict]:
        """
        Fetch complete data for an event: pick the primary YES/NO market,
        get price history, determine ground truth.
        """
        markets = event.get("markets", [])
        if not markets:
            return None

        # For multi-market events (like "Who wins X?"), find the winning market
        # For binary events, just use the first market
        best_market = None
        best_volume = 0

        for m in markets:
            resolution = self._resolve_outcome(m)
            vol = float(m.get("volume", 0))

            # Prefer binary YES/NO markets with a clear winner
            if resolution["winner"] is not None and vol > best_volume:
                best_market = m
                best_volume = vol

        if not best_market:
            # Fallback: first market
            best_market = markets[0]

        resolution = self._resolve_outcome(best_market)

        # Get CLOB token IDs
        clob_ids = best_market.get("clobTokenIds", "[]")
        if isinstance(clob_ids, str):
            clob_ids = json.loads(clob_ids)

        if not clob_ids:
            return None

        # Get price history for the first outcome (typically "Yes" or the named outcome)
        cache_key = f"event_{event.get('id', 'unknown')}"
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.json")

        if os.path.exists(cache_path):
            with open(cache_path, "r") as f:
                return json.load(f)

        # Fetch price history
        price_history = []
        try:
            price_history = self.get_price_history(clob_ids[0], fidelity=1440)
            time.sleep(0.5)
        except Exception as e:
            print(f"  ⚠️ Price history failed: {e}")

        # Determine ground truth for first outcome
        # If outcomePrices[0] == 1.0, first outcome won
        ground_truth = resolution["outcome_prices"][0] if resolution["outcome_prices"] else 0.5

        enriched = {
            "event": {
                "id": event.get("id"),
                "title": event.get("title", ""),
                "volume": float(event.get("volume", 0)),
            },
            "market": {
                "id": best_market.get("id"),
                "question": best_market.get("question", ""),
                "outcomes": resolution["outcomes"],
                "winner": resolution["winner"],
                "ground_truth": ground_truth,  # 1.0 if first outcome won, 0.0 if not
                "volume": float(best_market.get("volume", 0)),
            },
            "price_history": price_history,
            "fetched_at": datetime.now().isoformat(),
        }

        # Cache
        with open(cache_path, "w") as f:
            json.dump(enriched, f, indent=2)

        return enriched

    def fetch_resolved_dataset(self, count: int = 10) -> List[Dict]:
        """
        Build a dataset of resolved events with price histories.
        Filters for events that have usable price history.
        """
        print(f"📡 Fetching resolved events from Polymarket...")

        # Fetch more than needed since some won't have price history
        events = self.get_resolved_events(limit=count * 3)

        dataset = []
        for i, event in enumerate(events):
            if len(dataset) >= count:
                break

            title = event.get("title", "N/A")
            volume = float(event.get("volume", 0))

            print(f"\n  [{len(dataset)+1}/{count}] {title[:60]}...")
            print(f"    Volume: ${volume:,.0f}")

            enriched = self.fetch_event_data(event)
            if enriched and len(enriched.get("price_history", [])) >= 10:
                winner = enriched["market"]["winner"]
                pts = len(enriched["price_history"])
                print(f"    ✅ Winner: {winner} | {pts} price points")
                dataset.append(enriched)
            else:
                pts = len(enriched["price_history"]) if enriched else 0
                print(f"    ⏭️ Skipped (only {pts} price points)")

            time.sleep(0.3)

        print(f"\n✅ Fetched {len(dataset)} events with usable price history")
        return dataset


if __name__ == "__main__":
    fetcher = PolymarketFetcher()
    dataset = fetcher.fetch_resolved_dataset(count=5)

    for d in dataset:
        m = d["market"]
        ph = d["price_history"]
        print(f"\n📊 {m['question'][:60]}")
        print(f"   Winner: {m['winner']} | Ground truth: {m['ground_truth']}")
        print(f"   Price points: {len(ph)}")
        if ph:
            print(f"   Price range: {ph[0]['p']} → {ph[-1]['p']}")
