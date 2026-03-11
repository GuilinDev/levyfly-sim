#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fine-tune Chronos on Walmart M5 Demand Data

This script:
1. Loads M5 sales data and aggregates by dept per store (70 time series)
2. Splits: first 1400 days = train, last 500 days = test
3. Fine-tunes Chronos-2 (120M params) using the chronos training API
   - Also supports chronos-t5-small (46M) via fallback training loop
4. Saves the fine-tuned model to models/chronos-m5-finetuned/
5. Runs a quick forecast test on the test set

Note: Chronos-2 has native .fit() API for fine-tuning with LoRA support.
      Chronos T5 models require the custom training script approach.

Target: ~1-2 hours of training on CPU/GPU
"""
import os
import sys
import csv
import time
import torch
import numpy as np
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_m5_aggregated(data_path: str, max_days: int = 1913) -> Dict[str, np.ndarray]:
    """
    Load M5 data and aggregate by (store_id, dept_id).

    Returns:
        Dict mapping "store_dept" -> numpy array of daily sales
    """
    print(f"Loading M5 data from {data_path}...")

    sales_file = Path(data_path) / "sales_train_validation.csv"
    if not sales_file.exists():
        sales_file = Path(data_path) / "sales_train.csv"

    # Aggregate sales by store+dept+day
    aggregated = defaultdict(lambda: defaultdict(int))
    stores_set = set()
    depts_set = set()

    with open(sales_file, "r") as f:
        reader = csv.DictReader(f)
        row_count = 0

        for row in reader:
            store_id = row["store_id"]
            dept_id = row["dept_id"]
            key = f"{store_id}_{dept_id}"

            stores_set.add(store_id)
            depts_set.add(dept_id)

            # Read daily sales columns d_1 through d_{max_days}
            for d in range(1, max_days + 1):
                col = f"d_{d}"
                if col not in row:
                    break
                qty = int(row[col])
                aggregated[key][d] += qty

            row_count += 1
            if row_count % 5000 == 0:
                print(f"  Processed {row_count:,} rows...")

    print(f"  Total rows: {row_count:,}")
    print(f"  Stores: {len(stores_set)} - {sorted(stores_set)}")
    print(f"  Departments: {len(depts_set)} - {sorted(depts_set)}")
    print(f"  Time series: {len(aggregated)}")

    # Convert to numpy arrays
    result = {}
    actual_days = 0

    for key, daily_sales in aggregated.items():
        days = sorted(daily_sales.keys())
        actual_days = max(actual_days, max(days))
        # Create array with zeros for missing days
        arr = np.zeros(actual_days, dtype=np.float32)
        for d, qty in daily_sales.items():
            arr[d - 1] = qty  # d is 1-indexed
        result[key] = arr

    print(f"  Total days: {actual_days}")

    return result


def split_data(
    series_dict: Dict[str, np.ndarray],
    train_days: int = 1400,
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """
    Split time series into train (first train_days) and test (remaining).
    """
    train_data = {}
    test_data = {}

    for key, arr in series_dict.items():
        train_data[key] = arr[:train_days]
        test_data[key] = arr[train_days:]

    return train_data, test_data


def prepare_training_inputs(train_data: Dict[str, np.ndarray]) -> List[torch.Tensor]:
    """
    Prepare training inputs for Chronos fit() method.

    Returns list of tensors, one per time series.
    """
    inputs = []
    for key, arr in train_data.items():
        # Convert to tensor
        tensor = torch.tensor(arr, dtype=torch.float32)
        inputs.append(tensor)
    return inputs


def evaluate_forecasts(
    pipeline,
    test_data: Dict[str, np.ndarray],
    train_data: Dict[str, np.ndarray],
    prediction_length: int = 7,
    context_length: int = 512,
) -> Dict[str, float]:
    """
    Evaluate forecast quality on test set using rolling window.

    Computes MAE and RMSE across all series and forecast windows.
    """
    print("\nEvaluating forecasts on test set...")

    all_errors = []
    all_squared_errors = []

    series_keys = list(test_data.keys())

    for idx, key in enumerate(series_keys):
        test_arr = test_data[key]
        train_arr = train_data[key]

        # Use last context_length of train + test data as we slide
        full_series = np.concatenate([train_arr[-context_length:], test_arr])

        # Rolling forecast every 7 days
        n_forecasts = max(1, len(test_arr) // prediction_length - 1)

        for i in range(n_forecasts):
            # Context: from start up to current position
            ctx_end = context_length + i * prediction_length
            context = full_series[:ctx_end]

            # True future values
            true_future = full_series[ctx_end:ctx_end + prediction_length]
            if len(true_future) < prediction_length:
                continue

            # Predict
            ctx_tensor = torch.tensor([context[-context_length:]], dtype=torch.float32)
            with torch.no_grad():
                forecast = pipeline.predict(ctx_tensor, prediction_length=prediction_length)

            # Handle different forecast types (samples vs quantiles)
            if forecast.dim() == 3:
                # Chronos T5: (batch, num_samples, horizon) -> take median
                pred = torch.median(forecast, dim=1).values[0].numpy()
            elif forecast.dim() == 2:
                # Direct prediction
                pred = forecast[0].numpy()
            else:
                pred = forecast.numpy().flatten()[:prediction_length]

            # Compute errors
            errors = np.abs(pred - true_future)
            all_errors.extend(errors)
            all_squared_errors.extend((pred - true_future) ** 2)

        if (idx + 1) % 10 == 0:
            print(f"  Evaluated {idx + 1}/{len(series_keys)} series...")

    mae = np.mean(all_errors)
    rmse = np.sqrt(np.mean(all_squared_errors))

    return {"MAE": mae, "RMSE": rmse}


def main():
    """Main fine-tuning workflow."""
    print("=" * 60)
    print("Chronos Fine-tuning on Walmart M5 Data")
    print("=" * 60)

    # Configuration
    DATA_PATH = PROJECT_ROOT / "data" / "walmart_m5"
    MODEL_OUTPUT = PROJECT_ROOT / "models" / "chronos-m5-finetuned"

    TRAIN_DAYS = 1400
    PREDICTION_LENGTH = 7  # 7-day forecast horizon for supply chain
    BATCH_SIZE = 16
    NUM_STEPS = 1000
    LEARNING_RATE = 1e-5  # Recommended for LoRA
    FINETUNE_MODE = "lora"  # LoRA is more efficient for 70 series

    # Model selection:
    # - "chronos-2" (120M) - has native .fit() API, better for fine-tuning
    # - "chronos-t5-small" (46M) - original model, requires custom training
    MODEL_NAME = "amazon/chronos-2"  # Use Chronos-2 for fine-tuning API

    # Determine device
    if torch.cuda.is_available():
        device = "cuda"
        print(f"Using CUDA: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
        print("Using Apple MPS")
    else:
        device = "cpu"
        print("Using CPU")

    # Step 1: Load and aggregate M5 data
    print("\n" + "=" * 40)
    print("Step 1: Loading M5 Data")
    print("=" * 40)

    series_dict = load_m5_aggregated(str(DATA_PATH))

    # Step 2: Split data
    print("\n" + "=" * 40)
    print("Step 2: Splitting Data")
    print("=" * 40)

    train_data, test_data = split_data(series_dict, train_days=TRAIN_DAYS)
    print(f"Train: {TRAIN_DAYS} days")
    print(f"Test: {len(list(test_data.values())[0])} days")
    print(f"Number of time series: {len(train_data)}")

    # Verify expected 70 series (7 depts x 10 stores)
    if len(train_data) != 70:
        print(f"WARNING: Expected 70 time series, got {len(train_data)}")

    # Step 3: Prepare training inputs
    print("\n" + "=" * 40)
    print("Step 3: Preparing Training Data")
    print("=" * 40)

    train_inputs = prepare_training_inputs(train_data)
    print(f"Prepared {len(train_inputs)} time series tensors")
    print(f"Average series length: {np.mean([len(t) for t in train_inputs]):.0f}")
    print(f"Total training samples: {sum(len(t) for t in train_inputs):,}")

    # Step 4: Load pre-trained Chronos
    print("\n" + "=" * 40)
    print(f"Step 4: Loading Pre-trained {MODEL_NAME}")
    print("=" * 40)

    from chronos import BaseChronosPipeline

    pipeline = BaseChronosPipeline.from_pretrained(
        MODEL_NAME,
        device_map=device,
        dtype=torch.float32,
    )
    print(f"Loaded {MODEL_NAME}")
    print(f"Pipeline type: {type(pipeline).__name__}")

    # Step 5: Fine-tune
    print("\n" + "=" * 40)
    print("Step 5: Fine-tuning")
    print("=" * 40)
    print(f"  Mode: {FINETUNE_MODE}")
    print(f"  Steps: {NUM_STEPS}")
    print(f"  Batch size: {BATCH_SIZE}")
    print(f"  Learning rate: {LEARNING_RATE}")
    print(f"  Prediction length: {PREDICTION_LENGTH}")

    start_time = time.time()

    # Check if pipeline has fit method (Chronos 2.x API)
    if hasattr(pipeline, 'fit'):
        print("\nUsing Chronos 2 pipeline.fit() API...")

        # Prepare validation inputs
        val_inputs = prepare_training_inputs(test_data)

        try:
            finetuned_pipeline = pipeline.fit(
                inputs=train_inputs,
                prediction_length=PREDICTION_LENGTH,
                num_steps=NUM_STEPS,
                learning_rate=LEARNING_RATE,
                batch_size=BATCH_SIZE,
                finetune_mode=FINETUNE_MODE,
                validation_inputs=val_inputs[:10],  # Use subset for validation
                logging_steps=100,
            )
        except TypeError as e:
            # Fall back if some params not supported
            print(f"Adjusting parameters due to: {e}")
            try:
                finetuned_pipeline = pipeline.fit(
                    inputs=train_inputs,
                    prediction_length=PREDICTION_LENGTH,
                    num_steps=NUM_STEPS,
                    learning_rate=LEARNING_RATE,
                    batch_size=BATCH_SIZE,
                )
            except Exception as e2:
                print(f"fit() failed: {e2}")
                print("Falling back to manual training...")
                finetuned_pipeline = finetune_chronos_manual(
                    pipeline,
                    train_inputs,
                    PREDICTION_LENGTH,
                    NUM_STEPS,
                    BATCH_SIZE,
                    LEARNING_RATE,
                    device,
                )
    else:
        # Chronos T5: Use manual training loop
        print("\nChronos T5 model detected - using manual training loop...")
        finetuned_pipeline = finetune_chronos_manual(
            pipeline,
            train_inputs,
            PREDICTION_LENGTH,
            NUM_STEPS,
            BATCH_SIZE,
            LEARNING_RATE,
            device,
        )

    elapsed = time.time() - start_time
    print(f"\nFine-tuning completed in {elapsed / 60:.1f} minutes")

    # Step 6: Save model
    print("\n" + "=" * 40)
    print("Step 6: Saving Fine-tuned Model")
    print("=" * 40)

    MODEL_OUTPUT.mkdir(parents=True, exist_ok=True)

    if hasattr(finetuned_pipeline, 'save_pretrained'):
        finetuned_pipeline.save_pretrained(str(MODEL_OUTPUT))
        print(f"Model saved to {MODEL_OUTPUT}")
    else:
        # Save state dict manually
        model_path = MODEL_OUTPUT / "pytorch_model.bin"
        torch.save(finetuned_pipeline.model.state_dict(), str(model_path))
        print(f"Model state dict saved to {model_path}")

    # Step 7: Evaluate
    print("\n" + "=" * 40)
    print("Step 7: Evaluating on Test Set")
    print("=" * 40)

    metrics = evaluate_forecasts(
        finetuned_pipeline,
        test_data,
        train_data,
        prediction_length=PREDICTION_LENGTH,
    )

    print("\n" + "-" * 40)
    print("Final Metrics:")
    print(f"  MAE:  {metrics['MAE']:.2f}")
    print(f"  RMSE: {metrics['RMSE']:.2f}")
    print("-" * 40)

    # Quick comparison with zero-shot
    print("\n" + "=" * 40)
    print("Comparison: Zero-shot vs Fine-tuned")
    print("=" * 40)

    print("Running zero-shot evaluation for comparison...")
    zero_shot_pipeline = BaseChronosPipeline.from_pretrained(
        MODEL_NAME,
        device_map=device,
        dtype=torch.float32,
    )

    zs_metrics = evaluate_forecasts(
        zero_shot_pipeline,
        test_data,
        train_data,
        prediction_length=PREDICTION_LENGTH,
    )

    print("\n" + "-" * 40)
    print("                   Zero-Shot    Fine-tuned    Improvement")
    print("-" * 40)
    mae_imp = (zs_metrics['MAE'] - metrics['MAE']) / zs_metrics['MAE'] * 100
    rmse_imp = (zs_metrics['RMSE'] - metrics['RMSE']) / zs_metrics['RMSE'] * 100
    print(f"  MAE:       {zs_metrics['MAE']:8.2f}     {metrics['MAE']:8.2f}       {mae_imp:+.1f}%")
    print(f"  RMSE:      {zs_metrics['RMSE']:8.2f}     {metrics['RMSE']:8.2f}       {rmse_imp:+.1f}%")
    print("-" * 40)

    print("\nDone!")
    print(f"Fine-tuned model saved at: {MODEL_OUTPUT}")

    return metrics


def finetune_chronos_manual(
    pipeline,
    train_inputs: List[torch.Tensor],
    prediction_length: int,
    num_steps: int,
    batch_size: int,
    learning_rate: float,
    device: str,
):
    """
    Fallback fine-tuning for Chronos 1.x using manual training loop.

    This implements a simple fine-tuning approach when the .fit() API
    is not available.
    """
    from torch.optim import AdamW
    from torch.utils.data import DataLoader, Dataset
    import random

    class TimeSeriesDataset(Dataset):
        def __init__(self, series_list, context_length=512, pred_len=7):
            self.samples = []
            for series in series_list:
                n = len(series)
                if n > context_length + pred_len:
                    # Create samples from different positions
                    for start in range(0, n - context_length - pred_len, pred_len):
                        ctx = series[start:start + context_length]
                        target = series[start + context_length:start + context_length + pred_len]
                        self.samples.append((ctx, target))

        def __len__(self):
            return len(self.samples)

        def __getitem__(self, idx):
            ctx, target = self.samples[idx]
            return ctx.clone(), target.clone()

    print("Creating training dataset...")
    dataset = TimeSeriesDataset(train_inputs, context_length=512, pred_len=prediction_length)
    print(f"Created {len(dataset)} training samples")

    if len(dataset) == 0:
        print("WARNING: No training samples could be created. Series may be too short.")
        return pipeline

    # Get the underlying model
    model = pipeline.model
    model.train()

    # Setup optimizer
    optimizer = AdamW(model.parameters(), lr=learning_rate)

    # Training loop
    print(f"\nStarting training for {num_steps} steps...")

    step = 0
    epoch = 0
    losses = []

    while step < num_steps:
        epoch += 1
        indices = list(range(len(dataset)))
        random.shuffle(indices)

        for i in range(0, len(indices), batch_size):
            if step >= num_steps:
                break

            batch_indices = indices[i:i + batch_size]
            batch_ctx = []
            batch_target = []

            for idx in batch_indices:
                ctx, target = dataset[idx]
                batch_ctx.append(ctx)
                batch_target.append(target)

            # Stack batch
            ctx_batch = torch.stack(batch_ctx).to(device)
            target_batch = torch.stack(batch_target).to(device)

            # Forward pass - predict and compute loss
            optimizer.zero_grad()

            # Use model's forward for training
            try:
                # Try to use the model's built-in loss computation
                outputs = model(ctx_batch, target_batch)
                if hasattr(outputs, 'loss'):
                    loss = outputs.loss
                else:
                    # Compute MSE loss on predictions
                    with torch.no_grad():
                        forecast = pipeline.predict(ctx_batch, prediction_length=prediction_length)
                    pred = torch.median(forecast, dim=1).values
                    loss = torch.nn.functional.mse_loss(pred, target_batch)
            except Exception as e:
                # Simple MSE loss fallback
                forecast = pipeline.predict(ctx_batch, prediction_length=prediction_length)
                pred = torch.median(forecast, dim=1).values
                loss = torch.nn.functional.mse_loss(pred, target_batch)

            loss.backward()
            optimizer.step()

            losses.append(loss.item())
            step += 1

            if step % 100 == 0:
                avg_loss = np.mean(losses[-100:])
                print(f"  Step {step}/{num_steps}, Loss: {avg_loss:.4f}")

    print(f"Training complete. Final avg loss: {np.mean(losses[-100:]):.4f}")

    model.eval()
    return pipeline


if __name__ == "__main__":
    main()
