#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Time Series Forecast Models for Supply Chain AI Agent

Wraps pre-trained foundation models (Chronos, etc.) into a simple
predict(history, horizon) interface that inventory policies can use.
"""
import torch
import numpy as np
from typing import List, Optional


class ChronosForecastModel:
    """
    Amazon Chronos — pre-trained time series foundation model.
    No fine-tuning needed for initial demo; zero-shot forecasting.
    """

    def __init__(self, model_size: str = "tiny", device: str = "cpu"):
        """
        Args:
            model_size: tiny (8M), mini (20M), small (46M), base (200M), large (710M)
            device: cpu or cuda
        """
        from chronos import ChronosPipeline

        model_id = f"amazon/chronos-t5-{model_size}"
        print(f"  📦 Loading Chronos ({model_size})...")
        self.pipeline = ChronosPipeline.from_pretrained(
            model_id,
            device_map=device,
            torch_dtype=torch.float32,
        )
        self.name = f"chronos-{model_size}"
        print(f"  ✅ Chronos {model_size} loaded")

    def predict(self, history: List[float], horizon: int = 7) -> List[float]:
        """
        Predict future values given history.

        Args:
            history: Past demand values
            horizon: How many steps to predict

        Returns:
            List of predicted values
        """
        if len(history) < 3:
            # Not enough history, return mean
            avg = sum(history) / max(1, len(history)) if history else 10
            return [avg] * horizon

        context = torch.tensor([history], dtype=torch.float32)
        forecast = self.pipeline.predict(context, prediction_length=horizon)
        # forecast shape: (1, num_samples, horizon) — take median
        median_forecast = torch.median(forecast, dim=1).values[0].tolist()

        # Clamp to non-negative
        return [max(0, v) for v in median_forecast]


class NaiveForecastModel:
    """Simple baseline: predict last week's pattern will repeat."""

    def __init__(self):
        self.name = "naive-repeat"

    def predict(self, history: List[float], horizon: int = 7) -> List[float]:
        if len(history) < horizon:
            avg = sum(history) / max(1, len(history)) if history else 10
            return [avg] * horizon
        return history[-horizon:]


class MovingAvgForecastModel:
    """Moving average baseline."""

    def __init__(self, window: int = 14):
        self.window = window
        self.name = f"moving-avg-{window}"

    def predict(self, history: List[float], horizon: int = 7) -> List[float]:
        if not history:
            return [10] * horizon
        recent = history[-self.window:]
        avg = sum(recent) / len(recent)
        return [avg] * horizon


if __name__ == "__main__":
    # Quick test
    print("Testing forecast models...")

    history = [10, 12, 15, 11, 13, 18, 20, 14, 12, 16, 19, 22, 15, 13]

    # Test naive
    naive = NaiveForecastModel()
    print(f"Naive: {naive.predict(history, 7)}")

    # Test moving avg
    ma = MovingAvgForecastModel()
    print(f"MA-14: {ma.predict(history, 7)}")

    # Test Chronos
    try:
        chronos = ChronosForecastModel("tiny", device="cpu")
        pred = chronos.predict(history, 7)
        print(f"Chronos: {[f'{v:.1f}' for v in pred]}")
    except Exception as e:
        print(f"Chronos failed: {e}")
