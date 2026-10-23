"""Read-only candidate selection from the canonical Manager task registry."""
import json
from pathlib import Path

TASKS = Path(__file__).resolve().parents[1] / "docs/roadmap/tasks.json"


def ready_candidates(tasks):
    done = {item["id"] for item in tasks if item["status"] == "done"}
    return sorted(
        item["id"] for item in tasks
        if item["status"] == "todo"
        and all(dep in done for dep in item["depends"])
        and item.get("external", "none") == "none"
    )


if __name__ == "__main__":
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    print(json.dumps({"candidates_not_authorizations": ready_candidates(tasks)}))
