import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).parents[1]

def test_readme_offline_commands_execute_without_model_or_download():
    commands=[
        [sys.executable,"scripts/evaluate_cp1_context_offline.py"],
        [sys.executable,"-m","evals.skills.ablation"],
        [sys.executable,"-m","pytest","tests/test_benchmark_manifest_integrity.py","tests/test_cp2_dataset_fetch.py","tests/test_skill_ablation.py","-q","--basetemp=.tmp/pytest-readme-smoke"],
    ]
    for command in commands:
        completed=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
        assert completed.returncode==0, completed.stdout+completed.stderr
