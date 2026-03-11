#!/usr/bin/env python3
"""Fine-grained parameter search around current evolved policy."""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

import autotuning.evolvable_policy as ep
from autotuning.eval_policy import evaluate

print("Current baseline:")
r = evaluate(days=90, verbose=False)
print(f"  score={r['score']:.2f} fill={r['fill_rate']:.1%} so={r['stockouts']} ex={r['excess_ratio']:.0%}")
print(f"  SF={ep.SAFETY_FACTOR} OH={ep.ORDER_HORIZON} OB={ep.ORDER_BUFFER} EM={ep.EMERGENCY_MULTIPLIER} ET={ep.EMERGENCY_THRESHOLD}\n")

best = r['score']
best_cfg = "current"

tests = [
    ("SF=1.05", "SAFETY_FACTOR", 1.05),
    ("SF=1.08", "SAFETY_FACTOR", 1.08),
    ("SF=1.12", "SAFETY_FACTOR", 1.12),
    ("SF=1.15", "SAFETY_FACTOR", 1.15),
    ("OH=9", "ORDER_HORIZON", 9),
    ("OH=11", "ORDER_HORIZON", 11),
    ("OB=0.88", "ORDER_BUFFER", 0.88),
    ("OB=0.92", "ORDER_BUFFER", 0.92),
    ("OB=0.95", "ORDER_BUFFER", 0.95),
    ("EM=1.3", "EMERGENCY_MULTIPLIER", 1.3),
    ("EM=1.4", "EMERGENCY_MULTIPLIER", 1.4),
    ("EM=1.7", "EMERGENCY_MULTIPLIER", 1.7),
    ("ET=0.4", "EMERGENCY_THRESHOLD", 0.4),
    ("ET=0.6", "EMERGENCY_THRESHOLD", 0.6),
]

for label, key, val in tests:
    orig = getattr(ep, key)
    setattr(ep, key, val)
    try:
        r = evaluate(days=90, verbose=False)
        star = " ⭐" if r['score'] > best else ""
        print(f"  {label}: score={r['score']:.2f} fill={r['fill_rate']:.1%} so={r['stockouts']} ex={r['excess_ratio']:.0%}{star}")
        if r['score'] > best:
            best = r['score']
            best_cfg = label
    except Exception as e:
        print(f"  {label}: ERROR {e}")
    setattr(ep, key, orig)

print(f"\n🏆 Best: {best_cfg} → score={best:.2f}")
