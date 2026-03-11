# LevyFly AutoTuning Strategy

## Objective
Find an inventory policy that BEATS the industry-standard (s,S) policy
on Walmart M5 real demand data.

## Target Metrics
- PRIMARY: fill_rate > 0.999 (must beat (s,S) baseline of 99.9%)
- SECONDARY: fewer stockouts than (s,S) baseline (4 stockouts)
- TERTIARY: lower total inventory cost (fewer excess units held)

## Scoring Function
score = fill_rate * 100 - stockouts * 0.5 - excess_ratio * 10

Higher is better. (s,S) baseline score ≈ 97.9

## Constraints
- DO NOT modify demand data or network topology
- DO NOT assume lead time < 1 day
- All changes must be in the policy logic only
- Each experiment runs 90 days on M5 real data

## What You Can Change
- Reorder point calculation (fixed, adaptive, forecast-based)
- Order quantity formula
- Safety stock calculation
- When to trigger emergency vs normal reorder
- How to use demand history (window size, weighting)
- Disruption detection and response
- Any combination of the above

## Evaluation
- Run 90-day simulation on M5 data
- Compare fill_rate, stockouts, and total_reorders against (s,S) baseline
- Only COMMIT if score improves over previous best
