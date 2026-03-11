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
    Amazon Chronos T5 — pre-trained time series foundation model.
    Zero-shot forecasting.
    """

    def __init__(self, model_size: str = "tiny", device: str = "cpu"):
        from chronos import ChronosPipeline

        model_id = f"amazon/chronos-t5-{model_size}"
        print(f"  📦 Loading Chronos T5 ({model_size})...")
        self.pipeline = ChronosPipeline.from_pretrained(
            model_id,
            device_map=device,
            torch_dtype=torch.float32,
        )
        self.name = f"chronos-{model_size}"
        print(f"  ✅ Chronos {model_size} loaded")

    def predict(self, history: List[float], horizon: int = 7) -> List[float]:
        if len(history) < 3:
            avg = sum(history) / max(1, len(history)) if history else 10
            return [avg] * horizon

        context = torch.tensor([history], dtype=torch.float32)
        forecast = self.pipeline.predict(context, prediction_length=horizon)
        median_forecast = torch.median(forecast, dim=1).values[0].tolist()
        return [max(0, v) for v in median_forecast]


class Chronos2ForecastModel:
    """
    Chronos-2 — fine-tuned on domain data. Returns quantile forecasts.
    """

    def __init__(self, model_path: str = "models/chronos-m5-finetuned", device: str = "cpu"):
        from chronos import Chronos2Pipeline

        print(f"  📦 Loading Chronos-2 from {model_path}...")
        self.pipeline = Chronos2Pipeline.from_pretrained(
            model_path,
            device_map=device,
            dtype=torch.float32,
        )
        self.name = "chronos2-m5-finetuned"
        print(f"  ✅ Chronos-2 loaded")

    def predict(self, history: List[float], horizon: int = 7) -> List[float]:
        if len(history) < 3:
            avg = sum(history) / max(1, len(history)) if history else 10
            return [avg] * horizon

        context = torch.tensor([[history]], dtype=torch.float32)  # (1, 1, T)
        forecast = self.pipeline.predict(context, prediction_length=horizon)
        # forecast[0] shape: (1, n_quantiles, horizon)
        quantiles = forecast[0][0]  # (n_quantiles, horizon)
        median = quantiles[quantiles.shape[0] // 2].tolist()
        return [max(0, v) for v in median]


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
