"""Freeze a small, license-audited SWE-bench Lite task manifest without gold patches."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from codepilot.security import redact_sensitive_text


DATASET_REVISION = "SWE-bench/SWE-bench_Lite:test"
SWEBENCH_CODE_REVISION = "02e7a74ffd0b707aab73d203fe87bdc7c76afc8e"
REPOSITORY_LICENSES = {
    "django/django": "BSD-3-Clause",
    "pytest-dev/pytest": "MIT",
    "pydata/xarray": "Apache-2.0",
    "mwaskom/seaborn": "BSD-3-Clause",
    "scikit-learn/scikit-learn": "BSD-3-Clause",
}
TASK_IDS = (
    "django__django-10924",
    "django__django-11001",
    "django__django-11099",
    "django__django-11133",
    "pytest-dev__pytest-5103",
    "pytest-dev__pytest-5221",
    "pytest-dev__pytest-5413",
    "pytest-dev__pytest-5495",
    "pydata__xarray-3364",
    "pydata__xarray-4094",
    "pydata__xarray-4248",
    "pydata__xarray-4493",
    "mwaskom__seaborn-2848",
    "mwaskom__seaborn-3010",
    "mwaskom__seaborn-3190",
    "mwaskom__seaborn-3407",
    "scikit-learn__scikit-learn-10508",
    "scikit-learn__scikit-learn-10949",
    "scikit-learn__scikit-learn-11040",
    "scikit-learn__scikit-learn-12471",
)
_TEST_PATH = re.compile(r"(?:^|/)(?:test|tests|testing)/|(?:^|/)test_[^/]+\.py$|_test\.py$")


def freeze(source: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite frozen manifest: {output}")
    raw = source.read_bytes()
    dataset = json.loads(raw.decode("utf-8-sig"))
    rows = dataset if isinstance(dataset, list) else dataset.get("rows", [])
    if rows and isinstance(rows[0], dict) and "row" in rows[0]:
        rows = [item["row"] for item in rows]
    by_id = {str(row["instance_id"]): row for row in rows}
    missing = sorted(set(TASK_IDS) - by_id.keys())
    if missing:
        raise ValueError(f"dataset missing selected tasks: {', '.join(missing)}")
    tasks = []
    for task_id in TASK_IDS:
        row = by_id[task_id]
        repo = str(row["repo"])
        if repo not in REPOSITORY_LICENSES:
            raise ValueError(f"repository has no audited license entry: {repo}")
        patch = str(row.get("test_patch") or "")
        paths = [
            line.split(" b/", 1)[0].removeprefix("diff --git a/")
            for line in patch.splitlines()
            if line.startswith("diff --git a/")
        ]
        if not paths or any(not _TEST_PATH.search(path) for path in paths):
            raise ValueError(f"test patch includes a non-test path: {task_id}")
        statement = str(row.get("problem_statement") or "")
        if not statement.strip() or not row.get("base_commit"):
            raise ValueError(f"task lacks issue description or fixed base commit: {task_id}")
        issue_number = task_id.rsplit("-", 1)[-1]
        public_reference = row.get("pr_url") or f"https://github.com/{repo}/pull/{issue_number}"
        public_statement = redact_sensitive_text(statement)
        tasks.append(
            {
                "task_id": task_id,
                "repo": repo,
                "license": REPOSITORY_LICENSES[repo],
                "base_commit": row["base_commit"],
                "issue_url": row.get("issue_url", ""),
                "pull_request_url": public_reference,
                "problem_statement": public_statement,
                "docker_image": row.get("image", ""),
                "created_at": row.get("created_at", ""),
                "problem_statement_sha256": hashlib.sha256(public_statement.encode("utf-8")).hexdigest(),
                "hidden_test_patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
                "gold_patch_sha256": hashlib.sha256(str(row.get("patch") or "").encode("utf-8")).hexdigest(),
                "hidden_test_files": paths,
                "fail_to_pass_count": len(row.get("FAIL_TO_PASS", [])),
                "pass_to_pass_count": len(row.get("PASS_TO_PASS", [])),
            }
        )
    counts = Counter(item["repo"] for item in tasks)
    if len(tasks) < 15 or len(counts) < 3 or len(counts) > 5:
        raise ValueError("frozen set must contain at least 15 tasks across 3–5 repositories")
    manifest = {
        "benchmark": "SWE-bench Lite",
        "dataset_revision": DATASET_REVISION,
        "dataset_source_sha256": hashlib.sha256(raw).hexdigest(),
        "swebench_code_revision": SWEBENCH_CODE_REVISION,
        "gold_patch_policy": "hash only; patch contents excluded",
        "repository_count": len(counts),
        "task_count": len(tasks),
        "tasks_per_repository": dict(sorted(counts.items())),
        "tasks": tasks,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = freeze(args.source, args.output)
    print(f"冻结 {manifest['task_count']} 题 / {manifest['repository_count']} 个仓库：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
