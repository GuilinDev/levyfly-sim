#!/usr/bin/env python3
"""
Code Evolution Loop — AI agent evolves supply chain strategy code.

Inspired by Karpathy's autoresearch: human writes objectives (strategy.md),
AI modifies code (evolvable_policy.py), evaluator scores it, best version wins.

Unlike grid search (fixed algorithm, enumerate parameters), code evolution
lets the AI invent NEW algorithmic logic — strategies humans haven't tried.

Loop:
  1. Read strategy.md (human objectives)
  2. Read evolvable_policy.py (current best code)
  3. Read score history (what's been tried)
  4. LLM proposes code modification + hypothesis
  5. Write modified code → evaluate → score
  6. If score improves → commit + log
  7. If score worsens → rollback
  8. Repeat

Usage:
  python autotuning/evolve.py --rounds 5
  python autotuning/evolve.py --rounds 10 --model deepseek-r1:32b
"""
import os
import sys
import json
import shutil
import subprocess
import time
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STRATEGY_PATH = PROJECT_ROOT / "autotuning" / "strategy.md"
POLICY_PATH = PROJECT_ROOT / "autotuning" / "evolvable_policy.py"
BACKUP_PATH = PROJECT_ROOT / "autotuning" / "evolvable_policy.py.backup"
RESULTS_DIR = PROJECT_ROOT / "autotuning" / "results"
EVOLUTION_LOG = RESULTS_DIR / "evolution_log.json"


def read_file(path: Path) -> str:
    with open(path, "r") as f:
        return f.read()


def write_file(path: Path, content: str):
    with open(path, "w") as f:
        f.write(content)


def call_ollama(prompt: str, model: str = "mistral-small3.2:24b",
                max_tokens: int = 4000, temperature: float = 0.7) -> str:
    """Call local LLM via Ollama HTTP API."""
    import urllib.request
    import urllib.error

    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=300) as response:
        data = json.loads(response.read().decode("utf-8"))
        return data.get("response", "").strip()


def evaluate_policy() -> dict:
    """Run evaluation and return score dict."""
    from autotuning.eval_policy import evaluate
    import importlib
    import autotuning.evolvable_policy as ep
    importlib.reload(ep)
    return evaluate(days=90, verbose=False)


def extract_code_from_response(response: str) -> str:
    """Extract Python code from LLM response."""
    # Look for code blocks
    if "```python" in response:
        parts = response.split("```python")
        if len(parts) > 1:
            code = parts[1].split("```")[0]
            return code.strip()
    elif "```" in response:
        parts = response.split("```")
        if len(parts) > 2:
            code = parts[1]
            # Remove language tag if present
            if code.startswith("py\n") or code.startswith("python\n"):
                code = code.split("\n", 1)[1]
            return code.strip()
    
    # If no code block, look for the full file content
    # (sometimes LLM returns the whole file without code blocks)
    if "class EvolvablePolicy:" in response:
        # Find the start of the Python code
        lines = response.split("\n")
        code_lines = []
        in_code = False
        for line in lines:
            if line.startswith("#!/") or line.startswith("import ") or line.startswith("from ") or line.startswith("#") or line.startswith("\"\"\""):
                in_code = True
            if in_code:
                code_lines.append(line)
        if code_lines:
            return "\n".join(code_lines)
    
    return ""


def validate_code(code: str) -> bool:
    """Basic validation that the code is syntactically valid Python."""
    try:
        compile(code, "<evolved_policy>", "exec")
        return True
    except SyntaxError as e:
        print(f"    ❌ Syntax error: {e}")
        return False


def build_evolution_prompt(strategy: str, current_code: str, 
                            history: list, round_num: int) -> str:
    """Build the prompt for the LLM to propose code changes."""
    
    # Format history
    history_str = ""
    if history:
        history_str = "\n## Previous Attempts\n"
        for h in history[-5:]:  # Last 5 attempts
            status = "✅ IMPROVED" if h.get("improved") else "❌ WORSE"
            history_str += (
                f"- Round {h['round']}: {status} | "
                f"Score: {h['score']:.2f} | "
                f"Hypothesis: {h.get('hypothesis', 'N/A')}\n"
            )
    
    return f"""You are an AI researcher evolving a supply chain inventory policy.
Your goal: modify the Python code to achieve a HIGHER score.

## Strategy (Human-Defined Objectives)
{strategy}

## Current Best Code (score = {history[-1]['score'] if history else 'unknown'})
```python
{current_code}
```
{history_str}

## Your Task

1. ANALYZE the current code and identify what could be improved
2. HYPOTHESIZE a specific change that could improve the score
3. IMPLEMENT the change by rewriting the COMPLETE file

Rules:
- You MUST output the COMPLETE evolvable_policy.py file
- Keep the same class name (EvolvablePolicy) and interface (should_reorder method)
- You can change ANYTHING: parameters, logic, algorithms, add new methods
- Think creatively: try ideas humans might not consider
- The scoring function penalizes excess inventory heavily (×10)
- Previous grid search found optimal params: SF=1.2, OH=10, OB=0.9
- If params are already optimal, try STRUCTURAL changes to the algorithm

Ideas to explore:
- Momentum-based reorder (if demand rising 3 days straight, preemptively order)
- Inventory velocity (rate of consumption, not just level)
- Day-of-week patterns (weekends have different demand)
- Per-product learning (different products need different strategies)
- Cooldown after reorder (don't over-order by waiting for shipments)
- Adaptive thresholds (tighten/loosen based on recent volatility)

## Output Format

First, state your hypothesis in one line:
HYPOTHESIS: [what you're changing and why]

Then output the complete code:
```python
[complete evolvable_policy.py]
```
"""


def run_evolution(rounds: int = 5, model: str = "mistral-small3.2:24b"):
    """Run the evolution loop."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing log
    history = []
    if EVOLUTION_LOG.exists():
        with open(EVOLUTION_LOG) as f:
            history = json.load(f)

    # Evaluate current baseline
    print("=" * 70)
    print(f"🧬 CODE EVOLUTION LOOP — {rounds} rounds")
    print(f"   Model: {model}")
    print("=" * 70)

    print("\n📊 Evaluating current baseline...")
    try:
        baseline = evaluate_policy()
        best_score = baseline["score"]
        print(f"   Baseline score: {best_score:.2f} "
              f"(fill={baseline['fill_rate']:.1%}, stockouts={baseline['stockouts']}, "
              f"excess={baseline['excess_ratio']:.0%})")
    except Exception as e:
        print(f"   ❌ Baseline evaluation failed: {e}")
        return

    # Add baseline to history if empty
    if not history:
        history.append({
            "round": 0,
            "score": best_score,
            "fill_rate": baseline["fill_rate"],
            "stockouts": baseline["stockouts"],
            "excess_ratio": baseline["excess_ratio"],
            "hypothesis": "Grid search optimal (baseline)",
            "improved": True,
            "timestamp": datetime.now().isoformat(),
        })

    # Backup current best
    shutil.copy(POLICY_PATH, BACKUP_PATH)

    strategy = read_file(STRATEGY_PATH)
    improvements = 0

    for round_num in range(1, rounds + 1):
        print(f"\n{'─' * 60}")
        print(f"🔄 Round {round_num}/{rounds}")
        print(f"{'─' * 60}")

        current_code = read_file(POLICY_PATH)

        # 1. Ask LLM to propose modification
        print("   🧠 Asking LLM for code modification...")
        t0 = time.time()
        
        prompt = build_evolution_prompt(strategy, current_code, history, round_num)
        
        try:
            response = call_ollama(prompt, model=model, temperature=0.7 + round_num * 0.05)
        except Exception as e:
            print(f"   ❌ LLM call failed: {e}")
            continue
        
        llm_time = time.time() - t0
        print(f"   ⏱️  LLM responded in {llm_time:.1f}s")

        # 2. Extract hypothesis
        hypothesis = "unknown"
        for line in response.split("\n"):
            if line.strip().startswith("HYPOTHESIS:"):
                hypothesis = line.strip()[11:].strip()
                break
        print(f"   💡 Hypothesis: {hypothesis[:80]}")

        # 3. Extract and validate code
        new_code = extract_code_from_response(response)
        if not new_code:
            print("   ❌ No valid code extracted from response")
            history.append({
                "round": len(history),
                "score": best_score,
                "hypothesis": hypothesis,
                "improved": False,
                "error": "no_code_extracted",
                "timestamp": datetime.now().isoformat(),
            })
            continue

        if not validate_code(new_code):
            print("   ❌ Code has syntax errors, skipping")
            history.append({
                "round": len(history),
                "score": best_score,
                "hypothesis": hypothesis,
                "improved": False,
                "error": "syntax_error",
                "timestamp": datetime.now().isoformat(),
            })
            continue

        # 4. Write new code and evaluate
        write_file(POLICY_PATH, new_code)
        print("   📝 New code written, evaluating...")

        t0 = time.time()
        try:
            result = evaluate_policy()
            eval_time = time.time() - t0
            new_score = result["score"]
            
            print(f"   📊 Score: {new_score:.2f} "
                  f"(fill={result['fill_rate']:.1%}, stockouts={result['stockouts']}, "
                  f"excess={result['excess_ratio']:.0%}) [{eval_time:.1f}s]")

        except Exception as e:
            print(f"   ❌ Evaluation failed: {e}")
            # Rollback
            shutil.copy(BACKUP_PATH, POLICY_PATH)
            history.append({
                "round": len(history),
                "score": best_score,
                "hypothesis": hypothesis,
                "improved": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
            continue

        # 5. Compare and decide
        delta = new_score - best_score
        if new_score > best_score:
            print(f"   ✅ IMPROVED by {delta:+.2f} points!")
            best_score = new_score
            shutil.copy(POLICY_PATH, BACKUP_PATH)  # Update backup
            improvements += 1

            # Git commit
            try:
                subprocess.run(
                    ["git", "add", "autotuning/evolvable_policy.py"],
                    cwd=str(PROJECT_ROOT), capture_output=True, timeout=10
                )
                subprocess.run(
                    ["git", "commit", "-m",
                     f"evolve: score {new_score:.2f} (+{delta:.2f}) — {hypothesis[:60]}"],
                    cwd=str(PROJECT_ROOT), capture_output=True, timeout=10
                )
                print(f"   📦 Committed to git")
            except Exception:
                pass

            history.append({
                "round": len(history),
                "score": new_score,
                "fill_rate": result["fill_rate"],
                "stockouts": result["stockouts"],
                "excess_ratio": result["excess_ratio"],
                "hypothesis": hypothesis,
                "improved": True,
                "delta": delta,
                "timestamp": datetime.now().isoformat(),
            })
        else:
            print(f"   ❌ WORSE by {delta:.2f} points, rolling back")
            shutil.copy(BACKUP_PATH, POLICY_PATH)
            
            history.append({
                "round": len(history),
                "score": new_score,
                "fill_rate": result.get("fill_rate", 0),
                "stockouts": result.get("stockouts", 0),
                "excess_ratio": result.get("excess_ratio", 0),
                "hypothesis": hypothesis,
                "improved": False,
                "delta": delta,
                "timestamp": datetime.now().isoformat(),
            })

        # Save log after each round
        with open(EVOLUTION_LOG, "w") as f:
            json.dump(history, f, indent=2, default=str)

    # Summary
    print(f"\n{'=' * 70}")
    print(f"🧬 EVOLUTION COMPLETE — {rounds} rounds")
    print(f"{'=' * 70}")
    print(f"   Improvements: {improvements}/{rounds}")
    print(f"   Starting score: {history[0]['score']:.2f}")
    print(f"   Final score:    {best_score:.2f}")
    if history[0]["score"] > 0:
        total_gain = ((best_score - history[0]["score"]) / abs(history[0]["score"])) * 100
        print(f"   Total gain:     {total_gain:+.1f}%")

    print(f"\n📋 Evolution History:")
    for h in history:
        status = "✅" if h.get("improved") else "❌"
        print(f"   {status} Round {h['round']}: score={h['score']:.2f} — {h.get('hypothesis', '')[:60]}")

    print(f"\n📁 Log saved to: {EVOLUTION_LOG}")
    
    # Cleanup backup
    if BACKUP_PATH.exists():
        os.remove(BACKUP_PATH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="🧬 Code Evolution Loop")
    parser.add_argument("--rounds", type=int, default=5, help="Number of evolution rounds")
    parser.add_argument("--model", type=str, default="mistral-small3.2:24b",
                        help="Ollama model to use")
    args = parser.parse_args()
    
    run_evolution(rounds=args.rounds, model=args.model)
