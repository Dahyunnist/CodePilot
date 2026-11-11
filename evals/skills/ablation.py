"""Deterministic fixture-only skill ablation; performs no model calls."""
import json
from pathlib import Path
from codepilot.skills import get_skill

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "evals" / "skills" / "paired-smoke.json"
CHOICES = {
    "skill-pytest-config": ("search_code", "read_file", "run_tests", "apply_patch", "git_diff"),
    "skill-api-pagination": ("search_code", "read_file", "find_references", "run_selected_tests", "apply_patch", "run_tests", "git_diff"),
}

def run():
    frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases = []
    for entry in frozen["cases"]:
        case_id = entry["case_id"]
        skill_id = "pytest-failure-triage" if "pytest" in case_id else "api-contract-check"
        skill = get_skill(skill_id)
        selected = list(CHOICES[case_id])
        restricted = [tool for tool in selected if tool in skill.allowed_tools]
        cases.append({
            "case_id": case_id,
            "no_skill_fixture_tools": selected,
            "skill_fixture_tools": restricted,
            "constraints_satisfied": len(restricted) == len(selected),
            "tool_count_no_skill": len(selected),
            "tool_count_skill": len(restricted),
        })
    return {"kind": "deterministic_skill_ablation_fixture", "deterministic_fixture": True,
            "model_calls": 0, "sample_count": len(cases), "cases": cases,
            "interpretation": "固定工具选择 fixture；不代表 LLM 行为或修复效果"}

if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
