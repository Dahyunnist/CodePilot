import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from evals.cp2_benchmark import (
    AUTHORIZED_CAP_USD,
    DEFAULT_MANIFEST,
    DEFAULT_BUDGET_SUBSET,
    DEFAULT_SELECTION,
    DEFAULT_SOURCE_PROVENANCE,
    LIMITS,
    REPORTS_ROOT,
    TASK_IDS,
    _current_artifact_hashes,
    _canonical_hash,
    _case_materialization_blockers,
    _campaign_budget,
    _validate_runnable_contract,
    build_budget_ledger,
    build_budget_subset_manifest,
    freeze_manifest,
    plan,
    run_pairs,
    validate_budget_ledger,
)


def test_budget_ledger_deduplicates_same_run_across_csvs(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    header = "run_id,case_id,cost_usd_estimate\n"
    (reports / "run-a").mkdir()
    (reports / "run-b").mkdir()
    (reports / "run-a" / "results.csv").write_text(header + "run-1,case-a,0.004\n", encoding="utf-8")
    (reports / "run-b" / "results.csv").write_text(header + "run-1,case-a,0.004\n", encoding="utf-8")

    ledger = build_budget_ledger(reports)

    assert ledger["unique_positive_cost_runs"] == 1
    assert ledger["duplicate_identity_rows"] == 1
    assert ledger["known_cumulative_estimated_cost_usd"] == "0.004000"


def test_budget_ledger_quarantines_rows_without_run_id(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "run").mkdir()
    (reports / "run" / "results.csv").write_text(
        "run_id,case_id,cost_usd_estimate\n,case-a,0.004\n",
        encoding="utf-8",
    )

    ledger = build_budget_ledger(reports)

    assert ledger["unique_positive_cost_runs"] == 0
    assert ledger["quarantined_missing_run_id_rows"] == 1
    assert ledger["quarantined_missing_run_id_cost_usd"] == "0.004000"
    assert ledger["spendable_remaining_usd"] is None


def test_budget_ledger_deduplicates_request_ids_when_run_id_is_absent(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    header = "run_id,request_id,case_id,cost_usd_estimate\n"
    for folder in ("run-a", "run-b"):
        (reports / folder).mkdir()
        (reports / folder / "results.csv").write_text(
            header + ",request-1,case-a,0.002\n", encoding="utf-8"
        )

    ledger = build_budget_ledger(reports)

    assert ledger["unique_positive_cost_runs"] == 0
    assert ledger["unique_positive_cost_requests"] == 1
    assert ledger["duplicate_identity_rows"] == 1
    assert ledger["known_cumulative_estimated_cost_usd"] == "0.002000"


def test_budget_ledger_quarantines_partial_even_if_run_is_in_csv(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    partial_dir = reports / "cp4-live-pilot-20261024"
    partial_dir.mkdir(parents=True)
    (reports / "run").mkdir()
    (reports / "run" / "results.csv").write_text(
        "run_id,case_id,cost_usd_estimate\nrun-1,case-a,0.004\n",
        encoding="utf-8",
    )
    (partial_dir / "partial-django-none.json").write_text(
        json.dumps({"run_id": "run-1", "cost_usd_estimate": "0.004"}),
        encoding="utf-8",
    )

    ledger = build_budget_ledger(reports)

    assert ledger["known_cumulative_estimated_cost_usd"] == "0.004000"
    assert ledger["partial_record_status"] == "unknown_overlap_quarantined"
    assert ledger["partial_record_cost_usd"] == "0.004000"
    assert ledger["spendable_remaining_usd"] is None


def test_budget_ledger_without_raw_csv_or_balance_stays_unknown(tmp_path: Path) -> None:
    ledger = build_budget_ledger(tmp_path / "missing-reports")

    assert ledger["result_csv_count"] == 0
    assert ledger["provider_balance_status"] == "unknown"
    assert ledger["estimated_remaining_usd"] is None
    assert ledger["spendable_remaining_usd"] is None


def _materialized_case(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    case_dir = tmp_path / "c"
    repo = case_dir / "repo"
    visible = case_dir / "visible_tests" / "tests"
    repo_file = repo / "django" / "__init__.py"
    visible_repo_test = repo / "tests" / "t.py"
    visible_file = visible / "t.py"
    repo_file.parent.mkdir(parents=True)
    visible_repo_test.parent.mkdir(parents=True)
    visible_file.parent.mkdir(parents=True)
    repo_file.write_text("# public base\n", encoding="utf-8")
    test_content = "def test_public_regression(): pass\n"
    visible_file.write_text(test_content, encoding="utf-8")
    visible_repo_test.write_text(test_content, encoding="utf-8")
    manifest = {
        "case_id": "django__django-10924",
        "files": {"django/__init__.py": hashlib.sha256(repo_file.read_bytes()).hexdigest()},
        "source_commit": "a" * 40,
        "source_tree_sha": "b" * 40,
    }
    manifest_path = case_dir / "source-files.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    case = {
        "case_id": "django__django-10924",
        "source_commit": manifest["source_commit"],
        "source_tree_sha": manifest["source_tree_sha"],
        "source_file_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "visible_test_sha256": hashlib.sha256(visible_file.read_bytes()).hexdigest(),
        "visible_test_files": ["tests/t.py"],
    }
    return case_dir, case


def test_cp2_case_materialization_accepts_exact_public_base_and_visible_test(tmp_path: Path):
    case_dir, case = _materialized_case(tmp_path)

    assert _case_materialization_blockers(case_dir, case) == []


def test_cp2_case_materialization_rejects_added_or_changed_agent_files(tmp_path: Path):
    case_dir, case = _materialized_case(tmp_path)
    (case_dir / "repo" / "gold.patch").write_text("sentinel only\n", encoding="utf-8")
    (case_dir / "repo" / "django" / "__init__.py").write_text("changed\n", encoding="utf-8")

    blockers = _case_materialization_blockers(case_dir, case)

    assert any("file inventory differs" in item for item in blockers)
    assert any("base source file differs" in item for item in blockers)


def test_cp2_case_materialization_rejects_oracle_metadata(tmp_path: Path):
    case_dir, case = _materialized_case(tmp_path)
    case["gold_patch"] = "sentinel only"
    case["patches"] = [{"path": "django/__init__.py"}]

    blockers = _case_materialization_blockers(case_dir, case)

    assert "case contains forbidden oracle field: gold_patch" in blockers
    assert "case contains forbidden oracle field: patches" in blockers


def test_cp2_case_materialization_allows_hashed_pytest_runtime_version(tmp_path: Path):
    case_dir, case = _materialized_case(tmp_path)
    generated_path = "src/_pytest/_version.py"
    generated_file = case_dir / "repo" / generated_path
    generated_file.parent.mkdir(parents=True)
    generated_file.write_text("__version__ = '4.5.1.dev40'\n", encoding="utf-8")
    inventory_path = case_dir / "source-files.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    generated_sha256 = hashlib.sha256(generated_file.read_bytes()).hexdigest()
    inventory["generated_files"] = {generated_path: generated_sha256}
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    case["generated_version_sha256"] = generated_sha256
    case["source_file_manifest_sha256"] = hashlib.sha256(
        inventory_path.read_bytes()
    ).hexdigest()

    assert _case_materialization_blockers(case_dir, case) == []


def test_cp2_case_materialization_rejects_drifted_pytest_runtime_version(tmp_path: Path):
    case_dir, case = _materialized_case(tmp_path)
    generated_path = "src/_pytest/_version.py"
    generated_file = case_dir / "repo" / generated_path
    generated_file.parent.mkdir(parents=True)
    generated_file.write_text("__version__ = '4.5.1.dev40'\n", encoding="utf-8")
    inventory_path = case_dir / "source-files.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    generated_sha256 = hashlib.sha256(generated_file.read_bytes()).hexdigest()
    inventory["generated_files"] = {generated_path: generated_sha256}
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    case["generated_version_sha256"] = "0" * 64
    case["source_file_manifest_sha256"] = hashlib.sha256(
        inventory_path.read_bytes()
    ).hexdigest()

    blockers = _case_materialization_blockers(case_dir, case)

    assert "generated file inventory differs from approved version metadata" in blockers


def test_cp2_manifest_freezes_selected_scope_and_artifacts():
    manifest = freeze_manifest(DEFAULT_SELECTION)

    assert manifest["task_count"] == 15
    assert manifest["repository_count"] == 5
    assert manifest["dataset"]["gold_policy"] == "SHA-256 only; no patch content in agent workspace"
    assert manifest["model_sha256"] == _canonical_hash(manifest["model"])
    assert all("gold_patch" not in task for task in manifest["tasks"])
    assert all(task["gold_source"].endswith("gold content not read or exposed") for task in manifest["tasks"])


def test_checked_in_cp2_freeze_has_consistent_task_statement_and_gold_hashes():
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    selection = json.loads(DEFAULT_SELECTION.read_text(encoding="utf-8"))
    selected = {item["task_id"]: item for item in selection["tasks"]}
    tasks = manifest["tasks"]
    record_hashes = []
    gold_hashes = {}

    assert [item["task_id"] for item in tasks] == list(TASK_IDS)
    assert len({item["task_id"] for item in tasks}) == len(TASK_IDS)
    assert manifest["dataset"]["selection_manifest_sha256"] == hashlib.sha256(
        DEFAULT_SELECTION.read_bytes()
    ).hexdigest()
    for task in tasks:
        source = selected[task["task_id"]]
        assert task["problem_statement"] == source["problem_statement"]
        assert task["problem_statement_sha256"] == source["problem_statement_sha256"]
        assert hashlib.sha256(task["problem_statement"].encode("utf-8")).hexdigest() == task[
            "problem_statement_sha256"
        ]
        assert task["gold_patch_sha256"] == source["gold_patch_sha256"]
        record = dict(task)
        record_hash = record.pop("task_record_sha256")
        assert record_hash == _canonical_hash(record)
        record_hashes.append(record_hash)
        gold_hashes[task["task_id"]] = task["gold_patch_sha256"]

    assert manifest["task_record_sha256"] == _canonical_hash(record_hashes)
    assert manifest["gold_sha256"] == _canonical_hash(gold_hashes)
    assert all("gold_patch" not in task for task in tasks)


def test_cp2_preflight_does_not_create_output_or_call_live_runner(tmp_path, monkeypatch, capsys):
    from evals import live_runner

    calls = []

    def forbidden_model_path(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("preflight must not enter live runner")

    monkeypatch.setattr(live_runner, "run_live_evaluation", forbidden_model_path)
    output_root = tmp_path / "unique-output"
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    ledger = build_budget_ledger(REPORTS_ROOT)

    status = run_pairs(
        manifest,
        ledger,
        cases_root=tmp_path / "missing-cases",
        output_root=output_root,
        work_root=tmp_path / "work",
    )

    output = capsys.readouterr().out
    assert status == 2
    assert "未发送模型请求" in output
    assert calls == []
    assert not output_root.exists()
    assert manifest["task_count"] * 2 == 30
    assert AUTHORIZED_CAP_USD == Decimal("0.50")
    assert LIMITS["max_steps"] == 8


def test_cp2_pair_driver_retains_success_and_failure_traces(tmp_path, monkeypatch):
    from evals import compare_live_runs, live_runner
    import evals.cp2_benchmark as cp2

    manifest = {
        "limits": {
            "max_input_tokens_per_request": 22_000,
            "max_completion_tokens": 512,
            "max_steps": 8,
            "max_total_tokens_per_task": 20_000,
            "context_budget_chars": 8_000,
            "max_elapsed_seconds": 180,
        },
        "tasks": [{"task_id": "offline-case", "docker_image_config_digest": "sha256:test"}],
    }
    monkeypatch.setattr(cp2, "plan", lambda *args, **kwargs: ([], Decimal("0.01")))
    runs = []

    def fake_run(cases_root, output_root, work_root, case_ids, **kwargs):
        output_root.mkdir(parents=True)
        accepted = kwargs["context_selector"] is False
        trace = output_root / "offline-trace.jsonl"
        trace.write_text(json.dumps({"event": "run_finished", "accepted": accepted}) + "\n")
        (output_root / "results.csv").write_text("accepted\n" + str(accepted) + "\n")
        runs.append((accepted, trace))
        return []

    monkeypatch.setattr(live_runner, "run_live_evaluation", fake_run)
    monkeypatch.setattr(
        compare_live_runs,
        "compare_runs",
        lambda selector, baseline: {
            "details": [{"selector_accepted": False, "baseline_accepted": True}],
            "trace_files_retained": True,
        },
    )
    output_root = tmp_path / "new-pair-output"

    status = run_pairs(
        manifest,
        {},
        cases_root=tmp_path / "cases",
        output_root=output_root,
        work_root=tmp_path / "work",
    )

    assert status == 0
    assert len(runs) == 2
    assert {accepted for accepted, _ in runs} == {True, False}
    assert all(path.is_file() and json.loads(path.read_text()) for _, path in runs)
    paired = json.loads((output_root / "paired-results.json").read_text(encoding="utf-8"))
    assert paired[0]["details"][0] == {
        "selector_accepted": False,
        "baseline_accepted": True,
    }


def test_cp2_pair_driver_refuses_existing_output_path_before_runner(tmp_path, monkeypatch):
    from evals import live_runner
    import evals.cp2_benchmark as cp2

    monkeypatch.setattr(cp2, "plan", lambda *args, **kwargs: ([], Decimal("0.01")))
    calls = []
    monkeypatch.setattr(live_runner, "run_live_evaluation", lambda *a, **k: calls.append(a))
    output_root = tmp_path / "already-used"
    output_root.mkdir()
    sentinel = output_root / "keep.txt"
    sentinel.write_text("prior run", encoding="utf-8")
    manifest = {
        "limits": LIMITS,
        "tasks": [{"task_id": "offline-case", "docker_image_config_digest": "sha256:test"}],
    }

    with pytest.raises(FileExistsError):
        run_pairs(
            manifest,
            {},
            cases_root=tmp_path / "cases",
            output_root=output_root,
            work_root=tmp_path / "work",
        )

    assert calls == []
    assert sentinel.read_text(encoding="utf-8") == "prior run"


def test_cp2_freeze_rejects_missing_selected_task(tmp_path: Path):
    selection = json.loads(DEFAULT_SELECTION.read_text(encoding="utf-8"))
    selection["tasks"] = [task for task in selection["tasks"] if task["task_id"] != "django__django-10924"]
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(selection), encoding="utf-8")

    with pytest.raises(ValueError, match="selection lacks selected tasks"):
        freeze_manifest(selection_path)


def test_cp2_plan_blocks_unverified_budget_and_missing_runtime(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    ledger = {
        "account_usage_reconciled": False,
        "estimated_remaining_usd": "0.01",
    }

    blockers, reserve = plan(manifest, ledger, tmp_path / "cases")

    assert reserve > 0
    assert any("not provider-reconciled" in item for item in blockers)
    assert any("spendable budget is unknown" in item for item in blockers)
    assert any("worst-case reserve" in item for item in blockers)
    assert any("runtime image digest missing" in item for item in blockers)
    assert any("visible test baseline is not verified" in item for item in blockers)


def test_cp2_budget_subset_is_hash_pinned_three_repo_minimum():
    parent = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    subset = json.loads(DEFAULT_BUDGET_SUBSET.read_text(encoding="utf-8"))
    regenerated = build_budget_subset_manifest(parent)
    payload = dict(subset)
    stored_hash = payload.pop("subset_sha256")

    assert subset == regenerated
    assert stored_hash == _canonical_hash(payload)
    assert subset["task_count"] == 3
    assert subset["repository_count"] == 3
    assert subset["minimum_independent_tasks"] == 3
    assert len({task["repo"] for task in subset["tasks"]}) == 3
    assert all("gold_patch" not in task for task in subset["tasks"])
    assert subset["budget"]["max_model_requests"] == 48
    assert subset["budget"]["peak_worst_case_reserve_usd"] == "0.3462912"


def test_cp2_budget_request_ceiling_uses_frozen_task_rows_not_claimed_count():
    manifest = {
        "task_count": 900,
        "tasks": [{"task_id": "one"}, {"task_id": "two"}],
        "limits": {
            "max_input_tokens_per_request": 22_000,
            "max_completion_tokens": 512,
            "max_steps": 8,
        },
    }

    request_count, reserve = _campaign_budget(manifest)

    assert request_count == 32
    assert reserve == Decimal("0.2308608")


def test_cp2_exact_base_smoke_report_matches_budget_subset_and_is_not_agent_success():
    root = DEFAULT_BUDGET_SUBSET.parent
    report = json.loads(
        (root / "smoke" / "baseline-2026-11-15.json").read_text(encoding="utf-8")
    )
    subset = json.loads(DEFAULT_BUDGET_SUBSET.read_text(encoding="utf-8"))
    cases = {task["task_id"]: task for task in subset["tasks"]}

    assert report["model_calls"] == 0
    assert report["network_enabled"] is False
    assert report["agent_repair_attempted"] is False
    assert {row["task_id"] for row in report["results"]} == set(cases)
    for row in report["results"]:
        case = json.loads(
            (root / "cases" / row["task_id"] / "case.json").read_text(encoding="utf-8")
        )
        assert row["command"] == case["test_command"]
        assert row["image_config_digest"] == cases[row["task_id"]]["docker_image_config_digest"]
        assert row["base_commit"] == cases[row["task_id"]]["base_commit"]
        assert row["visible_test_sha256"] == case["visible_test_sha256"]
        assert row["outcome"] == "expected_baseline_failure"
        assert row["exit_code"] != 0
        assert row["agent_repair_result"] is None


def test_cp2_budget_gate_requires_reconciled_usage_and_provider_balance():
    reserve = Decimal("0.3462912")
    ledger = {
        "account_usage_reconciled": False,
        "usage_evidence_status": "missing_raw_csv",
        "provider_balance_status": "unknown",
        "spendable_remaining_usd": "100",
        "known_cumulative_estimated_cost_usd": "0.01",
    }

    blockers = validate_budget_ledger(ledger, reserve)

    assert "usage ledger is not provider-reconciled" in blockers
    assert "provider balance is unknown or unverified" in blockers
    assert any("missing/invalid" in blocker for blocker in blockers)
    assert "provider usage evidence file missing, unsafe, or hash-mismatched" in blockers
    assert "provider balance evidence file missing, unsafe, or hash-mismatched" in blockers


@pytest.mark.parametrize(
    ("cumulative", "provider_balance", "expected"),
    [
        ("0.10", "0.40", None),
        ("0.20", "0.40", "cumulative spend"),
        ("0.10", "0.30", "provider balance"),
    ],
)
def test_cp2_budget_gate_checks_cap_headroom_and_single_campaign_reserve(
    cumulative: str, provider_balance: str, expected: str | None, tmp_path: Path, monkeypatch
):
    import evals.cp2_benchmark as cp2

    monkeypatch.setattr(cp2, "ROOT", tmp_path)
    usage_evidence = tmp_path / "evidence" / "usage.json"
    balance_evidence = tmp_path / "evidence" / "balance.json"
    fx_evidence = tmp_path / "evidence" / "fx.json"
    usage_evidence.parent.mkdir()
    usage = {
        "scope": "project_api_key", "api_key_name": "project-key",
        "history_complete": True, "period_start": "2026-01-01", "period_end": "2026-01-31",
        "amount": str(Decimal(cumulative) / Decimal("0.01")), "currency": "CNY",
    }
    balance = {"amount": str(Decimal(provider_balance) / Decimal("0.01")), "currency": "CNY"}
    fx = {"policy_id": "test-fx", "method": "test-rate", "rate_to_usd": "0.01",
          "source": "synthetic test fixture", "effective_date": "2026-01-31"}
    usage_evidence.write_text(json.dumps(usage), encoding="utf-8")
    balance_evidence.write_text(json.dumps(balance), encoding="utf-8")
    fx_evidence.write_text(json.dumps(fx), encoding="utf-8")
    reserve = Decimal("0.3462912")
    ledger = {
        "account_usage_reconciled": True,
        "usage_evidence_status": "provider_reconciled",
        "provider_balance_status": "verified",
        "provider_balance_usd": provider_balance,
        "provider_cumulative_spend_usd": cumulative,
        "provider_balance_amount": balance["amount"],
        "provider_balance_currency": "CNY",
        "provider_cumulative_spend_amount": usage["amount"],
        "provider_cumulative_spend_currency": "CNY",
        "usage_scope": "project_api_key",
        "usage_api_key_name": "project-key",
        "provider_usage_history_complete": True,
        "provider_usage_period_start": "2026-01-01",
        "provider_usage_period_end": "2026-01-31",
        "fx_policy_id": "test-fx",
        "fx_method": "test-rate",
        "fx_rate_to_usd": "0.01",
        "fx_source": "synthetic test fixture",
        "fx_effective_date": "2026-01-31",
        "authorized_project_cap_usd": "999.00",
        "provider_usage_evidence_path": "evidence/usage.json",
        "provider_usage_evidence_sha256": hashlib.sha256(usage_evidence.read_bytes()).hexdigest(),
        "provider_balance_evidence_path": "evidence/balance.json",
        "provider_balance_evidence_sha256": hashlib.sha256(balance_evidence.read_bytes()).hexdigest(),
        "provider_fx_policy_evidence_path": "evidence/fx.json",
        "provider_fx_policy_evidence_sha256": hashlib.sha256(fx_evidence.read_bytes()).hexdigest(),
    }

    blockers = cp2.validate_budget_ledger(ledger, reserve)

    if expected is None:
        assert blockers == []
        account_only = dict(ledger, usage_scope="account")
        assert "provider usage is not attributed to an explicit project API key" in cp2.validate_budget_ledger(
            account_only, reserve
        )
        incomplete = dict(ledger, provider_usage_history_complete=False)
        assert "provider usage history coverage is incomplete" in cp2.validate_budget_ledger(
            incomplete, reserve
        )
        wrong_fx = dict(ledger, fx_rate_to_usd="0.02")
        assert "provider amounts, currencies, or FX conversion are missing/invalid/inconsistent" in cp2.validate_budget_ledger(
            wrong_fx, reserve
        )
    else:
        assert any(expected in blocker for blocker in blockers)


def test_cp2_budget_gate_rejects_evidence_path_escape(tmp_path: Path, monkeypatch):
    import evals.cp2_benchmark as cp2

    monkeypatch.setattr(cp2, "ROOT", tmp_path)
    usage = tmp_path / "usage.json"
    balance = tmp_path / "balance.json"
    usage.write_text("{}", encoding="utf-8")
    balance.write_text("{}", encoding="utf-8")
    ledger = {
        "account_usage_reconciled": True,
        "usage_evidence_status": "provider_reconciled",
        "provider_balance_status": "verified",
        "provider_balance_usd": "0.40",
        "provider_cumulative_spend_usd": "0.10",
        "provider_usage_evidence_path": "../usage.json",
        "provider_usage_evidence_sha256": hashlib.sha256(usage.read_bytes()).hexdigest(),
        "provider_balance_evidence_path": "balance.json",
        "provider_balance_evidence_sha256": hashlib.sha256(balance.read_bytes()).hexdigest(),
    }

    blockers = cp2.validate_budget_ledger(ledger, Decimal("0.3462912"))

    assert "provider usage evidence file missing, unsafe, or hash-mismatched" in blockers


def test_cp2_budget_precheck_is_read_only_when_ledger_is_missing(tmp_path: Path, monkeypatch, capsys):
    import evals.cp2_benchmark as cp2

    reports = tmp_path / "empty-reports"
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cp2_benchmark",
            "budget-plan",
            "--reports",
            str(reports),
            "--ledger",
            str(ledger_path),
        ],
    )

    status = cp2.main()

    output = capsys.readouterr().out
    assert status == 2
    assert "不调用模型" in output
    assert "provider balance is unknown or unverified" in output
    assert not ledger_path.exists()
    assert not reports.exists()


def test_cp2_plan_rejects_model_manifest_tampering(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    manifest["model"]["configured_model_alias"] = "tampered"
    ledger = {"account_usage_reconciled": True, "estimated_remaining_usd": "100"}

    blockers, _ = plan(manifest, ledger, tmp_path / "cases")

    assert "model manifest hash mismatch" in blockers


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("public_reference", None, "source PR link missing, invalid, or inconsistent"),
        ("license", None, "license metadata or exact-base evidence missing"),
        ("license_file_sha256", None, "license metadata or exact-base evidence missing"),
        ("docker_image_config_digest", None, "runtime image digest missing"),
        ("visible_test_sha256", None, "materialized visible test hash missing or invalid"),
    ],
)
def test_cp2_plan_stays_blocked_when_source_license_digest_or_test_hash_missing(
    tmp_path: Path, field: str, value: object, expected: str
):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    target = next(item for item in manifest["tasks"] if item["task_id"] == "pytest-dev__pytest-5103")
    target[field] = value
    ledger = {"account_usage_reconciled": True, "estimated_remaining_usd": "100"}

    blockers, _ = plan(manifest, ledger, tmp_path / "cases")

    assert any(expected in blocker for blocker in blockers)


def test_cp2_plan_rejects_missing_or_drifted_evaluator_hash(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    manifest["artifacts"]["paired_driver_sha256"] = "0" * 64
    ledger = {"account_usage_reconciled": True, "estimated_remaining_usd": "100"}

    blockers, _ = plan(manifest, ledger, tmp_path / "cases")

    assert "frozen artifact hash differs from current source: paired_driver_sha256" in blockers


def test_frozen_manifest_records_current_evaluator_hashes():
    manifest = freeze_manifest(DEFAULT_SELECTION)

    assert manifest["artifacts"] == _current_artifact_hashes()


def test_source_provenance_covers_frozen_tasks_and_matches_pull_request_links():
    manifest = freeze_manifest(DEFAULT_SELECTION)
    provenance = json.loads(DEFAULT_SOURCE_PROVENANCE.read_text(encoding="utf-8"))
    rows = {item["task_id"]: item for item in provenance["tasks"]}

    assert set(rows) == {item["task_id"] for item in manifest["tasks"]}
    for task in manifest["tasks"]:
        source = rows[task["task_id"]]
        assert source["repo"] == task["repo"]
        assert source["source_pr_url"] == task["public_reference"]
        assert source["pr_status"] == "merged"
        assert source["linked_issues"]


def test_cp2_plan_blocks_when_issue_pr_provenance_is_missing(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    provenance = json.loads(DEFAULT_SOURCE_PROVENANCE.read_text(encoding="utf-8"))
    first = provenance["tasks"][0]
    first["linked_issues"] = []
    provenance_path = tmp_path / "provenance.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    ledger = {"account_usage_reconciled": True, "estimated_remaining_usd": "100"}

    blockers, _ = plan(
        manifest, ledger, tmp_path / "cases", source_provenance_path=provenance_path
    )

    assert f"{first['task_id']}: linked issue provenance missing" in blockers


def test_cp2_plan_blocks_when_provenance_file_is_absent(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    ledger = {"account_usage_reconciled": True, "estimated_remaining_usd": "100"}

    blockers, _ = plan(
        manifest, ledger, tmp_path / "cases",
        source_provenance_path=tmp_path / "missing-provenance.json",
    )

    assert "source provenance manifest missing or invalid" in blockers


def test_cp2_visible_test_and_runtime_status_remain_fail_closed():
    manifest = freeze_manifest(DEFAULT_SELECTION)

    assert len(manifest["tasks"]) == 15
    assert all(
        task["visible_test_status"] == "spec_frozen_test_not_materialized_or_run"
        for task in manifest["tasks"]
    )
    missing_images = [
        task["task_id"] for task in manifest["tasks"]
        if task["docker_image_config_digest"] is None
    ]
    assert missing_images == ["pydata__xarray-4493"]


def test_freeze_does_not_claim_exact_base_license_or_commit_verification():
    manifest = freeze_manifest(DEFAULT_SELECTION)
    provenance = json.loads(DEFAULT_SOURCE_PROVENANCE.read_text(encoding="utf-8"))

    assert all(task["base_commit_verified_in_image"] is False for task in manifest["tasks"])
    assert all(task["license_file_at_base"] is None for task in manifest["tasks"])
    assert all(task["license_file_sha256"] is None for task in manifest["tasks"])
    assert all(task["license_evidence"] == "pending_exact_base_verification" for task in manifest["tasks"])
    assert all(item["exact_base_verification"] == {"status": "pending"} for item in provenance["tasks"])

    blockers = _validate_runnable_contract(manifest)
    assert sum("exact-base image/license evidence is pending" in item for item in blockers) == 15


def test_cp2_plan_rejects_exact_base_evidence_path_escape(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    task = manifest["tasks"][0]
    task["base_commit_verified_in_image"] = True
    task["license_file_at_base"] = "LICENSE"
    task["license_file_sha256"] = "a" * 64
    task["license_evidence"] = "verified_at_exact_base"
    record = dict(task)
    record.pop("task_record_sha256")
    task["task_record_sha256"] = _canonical_hash(record)
    manifest["task_record_sha256"] = _canonical_hash(
        [item["task_record_sha256"] for item in manifest["tasks"]]
    )

    provenance = json.loads(DEFAULT_SOURCE_PROVENANCE.read_text(encoding="utf-8"))
    evidence = provenance["tasks"][0]["exact_base_verification"]
    evidence.update(
        {
            "status": "verified",
            "image_config_digest": task["docker_image_config_digest"],
            "observed_base_commit": task["base_commit"],
            "license_file_at_base": task["license_file_at_base"],
            "license_file_sha256": task["license_file_sha256"],
            "license": task["license"],
            "evidence_path": "../outside.json",
            "evidence_sha256": "0" * 64,
        }
    )
    provenance_path = tmp_path / "source-provenance.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")

    blockers = _validate_runnable_contract(
        manifest, source_provenance_path=provenance_path
    )

    assert f"{task['task_id']}: exact-base evidence file missing, unsafe, or mismatched" in blockers
