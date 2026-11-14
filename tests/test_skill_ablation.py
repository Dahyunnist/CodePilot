import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "evals" / "skills" / "ablation.py"
spec = importlib.util.spec_from_file_location("skill_ablation", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_skill_ablation_is_deterministic_fixture_only():
    report = module.run()
    assert report["deterministic_fixture"] is True
    assert report["model_calls"] == 0
    assert report["sample_count"] == 2
    assert all(case["constraints_satisfied"] for case in report["cases"])
    assert all(case["tool_count_no_skill"] == case["tool_count_skill"] for case in report["cases"])
    assert all(case["inputs"]["instruction"] and case["inputs"]["test_command"] for case in report["cases"])
    assert all(case["skill"]["allowed_tools"] for case in report["cases"])
    assert all(case["skill"]["exit_conditions"] for case in report["cases"])
    assert all(case["skill"]["limits"]["max_steps"] > 0 for case in report["cases"])
    assert all(set(case["skill_fixture_tools"]) <= set(case["skill"]["allowed_tools"]) for case in report["cases"])
