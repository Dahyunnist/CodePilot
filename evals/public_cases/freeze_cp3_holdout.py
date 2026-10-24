"""Freeze a fresh, hash-pinned public repair set without exposing oracle patches."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from codepilot.security import redact_sensitive_text


DATASET_REVISION = "SWE-bench/SWE-bench_Lite:test"
DATASET_SOURCE_SHA256 = "5cb74f0feb564d6c6bf3f51725384ca646b854d2713d62e86227a29af61d1a92"
SWEBENCH_CODE_REVISION = "02e7a74ffd0b707aab73d203fe87bdc7c76afc8e"
REPOSITORY_LICENSES = {
    "django/django": "BSD-3-Clause",
    "pytest-dev/pytest": "MIT",
    "pydata/xarray": "Apache-2.0",
    "scikit-learn/scikit-learn": "BSD-3-Clause",
}
TASK_SELECTIONS = (
    {
        "task_id": "django__django-16379",
        "defect_mechanism": "缓存并发与一致性",
    },
    {
        "task_id": "pytest-dev__pytest-7168",
        "defect_mechanism": "异常表示与错误报告",
    },
    {
        "task_id": "pydata__xarray-5131",
        "defect_mechanism": "多对象文本表示一致性",
    },
    {
        "task_id": "scikit-learn__scikit-learn-14087",
        "defect_mechanism": "模型边界条件与索引安全",
    },
)
PREVIOUSLY_EXPOSED_TASK_IDS = frozenset(
    {
        "django__django-10924", "django__django-11001", "django__django-11099",
        "django__django-11133", "mwaskom__seaborn-2848", "mwaskom__seaborn-3010",
        "mwaskom__seaborn-3190", "mwaskom__seaborn-3407", "pydata__xarray-3364",
        "pydata__xarray-4094", "pydata__xarray-4248", "pydata__xarray-4493",
        "pytest-dev__pytest-5103", "pytest-dev__pytest-5221",
        "pytest-dev__pytest-5413", "pytest-dev__pytest-5495",
        "scikit-learn__scikit-learn-10508", "scikit-learn__scikit-learn-10949",
        "scikit-learn__scikit-learn-11040", "scikit-learn__scikit-learn-12471",
        "urllib3-3636", "urllib3-3649", "urllib3-3653", "urllib3-3653-narrow",
        "urllib3-3700", "urllib3-3710", "requests-6628",
    }
)
_TEST_PATH = re.compile(
    r"(?:^|/)(?:test|tests|testing)/|(?:^|/)test_[^/]+\.py$|_test\.py$",
    re.IGNORECASE,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dataset_rows(raw: Any) -> dict[str, dict[str, Any]]:
    rows = raw if isinstance(raw, list) else raw.get("rows", [])
    if rows and isinstance(rows[0], dict) and "row" in rows[0]:
        rows = [item["row"] for item in rows]
    return {str(row["instance_id"]): row for row in rows}


def _test_paths(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        if not line.startswith("diff --git a/"):
            continue
        parts = line.split(" ")
        if len(parts) != 4:
            raise ValueError("隐藏测试补丁含无法解析的文件路径")
        old_path = parts[2][2:]
        new_path = parts[3][2:]
        for path in (old_path, new_path):
            if path == "/dev/null":
                continue
            if (
                path.startswith("/")
                or "\\" in path
                or ".." in Path(path).parts
                or not _TEST_PATH.search(path)
            ):
                raise ValueError(f"隐藏测试补丁触及非测试路径：{path}")
            paths.append(path)
    return list(dict.fromkeys(paths))


def freeze(
    source: Path,
    output: Path,
    *,
    selections: Sequence[dict[str, str]] = TASK_SELECTIONS,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"拒绝覆盖已冻结清单：{output}")
    raw = source.read_bytes()
    dataset_sha = _sha256(raw)
    if dataset_sha != DATASET_SOURCE_SHA256:
        raise ValueError("SWE-bench Lite 原始数据 SHA-256 与审计记录不符")
    rows = _dataset_rows(json.loads(raw.decode("utf-8-sig")))
    task_ids = [item["task_id"] for item in selections]
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("冻结任务 ID 重复")
    seen = set(task_ids) & PREVIOUSLY_EXPOSED_TASK_IDS
    if seen:
        raise ValueError(f"冻结任务曾用于模型评测：{', '.join(sorted(seen))}")
    if len(selections) < 4:
        raise ValueError("新 holdout 至少冻结 4 道任务")

    tasks: list[dict[str, Any]] = []
    for selection in selections:
        task_id = selection["task_id"]
        row = rows.get(task_id)
        if row is None:
            raise ValueError(f"数据集缺少任务：{task_id}")
        repo = str(row.get("repo") or "")
        if repo not in REPOSITORY_LICENSES:
            raise ValueError(f"仓库许可证未审核：{repo}")
        statement = redact_sensitive_text(str(row.get("problem_statement") or ""))
        if not statement.strip() or not re.fullmatch(r"[0-9a-f]{40}", str(row.get("base_commit") or "")):
            raise ValueError(f"任务缺少说明或固定 base commit：{task_id}")
        test_patch = str(row.get("test_patch") or "")
        hidden_paths = _test_paths(test_patch)
        if not hidden_paths:
            raise ValueError(f"隐藏测试补丁没有可识别的测试路径：{task_id}")
        image = str(row.get("image") or "")
        if not image:
            raise ValueError(f"任务缺少固定 Docker 镜像：{task_id}")
        tasks.append(
            {
                "task_id": task_id,
                "repo": repo,
                "license": REPOSITORY_LICENSES[repo],
                "defect_mechanism": selection["defect_mechanism"],
                "base_commit": row["base_commit"],
                "docker_image": image,
                "issue_url": row.get("issue_url"),
                "pull_request_url": row.get("pull_request_url"),
                "environment_setup_commit": row.get("environment_setup_commit"),
                "version": row.get("version"),
                "created_at": row.get("created_at", ""),
                "problem_statement": statement,
                "problem_statement_sha256": _sha256(statement.encode("utf-8")),
                "hidden_test_patch_sha256": _sha256(test_patch.encode("utf-8")),
                "gold_patch_sha256": _sha256(str(row.get("patch") or "").encode("utf-8")),
                "hidden_test_paths": hidden_paths,
                "hidden_test_files": hidden_paths,
                "fail_to_pass_count": len(row.get("FAIL_TO_PASS", [])),
                "pass_to_pass_count": len(row.get("PASS_TO_PASS", [])),
            }
        )

    repositories = Counter(task["repo"] for task in tasks)
    mechanisms = {task["defect_mechanism"] for task in tasks}
    if len(repositories) < 3 or len(mechanisms) < 3:
        raise ValueError("冻结集须覆盖至少 3 个仓库和 3 种缺陷机制")
    per_task_cost = 8 * (22_000 * 0.30 + 512 * 1.20) / 1_000_000
    manifest = {
        "benchmark": "SWE-bench Lite fresh CP-1/CP-2 slice",
        "frozen_at": "2026-10-23",
        "dataset_revision": DATASET_REVISION,
        "dataset_source_sha256": dataset_sha,
        "swebench_code_revision": SWEBENCH_CODE_REVISION,
        "exclusion_policy": "排除此前公开评测任务、S16 urllib3-3636、S21 urllib3-3653",
        "excluded_seen_task_ids": sorted(PREVIOUSLY_EXPOSED_TASK_IDS),
        "model_exposure": "本次冻结前未调用模型；公开基准仍可能存在训练污染",
        "gold_patch_policy": "仅保存 SHA-256，不保存 gold patch 内容",
        "strict_acceptance": "Agent 正常 success 且 Agent 完整测试、独立可见测试、隐藏测试全部通过",
        "task_count": len(tasks),
        "repository_count": len(repositories),
        "repositories": dict(sorted(repositories.items())),
        "defect_mechanism_count": len(mechanisms),
        "real_model_authorized": False,
        "real_model_blocker": "账户当前余额未知；须先核对余额与项目账本，不可用离线测试代替",
        "limits": {
            "max_total_tokens_per_task": 20_000,
            "context_budget_chars": 12_000,
            "max_steps": 8,
            "max_elapsed_seconds": 300,
            "max_input_tokens_per_request": 22_000,
            "max_completion_tokens": 512,
            "sdk_retries": 0,
            "max_cost_reserve_usd_per_task": 0.06,
            "worst_case_cost_usd_per_task": round(per_task_cost, 8),
            "max_cost_reserve_usd_all_tasks": round(0.06 * len(tasks), 2),
        },
        "preflight_status": "pending_docker_images_and_baselines",
        "tasks": tasks,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/public_cases/cp3/fresh-holdout-2026-10-23.json"),
    )
    args = parser.parse_args()
    manifest = freeze(args.source, args.output)
    print(
        f"已冻结 {manifest['task_count']} 题，覆盖 {manifest['repository_count']} 个仓库；"
        "真实模型授权关闭，等待 Docker 基线和费用复核。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
