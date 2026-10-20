import json
import subprocess
import sys

with open("evaluation_scenarios.json", encoding="utf-8-sig") as f:
    scenarios = json.load(f)

results = []

for scenario in scenarios:
    query = scenario["query"]
    print(f"Testing {scenario['id']}: {query}", flush=True)

    run = subprocess.run(
        [sys.executable, "corpus.py", "search", query, "-k", "3"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    try:
        passages = json.loads(run.stdout)
    except (json.JSONDecodeError, TypeError):
        passages = []

    results.append({
        "id": scenario["id"],
        "query": query,
        "expected_section_type": scenario.get("expected_section_type"),
        "results": [
            {
                "clause_id": p.get("clause_id"),
                "page": p.get("page"),
                "section_type": p.get("section_type"),
                "score": p.get("score"),
                "text": p.get("text", "")[:500],
            }
            for p in passages
        ],
        "error": run.stderr[-500:] if run.returncode != 0 else None,
    })

with open("evaluation_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\nFinished: {len(results)} scenarios tested.")
print("Results saved to evaluation_results.json")
