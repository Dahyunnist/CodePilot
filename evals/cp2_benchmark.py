"""Freeze and run paired, visible-only CP-2 evaluations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from codepilot.security import redact_sensitive_text


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION = ROOT / "evals/public_cases/cp2/frozen-selection.json"
DEFAULT_MANIFEST = ROOT / "evals/public_cases/cp2/benchmark-v1.json"
DEFAULT_SOURCE_PROVENANCE = ROOT / "evals/public_cases/cp2/source-provenance-v1.json"
RUNNABLE_TASK_SCHEMA = ROOT / "evals/public_cases/cp2/runnable-task.schema.json"
SOURCE_PROVENANCE_SCHEMA = ROOT / "evals/public_cases/cp2/source-provenance.schema.json"
DEFAULT_LEDGER = ROOT / "evals/public_cases/cp2/budget-ledger-v1.json"
REPORTS_ROOT = ROOT / "reports"
AUTHORIZED_CAP_USD = Decimal("0.50")
DATASET_REVISION = "b0dde1093fe417d83b7184254edf8199c1f0dff5"
DATASET_SHA256 = "438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3"
SUBSET_SHA256 = "8fb7c6b9a93a3eaef1d0c55839e8d5420ad222447cac7b247735faf23927941d"

TASK_IDS = (
    "django__django-10924", "django__django-11001", "django__django-11099",
    "django__django-11133", "pytest-dev__pytest-5103", "pytest-dev__pytest-5221",
    "pytest-dev__pytest-5413", "pytest-dev__pytest-5495", "pydata__xarray-3364",
    "pydata__xarray-4094", "pydata__xarray-4248", "pydata__xarray-4493",
    "mwaskom__seaborn-2848", "mwaskom__seaborn-3010",
    "scikit-learn__scikit-learn-10508",
)

RUNTIME = {
    "django__django-10924": "sha256:d41b289ea27a92ef6346702388e5ea0b8c8f48c41d83466a72c2dffb934007a1",
    "django__django-11001": "sha256:68c61032db48a5eef2175532d3555e20acdd426aa5b426ba3acfe34a0ddd83b7",
    "django__django-11099": "sha256:cca302934edd881cc4f1e4647a389a25cdaa3c02bfa33667a4204934a09c4fb1",
    "django__django-11133": "sha256:914093363dbe12def92c5d36e9bdc5270cce5ed0aa6f3daad8bc4ef0389c29bf",
    "pytest-dev__pytest-5103": "sha256:1648c614485c81d9e08bcf9ec8014fb38cd2f20fad6bea782552d923a35ce714",
    "pytest-dev__pytest-5221": "sha256:547472f1933751a67623599dae697188232c9712a46ab66fb69330f88b911e5a",
    "pytest-dev__pytest-5413": "sha256:75700210c9eb925d1abde2cb95b7dfffc2c409376ae434854375bacaa193864f",
    "pytest-dev__pytest-5495": "sha256:86b356cf05ac9a623ba8943849e25ce2d0bcebc506753b1361595e5ad488a9b3",
    "pydata__xarray-3364": "sha256:8591047f512d8d26b4d0e121d2d04eb6b95fa6ad41e13d92fe64f5ef66244c27",
    "pydata__xarray-4094": "sha256:6bcd1fe581af0796691ac3527b940d43e5e1bfd6539adeecebb12f3e4b25dc2c",
    "pydata__xarray-4248": "sha256:d16aca15c86b2ef8a698600711bfde3559f794154a0edd4ac4213edf6b6fdf73",
    "pydata__xarray-4493": None,
    "mwaskom__seaborn-2848": "sha256:d719470351e66623e532a4f23cdedfe8fb737147fe108e4b5829aa273528389d",
    "mwaskom__seaborn-3010": "sha256:22fef36e8b9655fb1642d976de669e3f2426df0186a09d6d788fc6215cfa1bc0",
    "scikit-learn__scikit-learn-10508": "sha256:4c25a7511f252ed93ce8555f6bb84ffb8d56baa46151e3df5b4338cb2f228677",
}

LICENSES = {
    "django/django": ("BSD-3-Clause", "LICENSE", "b846415d1b514e9c1dff14a22deb906d794bc546ca6129f950a18cd091e2a669"),
    "pytest-dev/pytest": ("MIT", "LICENSE", "4be38574daf05665b6194e4fd84c5ef6ce7c3a2810308a5222d5cdffc2d04d18"),
    "pydata/xarray": ("Apache-2.0", "LICENSE", "73ba74dfaa520b49a401b5d21459a8523a146f3b7518a833eea5efa85130bf68"),
    "mwaskom/seaborn": ("BSD-3-Clause", "LICENSE", "0874bfc01308833385b2f5ca62205525739f6a57b8688afea1b078d0f845d6d4"),
    "scikit-learn/scikit-learn": ("BSD-3-Clause", "COPYING", "3f046f2b5eea2c3b852dae4feea90f92a64ced2a6ac23ea137db2a5ac347ce22"),
}

VISIBLE_SPECS = {
    "django__django-10924": "FilePathField accepts a callable path and migration deconstruction preserves it.",
    "django__django-11001": "Distinct multiline RawSQL ordering expressions both survive SQL compilation.",
    "django__django-11099": "ASCII and Unicode username validators reject a trailing newline.",
    "django__django-11133": "HttpResponse(memoryview(...)).content returns the underlying bytes.",
    "pytest-dev__pytest-5103": "A failing all(generator) assertion reports the failing element.",
    "pytest-dev__pytest-5221": "pytest --fixtures output includes each fixture's declared scope.",
    "pytest-dev__pytest-5413": "str(pytest.raises(...)) exposes the captured exception message.",
    "pytest-dev__pytest-5495": "Byte-string assertion output avoids misleading integer ordinals.",
    "pydata__xarray-3364": "Concatenating datasets with different variables retains the variable union.",
    "pydata__xarray-4094": "Stack/unstack round-trip supports variables with one sample dimension.",
    "pydata__xarray-4248": "Dataset representation displays units stored in variable attributes.",
    "pydata__xarray-4493": "Dataset.update preserves laziness of a chunked Dask array.",
    "mwaskom__seaborn-2848": "pairplot accepts hue_order that omits observed hue values.",
    "mwaskom__seaborn-3010": "PolyFit plotting tolerates missing observations without eager failure.",
    "scikit-learn__scikit-learn-10508": "LabelEncoder transforms an empty input after fitting string labels.",
}

MODEL = {
    "provider": "DeepSeek",
    "api_base_url": "https://api.deepseek.com",
    "configured_model_alias": "deepseek-v4-flash",
    "resolved_model_version": "DeepSeek-V4.1-Flash-1017",
    "price_url": "https://api-docs.deepseek.com/quick_start/pricing/",
    "peak_usd_per_million": {"input_uncached": "0.30", "input_cached": "0.006", "output": "1.20"},
    "off_peak_usd_per_million": {"input_uncached": "0.15", "input_cached": "0.003", "output": "0.60"},
    "temperature": "provider_default_unspecified",
}

LIMITS = {
    "max_input_tokens_per_request": 22_000,
    "max_completion_tokens": 512,
    "max_steps": 8,
    "max_total_tokens_per_task": 20_000,
    "context_budget_chars": 8_000,
    "max_elapsed_seconds": 180,
}


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _walk_reports(root: Path):
    excluded = {".tmp", "verification", "repo", "traces", "test-logs", "django_10924"}
    for base, directories, files in os.walk(root):
        directories[:] = [name for name in directories if name not in excluded]
        for name in files:
            if name == "results.csv":
                yield Path(base) / name


def build_budget_ledger(reports_root: Path) -> dict[str, Any]:
    unique: dict[str, tuple[Decimal, str]] = {}
    file_fingerprints: list[tuple[str, str]] = []
    csv_count = 0
    for path in sorted(_walk_reports(reports_root)):
        relative = path.relative_to(reports_root).as_posix()
        file_fingerprints.append((relative, _file_hash(path)))
        csv_count += 1
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    cost = Decimal((row.get("cost_usd_estimate") or "").strip())
                except Exception:
                    continue
                if cost <= 0:
                    continue
                run_id = (row.get("run_id") or "").strip() or f"{relative}:{row.get('case_id', '')}"
                prior = unique.get(run_id)
                if prior is None or cost > prior[0]:
                    unique[run_id] = (cost, relative)

    partial_path = reports_root / "cp4-live-pilot-20261024" / "partial-django-none.json"
    partial_cost = Decimal("0")
    partial_hash = None
    if partial_path.is_file():
        partial = json.loads(partial_path.read_text(encoding="utf-8"))
        partial_cost = Decimal(str(partial.get("cost_usd_estimate", "0")))
        partial_hash = _file_hash(partial_path)

    csv_usage = sum((item[0] for item in unique.values()), Decimal("0"))
    cumulative = csv_usage + partial_cost
    remaining = AUTHORIZED_CAP_USD - cumulative
    return {
        "ledger_version": 1,
        "authorized_project_cap_usd": str(AUTHORIZED_CAP_USD),
        "usage_source": "local evaluation result CSVs; estimate, not provider billing export",
        "result_csv_count": csv_count,
        "unique_positive_cost_runs": len(unique),
        "result_csv_estimated_cost_usd": str(csv_usage.quantize(Decimal("0.000001"))),
        "additional_partial_cost_usd": str(partial_cost.quantize(Decimal("0.000001"))),
        "additional_partial_record_sha256": partial_hash,
        "known_cumulative_estimated_cost_usd": str(cumulative.quantize(Decimal("0.000001"))),
        "estimated_remaining_usd": str(remaining.quantize(Decimal("0.000001"))),
        "usage_files_sha256": _canonical_hash(file_fingerprints),
        "provider_balance_available": True,
        "provider_balance_amounts_persisted": False,
        "account_usage_reconciled": False,
        "model_calls_allowed": False,
        "blocker": "remaining authorized budget is below the 15-task paired worst-case reserve; provider balance endpoint exposes availability/current balance, not cumulative usage",
    }


def freeze_manifest(selection_path: Path) -> dict[str, Any]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    by_id = {task["task_id"]: task for task in selection["tasks"]}
    missing = sorted(set(TASK_IDS) - by_id.keys())
    if missing:
        raise ValueError(f"selection lacks selected tasks: {missing}")

    tasks = []
    for task_id in TASK_IDS:
        source = by_id[task_id]
        if source["repo"] not in LICENSES:
            raise ValueError(f"no license evidence for {task_id}")
        license_name, license_file, license_hash = LICENSES[source["repo"]]
        image_digest = RUNTIME[task_id]
        spec = VISIBLE_SPECS[task_id]
        task = {
            "task_id": task_id,
            "repo": source["repo"],
            "license": license_name,
            "license_file_at_base": license_file if image_digest else None,
            "license_file_sha256": license_hash if image_digest else None,
            "license_evidence": "verified_at_exact_base" if image_digest else "pending_missing_image",
            "base_commit": source["base_commit"],
            "base_commit_verified_in_image": image_digest is not None,
            "public_reference": source["pull_request_url"],
            "problem_statement": source["problem_statement"],
            "problem_statement_sha256": source["problem_statement_sha256"],
            "gold_patch_sha256": source["gold_patch_sha256"],
            "gold_source": "hash copied from prior frozen selection; gold content not read or exposed",
            "docker_image_ref": source["docker_image"],
            "docker_image_config_digest": image_digest,
            "runtime_status": "pinned_local_image" if image_digest else "image_missing",
            "visible_test_spec": spec,
            "visible_test_spec_sha256": hashlib.sha256(spec.encode("utf-8")).hexdigest(),
            "visible_test_status": "spec_frozen_test_not_materialized_or_run",
        }
        task["task_record_sha256"] = _canonical_hash(task)
        tasks.append(task)

    if len(tasks) != 15 or len({task["repo"] for task in tasks}) != 5:
        raise ValueError("CP-2 freeze must contain 15 tasks across 5 repositories")

    artifacts = _current_artifact_hashes()
    scorer_hash = _canonical_hash({"files": artifacts, "policy": "agent_success_and_agent_tests_and_independent_public_visible_tests; no private oracle"})
    runtime_descriptor = {task["task_id"]: {"ref": task["docker_image_ref"], "config_digest": task["docker_image_config_digest"]} for task in tasks}
    runtime_hash = _canonical_hash({"platform": "linux/amd64", "images": runtime_descriptor})
    model_descriptor = dict(MODEL)
    model_hash = _canonical_hash(model_descriptor)
    manifest = {
        "schema_version": 1,
        "benchmark": "SWE-bench Lite public visible-only subset",
        "frozen_at": "2026-11-13",
        "task_count": len(tasks),
        "repository_count": len({task["repo"] for task in tasks}),
        "dataset": {
            "name": "SWE-bench Lite",
            "revision": DATASET_REVISION,
            "source_parquet_sha256": DATASET_SHA256,
            "selected_subset_sha256": SUBSET_SHA256,
            "selection_manifest_sha256": _file_hash(selection_path),
            "metadata_crosscheck": "15/15 selected task IDs, repos, base commits, and public statement hashes match sanitized frozen subset",
            "gold_policy": "SHA-256 only; no patch content in agent workspace",
        },
        "task_record_sha256": _canonical_hash([task["task_record_sha256"] for task in tasks]),
        "gold_sha256": _canonical_hash({task["task_id"]: task["gold_patch_sha256"] for task in tasks}),
        "artifacts": artifacts,
        "scorer_sha256": scorer_hash,
        "runtime_sha256": runtime_hash,
        "runtime_platform": "linux/amd64",
        "model": model_descriptor,
        "model_sha256": model_hash,
        "pairing": {
            "dimension": "context_selector",
            "baseline": {"context_selector_enabled": False, "context_selector_version": "baseline"},
            "treatment": {"context_selector_enabled": True, "context_selector_version": "layered-context-v1"},
            "same_for_pair": ["task statement", "base commit", "visible tests", "runtime image", "model", "prompt", "token limits", "time limit", "test oracle"],
            "run_order": "deterministic alternating order by sorted task index",
            "failure_artifacts": "retain each variant's JSONL trace and per-case JSON result",
        },
        "limits": dict(LIMITS),
        "budget_ledger_path": "budget-ledger-v1.json",
        "tasks": tasks,
        "freeze_status": "metadata_frozen; visible tests and one runtime image pending; live evaluation blocked by budget",
    }
    return manifest


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_sha256(value: Any, *, prefixed: bool = False) -> bool:
    pattern = r"sha256:[a-f0-9]{64}" if prefixed else r"[a-f0-9]{64}"
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _current_artifact_hashes() -> dict[str, str]:
    return {
        "agent_python_tree_sha256": _tree_hash(ROOT / "codepilot"),
        "live_runner_sha256": _file_hash(ROOT / "evals/live_runner.py"),
        "pair_scorer_sha256": _file_hash(ROOT / "evals/compare_live_runs.py"),
        "paired_driver_sha256": _file_hash(ROOT / "evals/cp2_benchmark.py"),
        "source_provenance_sha256": _file_hash(DEFAULT_SOURCE_PROVENANCE),
        "runnable_task_schema_sha256": _file_hash(RUNNABLE_TASK_SCHEMA),
        "source_provenance_schema_sha256": _file_hash(SOURCE_PROVENANCE_SCHEMA),
    }


def _validate_runnable_contract(
    manifest: dict[str, Any],
    *,
    source_provenance_path: Path = DEFAULT_SOURCE_PROVENANCE,
) -> list[str]:
    """Validate source, license, image, test, and executable artifact pins.

    The checked-in JSON schemas describe the same fail-closed contract. This
    validator uses only stdlib checks so planning does not add a dependency.
    """
    blockers: list[str] = []
    try:
        task_schema = _load_json(RUNNABLE_TASK_SCHEMA)
        provenance_schema = _load_json(SOURCE_PROVENANCE_SCHEMA)
    except (OSError, json.JSONDecodeError):
        return ["runnable contract schema missing or invalid"]
    required_fields = task_schema.get("required", [])
    source_required = provenance_schema["$defs"]["task"].get("required", [])
    issue_required = provenance_schema["$defs"]["issue"].get("required", [])

    try:
        provenance = _load_json(source_provenance_path)
    except (OSError, json.JSONDecodeError):
        provenance = {}
        blockers.append("source provenance manifest missing or invalid")
    provenance_rows = provenance.get("tasks", [])
    provenance_by_id = {
        item.get("task_id"): item for item in provenance_rows
        if isinstance(item, dict)
    } if isinstance(provenance_rows, list) else {}
    manifest_tasks = manifest.get("tasks", [])
    if not isinstance(manifest_tasks, list):
        blockers.append("manifest tasks must be an array")
        manifest_tasks = []
    manifest_task_ids = {
        item.get("task_id") for item in manifest_tasks if isinstance(item, dict)
    }
    if len(provenance_by_id) != len(provenance_rows) or set(provenance_by_id) != manifest_task_ids:
        blockers.append("source provenance task set differs from benchmark task set")
    if provenance.get("schema_version") != provenance_schema["properties"]["schema_version"]["const"]:
        blockers.append("source provenance schema version invalid")

    record_hashes: list[str] = []
    gold_hashes: dict[str, str] = {}
    for item in manifest_tasks:
        if not isinstance(item, dict):
            blockers.append("manifest task entry must be an object")
            continue
        record = dict(item)
        expected_record_hash = record.pop("task_record_sha256", None)
        actual_record_hash = _canonical_hash(record)
        if not _is_sha256(expected_record_hash) or expected_record_hash != actual_record_hash:
            blockers.append(f"{item.get('task_id', '<missing-task-id>')}: task record hash missing or mismatched")
        else:
            record_hashes.append(expected_record_hash)
        task_id = item.get("task_id")
        patch_hash = item.get("gold_patch_sha256")
        if isinstance(task_id, str) and isinstance(patch_hash, str):
            gold_hashes[task_id] = patch_hash
    if _canonical_hash(record_hashes) != manifest.get("task_record_sha256"):
        blockers.append("task record aggregate hash mismatch")
    if _canonical_hash(gold_hashes) != manifest.get("gold_sha256"):
        blockers.append("gold patch hash aggregate mismatch")
    if (
        manifest.get("dataset", {}).get("selection_manifest_sha256")
        != _file_hash(DEFAULT_SELECTION)
    ):
        blockers.append("frozen selection manifest hash mismatch")

    runtime_descriptor = {
        item["task_id"]: {
            "ref": item.get("docker_image_ref"),
            "config_digest": item.get("docker_image_config_digest"),
        }
        for item in manifest_tasks
        if isinstance(item, dict) and isinstance(item.get("task_id"), str)
    }
    expected_runtime_hash = _canonical_hash(
        {"platform": manifest.get("runtime_platform"), "images": runtime_descriptor}
    )
    if expected_runtime_hash != manifest.get("runtime_sha256"):
        blockers.append("runtime manifest hash mismatch")

    for task in manifest.get("tasks", []):
        task_id = str(task.get("task_id", "<missing-task-id>"))
        for field in required_fields:
            if field not in task or task[field] is None or task[field] == "":
                blockers.append(f"{task_id}: required runnable field missing: {field}")

        source = provenance_by_id.get(task.get("task_id"))
        if source is None:
            blockers.append(f"{task_id}: first-party source provenance missing")
        else:
            for field in source_required:
                if field not in source or source[field] is None or source[field] == "":
                    blockers.append(f"{task_id}: source provenance field missing: {field}")
            repo = task.get("repo")
            if source.get("repo") != repo or source.get("pr_status") != "merged":
                blockers.append(f"{task_id}: source repository or PR status mismatch")
            source_url = source.get("source_pr_url")
            parsed = urlparse(source_url) if isinstance(source_url, str) else None
            valid_pr = bool(
                parsed
                and parsed.scheme == "https"
                and parsed.netloc == "github.com"
                and parsed.path.startswith(f"/{repo}/pull/")
                and re.fullmatch(rf"/{re.escape(str(repo))}/pull/[0-9]+", parsed.path)
            )
            if not valid_pr or source_url != task.get("public_reference"):
                blockers.append(f"{task_id}: source PR link missing, invalid, or inconsistent")
            linked_issues = source.get("linked_issues")
            if not isinstance(linked_issues, list) or not linked_issues:
                blockers.append(f"{task_id}: linked issue provenance missing")
            else:
                for issue in linked_issues:
                    if not isinstance(issue, dict) or any(
                        field not in issue or issue[field] in (None, "")
                        for field in issue_required
                    ):
                        blockers.append(f"{task_id}: linked issue provenance incomplete")
                        break
                    issue_url = issue.get("url") if isinstance(issue, dict) else None
                    issue_parsed = urlparse(issue_url) if isinstance(issue_url, str) else None
                    issue_host = issue_parsed.netloc if issue_parsed else ""
                    relationship = issue.get("relationship") if isinstance(issue, dict) else None
                    if (
                        issue_parsed is None
                        or issue_parsed.scheme != "https"
                        or issue_host not in {"github.com", "code.djangoproject.com"}
                        or relationship not in {"fixes", "closes", "supersedes", "possible_closes"}
                    ):
                        blockers.append(f"{task_id}: linked issue URL is not first-party")
                        break

        if not re.fullmatch(r"[a-f0-9]{40}", str(task.get("base_commit", ""))):
            blockers.append(f"{task_id}: base commit hash missing or invalid")
        if task.get("base_commit_verified_in_image") is not True:
            blockers.append(f"{task_id}: base commit not verified in pinned image")
        if (
            not isinstance(task.get("license"), str)
            or task.get("license") not in {"MIT", "BSD-3-Clause", "Apache-2.0"}
            or not task.get("license_file_at_base")
            or not _is_sha256(task.get("license_file_sha256"))
            or task.get("license_evidence") != "verified_at_exact_base"
        ):
            blockers.append(f"{task_id}: license metadata or exact-base evidence missing")
        if not task.get("docker_image_ref") or not _is_sha256(
            task.get("docker_image_config_digest"), prefixed=True
        ):
            blockers.append(f"{task_id}: runtime image reference or config digest missing/invalid")
        spec_hash = hashlib.sha256(
            str(task.get("visible_test_spec", "")).encode("utf-8")
        ).hexdigest()
        if not _is_sha256(task.get("visible_test_spec_sha256")) or task.get("visible_test_spec_sha256") != spec_hash:
            blockers.append(f"{task_id}: visible test specification hash missing or mismatched")
        if task.get("visible_test_status") != "ready_and_baseline_verified":
            blockers.append(f"{task_id}: visible test baseline is not verified")
        if not _is_sha256(task.get("visible_test_sha256")):
            blockers.append(f"{task_id}: materialized visible test hash missing or invalid")

    artifacts = manifest.get("artifacts", {})
    if not isinstance(artifacts, dict):
        blockers.append("frozen artifacts must be an object")
        artifacts = {}
    for name, actual in _current_artifact_hashes().items():
        frozen = artifacts.get(name)
        if not _is_sha256(frozen):
            blockers.append(f"frozen artifact hash missing or invalid: {name}")
        elif frozen != actual:
            blockers.append(f"frozen artifact hash differs from current source: {name}")

    return blockers


def _worst_case_usd(input_tokens: int, output_tokens: int, steps: int) -> Decimal:
    return Decimal(steps) * (
        Decimal(input_tokens) * Decimal("0.30")
        + Decimal(output_tokens) * Decimal("1.20")
    ) / Decimal(1_000_000)


def plan(
    manifest: dict[str, Any],
    ledger: dict[str, Any],
    cases_root: Path,
    *,
    source_provenance_path: Path = DEFAULT_SOURCE_PROVENANCE,
) -> tuple[list[str], Decimal]:
    blockers = []
    blockers.extend(
        _validate_runnable_contract(
            manifest, source_provenance_path=source_provenance_path
        )
    )
    if ledger.get("account_usage_reconciled") is not True:
        blockers.append("usage ledger is not provider-reconciled")
    remaining = Decimal(str(ledger.get("estimated_remaining_usd", "0")))
    task_count = int(manifest.get("task_count", 0))
    limits = manifest["limits"]
    one_run = _worst_case_usd(
        int(limits["max_input_tokens_per_request"]),
        int(limits["max_completion_tokens"]),
        int(limits["max_steps"]),
    )
    total_reserve = one_run * task_count * 2
    if total_reserve > remaining:
        blockers.append(f"paired worst-case reserve ${total_reserve:.6f} exceeds remaining ${remaining:.6f}")
    if manifest.get("model_sha256") != _canonical_hash(manifest.get("model")):
        blockers.append("model manifest hash mismatch")
    for task in manifest.get("tasks", []):
        if not task.get("docker_image_config_digest"):
            blockers.append(f"{task['task_id']}: runtime image digest missing")
        if task.get("visible_test_status") != "ready_and_baseline_verified":
            blockers.append(f"{task['task_id']}: visible test baseline is not verified")
        case_path = cases_root / task["task_id"] / "case.json"
        if not case_path.is_file():
            blockers.append(f"{task['task_id']}: materialized visible-only case missing")
            continue
        case = _load_json(case_path)
        if case.get("case_id") != task["task_id"] or case.get("source_commit") != task["base_commit"]:
            blockers.append(f"{task['task_id']}: case identity or base commit mismatch")
        if not case.get("visible_test_sha256"):
            blockers.append(f"{task['task_id']}: visible test hash missing")
        if case.get("hidden_test_patch") or case.get("hidden_test_command"):
            blockers.append(f"{task['task_id']}: case contains private-oracle metadata")
        if (case_path.parent / "hidden_tests").exists():
            blockers.append(f"{task['task_id']}: private-oracle directory present")
    return blockers, total_reserve


def run_pairs(
    manifest: dict[str, Any],
    ledger: dict[str, Any],
    *,
    cases_root: Path,
    output_root: Path,
    work_root: Path,
) -> int:
    blockers, reserve = plan(manifest, ledger, cases_root)
    if blockers:
        print(f"未发送模型请求；CP-2 配对评测被预算/预检阻断。总预留=${reserve:.6f}")
        for blocker in blockers:
            print(f"- {blocker}")
        return 2

    from evals.compare_live_runs import compare_runs
    from evals.live_runner import run_live_evaluation

    limits = manifest["limits"]
    one_run_reserve = float(
        _worst_case_usd(
            int(limits["max_input_tokens_per_request"]),
            int(limits["max_completion_tokens"]),
            int(limits["max_steps"]),
        )
    )
    output_root.mkdir(parents=True, exist_ok=False)
    comparisons = []
    for index, task in enumerate(manifest["tasks"]):
        task_id = task["task_id"]
        variants = [False, True] if index % 2 == 0 else [True, False]
        paths: dict[bool, Path] = {}
        for enabled in variants:
            variant = "enabled" if enabled else "baseline"
            destination = output_root / variant / task_id
            run_live_evaluation(
                cases_root,
                destination,
                work_root / variant,
                {task_id},
                execution="docker",
                approve_host_tests=False,
                docker_image=task["docker_image_config_digest"],
                max_total_tokens=int(limits["max_total_tokens_per_task"]),
                max_elapsed=float(limits["max_elapsed_seconds"]),
                context_budget_chars=int(limits["context_budget_chars"]),
                max_steps=int(limits["max_steps"]),
                max_input_tokens_per_request=int(limits["max_input_tokens_per_request"]),
                max_completion_tokens=int(limits["max_completion_tokens"]),
                max_cost_reserve_usd=one_run_reserve,
                context_selector=enabled,
                verification_mode="visible_only",
            )
            paths[enabled] = destination / "results.csv"
        comparisons.append(compare_runs(paths[True], paths[False]))
        (output_root / "paired-results.json").write_text(
            json.dumps(comparisons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    accepted_pairs = sum(
        1 for item in comparisons
        if item["details"][0]["selector_accepted"] and item["details"][0]["baseline_accepted"]
    )
    print(f"配对任务={len(comparisons)}；两组均通过={accepted_pairs}；失败轨迹保存在 {output_root}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "ledger", "plan", "run"))
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--reports", type=Path, default=REPORTS_ROOT)
    parser.add_argument("--cases", type=Path, default=ROOT / "evals/public_cases/cp2/cases")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/cp2-paired-visible")
    parser.add_argument("--work", type=Path, default=ROOT / "reports/cp2-paired-visible/workspaces")
    args = parser.parse_args()

    if args.action == "freeze":
        if args.manifest.exists():
            raise FileExistsError(f"refusing to overwrite frozen benchmark: {args.manifest}")
        data = freeze_manifest(args.selection)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"冻结 {data['task_count']} 题 / {data['repository_count']} 个仓库；{data['freeze_status']}")
        return 0
    if args.action == "ledger":
        if args.ledger.exists():
            raise FileExistsError(f"refusing to overwrite budget ledger: {args.ledger}")
        ledger = build_budget_ledger(args.reports)
        args.ledger.parent.mkdir(parents=True, exist_ok=True)
        args.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已记账：usage=${ledger['known_cumulative_estimated_cost_usd']}；remaining=${ledger['estimated_remaining_usd']}")
        return 0

    manifest = _load_json(args.manifest)
    ledger = _load_json(args.ledger)
    if args.action == "plan":
        blockers, reserve = plan(manifest, ledger, args.cases)
        print(f"CP-2：{manifest['task_count']} 题，5 仓；双配置最坏费用预留=${reserve:.6f}；余额=${ledger['estimated_remaining_usd']}")
        for blocker in blockers:
            print(f"阻断：{blocker}")
        return 2 if blockers else 0
    return run_pairs(manifest, ledger, cases_root=args.cases, output_root=args.output, work_root=args.work)


if __name__ == "__main__":
    raise SystemExit(main())
