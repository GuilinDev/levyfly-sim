#!/usr/bin/env bash
# ============================================================
# LevyFly AutoTuning Loop
# Inspired by Karpathy's autoresearch
#
# Human writes strategy.md → Agent modifies evolvable_policy.py
# → Eval runs → Score improves? → Git commit → Repeat
#
# Usage: bash autotuning/run_loop.sh [rounds]
# ============================================================

set -e
cd "$(dirname "$0")/.."

ROUNDS=${1:-20}
BRANCH="autotuning-$(date +%Y%m%d-%H%M)"
BEST_SCORE_FILE="autotuning/results/best_score.txt"
LOG_FILE="autotuning/results/tuning_log.jsonl"

mkdir -p autotuning/results

# Create branch
git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"

# Get initial score
echo "🏁 Running initial evaluation..."
python3 -m autotuning.eval_policy > /tmp/eval_output.txt 2>&1
INITIAL_SCORE=$(python3 -c "import json; print(json.load(open('autotuning/results/latest.json'))['score'])")
echo "$INITIAL_SCORE" > "$BEST_SCORE_FILE"
echo "📊 Initial score: $INITIAL_SCORE"

for i in $(seq 1 "$ROUNDS"); do
    echo ""
    echo "============================================================"
    echo "🔄 ROUND $i / $ROUNDS"
    echo "============================================================"

    CURRENT_BEST=$(cat "$BEST_SCORE_FILE")

    # Let Claude Code modify the policy
    claude --permission-mode bypassPermissions --print "You are optimizing a supply chain inventory policy.

## Context
- Read autotuning/strategy.md for the objective
- Read autotuning/evolvable_policy.py — this is the ONLY file you modify
- Current best score: $CURRENT_BEST
- Score = fill_rate * 100 - stockouts * 0.5 - excess_ratio * 10
- The problem: we need high fill rate (>99.9%) but LOW excess inventory

## Current Results
$(cat autotuning/results/latest.json 2>/dev/null || echo 'No results yet')

## Your Task (Round $i)
1. Read evolvable_policy.py carefully
2. Make ONE targeted change to improve the score
3. Focus on reducing excess_ratio while maintaining fill_rate > 99.9%
4. Ideas: tighter reorder points, smaller order quantities, better demand estimation
5. Save the modified evolvable_policy.py

IMPORTANT: Make only ONE change per round. Small, testable changes.
Do NOT modify any other files. Only evolvable_policy.py." 2>/dev/null

    # Evaluate
    echo "📊 Evaluating round $i..."
    python3 -m autotuning.eval_policy > /tmp/eval_output.txt 2>&1
    cat /tmp/eval_output.txt

    NEW_SCORE=$(python3 -c "import json; print(json.load(open('autotuning/results/latest.json'))['score'])")
    RESULT=$(cat autotuning/results/latest.json)

    # Compare
    IMPROVED=$(python3 -c "print('yes' if $NEW_SCORE > $CURRENT_BEST else 'no')")

    if [ "$IMPROVED" = "yes" ]; then
        echo "✅ IMPROVED: $CURRENT_BEST → $NEW_SCORE (+$(python3 -c "print(round($NEW_SCORE - $CURRENT_BEST, 4))"))"
        echo "$NEW_SCORE" > "$BEST_SCORE_FILE"
        git add autotuning/evolvable_policy.py autotuning/results/
        git commit -m "autotuning round $i: score $CURRENT_BEST → $NEW_SCORE"
    else
        echo "❌ NO IMPROVEMENT: $NEW_SCORE <= $CURRENT_BEST — rolling back"
        git checkout -- autotuning/evolvable_policy.py
    fi

    # Log
    echo "{\"round\":$i,\"score\":$NEW_SCORE,\"improved\":\"$IMPROVED\",\"result\":$RESULT}" >> "$LOG_FILE"
done

echo ""
echo "============================================================"
echo "🏆 AUTOTUNING COMPLETE"
echo "  Rounds: $ROUNDS"
echo "  Best score: $(cat $BEST_SCORE_FILE)"
echo "  Log: $LOG_FILE"
echo "============================================================"

# Notify
openclaw system event --text "AutoTuning complete: $ROUNDS rounds, best score $(cat $BEST_SCORE_FILE)" --mode now 2>/dev/null || true
