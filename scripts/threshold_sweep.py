"""Sweep confidence thresholds for a drex -> llm hybrid escalation policy.

Reads results/benchmark_final_vs_opus55.json and, for each threshold,
simulates: use the llm answer when the drex confidence is below the
threshold, otherwise use the drex answer. Prints a markdown table with
the threshold, escalation rate, and hybrid accuracy.
"""

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "results" / "benchmark_final_vs_opus55.json"
THRESHOLDS = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def main():
    with open(DATA) as f:
        data = json.load(f)

    rows = data["rows"]
    drex = {r["case"]: r for r in rows if r["provider"] == "drex"}
    llm = {r["case"]: r for r in rows if r["provider"] == "llm"}

    cases = list(drex.keys())
    n = len(cases)
    if not n:
        raise SystemExit("no drex rows found")

    lines = ["| threshold | escalation rate | hybrid accuracy |",
             "|---|---|---|"]
    for t in THRESHOLDS:
        escalated = 0
        correct = 0
        for case in cases:
            conf = drex[case]["confidence"]
            if conf < t:
                escalated += 1
                used = llm[case]["correct"]
            else:
                used = drex[case]["correct"]
            if used:
                correct += 1
        lines.append(
            f"| {t:.1f} | {escalated / n:.3f} | {correct / n:.3f} |"
        )
    print("\n".join(lines))


if __name__ == "__main__":
    main()
