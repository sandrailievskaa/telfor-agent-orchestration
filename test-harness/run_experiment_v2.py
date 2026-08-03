"""ПРИВРЕМЕН контролиран експеримент - придружник на
langgraph-poc/experiment_policy_v2.py. Пушта 10x на `guaranteed_safe`
intent-от со изменетиот policy_checker промпт (v2) и append-ува во истиот
results/experiment_results.csv со platform="langgraph_prompt_v2", за да се
разликува од оригиналната ("langgraph") серија при анализа. Не ги пресоздава
редовите на оригиналната верзија - run_experiment.py не е менуван.

Избриши го овој фајл заедно со experiment_policy_v2.py штом наодот е
документиран во dev_notes.md.
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "langgraph-poc"))
sys.path.append(str(Path(__file__).resolve().parent.parent))
import experiment_policy_v2 as v2

from run_experiment import TEST_INTENTS, N_RUNS, OUTPUT_PATH, CSV_FIELDS, _failed_at_step
import csv

PLATFORM = "langgraph_prompt_v2"


def run_once_v2(intent_id: str, raw_request: str, run_number: int) -> dict:
    start = time.perf_counter()
    try:
        state = v2.run_pipeline_v2(raw_request, approve_callback=lambda: True)
        duration = time.perf_counter() - start
        guardrail_log = state.get("guardrail_log", [])
        outcome = state.get("status", "unknown")
        return {
            "platform": PLATFORM,
            "intent_id": intent_id,
            "run": run_number,
            "outcome": outcome,
            "failed_at_step": _failed_at_step(outcome, guardrail_log),
            "guardrail_catches": sum(1 for e in guardrail_log if not e.get("passed", True)),
            "duration_sec": round(duration, 2),
        }
    except Exception as e:
        duration = time.perf_counter() - start
        return {
            "platform": PLATFORM,
            "intent_id": intent_id,
            "run": run_number,
            "outcome": "error",
            "failed_at_step": f"exception: {type(e).__name__}: {e}",
            "guardrail_catches": 0,
            "duration_sec": round(duration, 2),
        }


def main():
    intent = next(i for i in TEST_INTENTS if i["intent_id"] == "guaranteed_safe")
    with open(OUTPUT_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        for run_number in range(1, N_RUNS + 1):
            row = run_once_v2(intent["intent_id"], intent["raw_request"], run_number)
            writer.writerow(row)
            f.flush()
            print(f"[v2 guaranteed_safe run {run_number}/{N_RUNS}] "
                  f"outcome={row['outcome']} failed_at={row['failed_at_step']} "
                  f"catches={row['guardrail_catches']} dur={row['duration_sec']}s")
    print(f"\nЗачувано во {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
