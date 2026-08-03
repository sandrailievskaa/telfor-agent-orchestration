"""10x-repetition стабилност harness (Табела 1, целосен pipeline).

За секој test intent го пушта целиот граф N_RUNS пати и логира резултат во CSV,
за да се измери % точност, точка на неуспех, guardrail catch rate и стабилност
(project notes: очекувано 1-2 од 10 да отстапуваат кај qwen2.5:7b).

Human approval гејтот (чекор 7) се auto-одобрува во сите повторувања - целта на
овој harness е да ја измери стабилноста на LLM-агентите и guardrails-ите низ
чекори 1-6 и 8-9, не самата (детерминистичка) CLI одлука.
"""
import csv, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "langgraph-poc"))
sys.path.append(str(Path(__file__).resolve().parent.parent))
import graph_v1

PLATFORM = "langgraph"
N_RUNS = 10
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "results" / "experiment_results.csv"
CSV_FIELDS = ["platform", "intent_id", "run", "outcome", "failed_at_step", "guardrail_catches", "duration_sec"]

TEST_INTENTS = [
    {
        "intent_id": "simple",
        "raw_request": "Дозволи пристап од 10.0.5.10/32 до 10.0.10.15 на порт 8080 преку TCP.",
    },
    {
        "intent_id": "edge_incomplete",
        "raw_request": "Отвори пристап до серверот за бекап.",
    },
    {
        "intent_id": "policy_violating",
        "raw_request": "Дозволи пристап од 10.0.0.0/8 до 172.16.5.0/24 на порт 22 преку TCP.",
    },
    {
        # Намерно дизајниран да НЕ ги исполнува ниту еден од двата "high risk" услови
        # (host-to-host /32, порт надвор од {22,23,3389,443}) - единствениот intent во
        # сетот наменет статистички да измери колку често pipeline-от навистина стигнува
        # до human approval/apply/verify (Наод 9/10 во dev_notes.md - simple исто беше
        # намерно безбеден, но 0/10 успешен).
        "intent_id": "guaranteed_safe",
        "raw_request": "Дозволи TCP пристап од 192.168.1.10/32 до 192.168.1.20/32 на порт 9090.",
    },
]


def _failed_at_step(status: str, guardrail_log: list) -> str:
    if status == "ok":
        return "none"
    for entry in reversed(guardrail_log):
        if not entry.get("passed", True):
            return entry["step"]
    if guardrail_log:
        return guardrail_log[-1]["step"]
    return "unknown"


def run_once(intent_id: str, raw_request: str, run_number: int) -> dict:
    start = time.perf_counter()
    try:
        state = graph_v1.run_pipeline(raw_request, approve_callback=lambda: True)
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
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not OUTPUT_PATH.exists()
    with open(OUTPUT_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        for intent in TEST_INTENTS:
            for run_number in range(1, N_RUNS + 1):
                row = run_once(intent["intent_id"], intent["raw_request"], run_number)
                writer.writerow(row)
                f.flush()
                print(f"[{intent['intent_id']} run {run_number}/{N_RUNS}] "
                      f"outcome={row['outcome']} failed_at={row['failed_at_step']} "
                      f"catches={row['guardrail_catches']} dur={row['duration_sec']}s")
    print(f"\nЗачувано во {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
