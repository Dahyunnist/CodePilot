"""Deterministic mechanism-only context budget evaluator; never calls an LLM."""
import json
from pathlib import Path

FIXTURE = Path("evals/context_selector_fixture.json")

def evaluate(data):
    rows=[]
    for task in data["tasks"]:
        evidence=task["evidence"]
        unique={item["sha256"]:item for item in evidence}
        total_tokens=sum(item["tokens"] for item in evidence)
        unique_tokens=sum(item["tokens"] for item in unique.values())
        reserves=task["reserved_patch"]+task["reserved_test"]+task["reserved_final"]
        available=max(0,task["budget"]-reserves)
        retained=min(unique_tokens,available)
        rows.append({"task_id":task["task_id"],"input_tokens":total_tokens,
          "deduplicated_tokens":unique_tokens,"deduplicated_items":len(evidence)-len(unique),
          "truncated_tokens":max(0,unique_tokens-retained),"budget":task["budget"],
          "reserved_tokens":reserves,"retained_tokens":retained,
          "budget_violation":reserves>task["budget"] or retained+reserves>task["budget"]})
    return {"kind":"cp1_context_mechanism_fixture","model_calls":0,"mechanism_only":True,"tasks":rows}

def main():
    data=json.loads(FIXTURE.read_text(encoding="utf-8")); print(json.dumps(evaluate(data),ensure_ascii=False,indent=2))
if __name__=="__main__": main()
