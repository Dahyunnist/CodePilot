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
        case_data = json.loads(
            (ROOT / "evals" / "skills" / "cases" / case_id / "case.json").read_text(encoding="utf-8")
        )
        skill_id = {
            "pytest-failure-triage": "pytest-failure-triage",
            "api-contract-cross-file": "api-contract-check",
        }[case_data["category"]]
        skill = get_skill(skill_id)
        selected = list(CHOICES[case_id])
        restricted = [tool for tool in selected if tool in skill.allowed_tools]
        case_root = ROOT / "evals" / "skills" / "cases" / case_id
        cases.append({
            "case_id": case_id,
            "skill": {
                "skill_id": skill.skill_id,
                "title": skill.title,
                "objective": skill.objective,
                "allowed_tools": sorted(skill.allowed_tools),
                "exit_conditions": list(skill.exit_conditions),
                "limits": {
                    "max_steps": skill.max_steps,
                    "max_test_attempts": skill.max_test_attempts,
                    "max_total_tokens": skill.max_total_tokens,
                },
            },
            "inputs": {
                "instruction": case_data["instruction"],
                "test_command": case_data["test_command"],
                "repository": str((case_root / "repo").relative_to(ROOT)),
            },
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
