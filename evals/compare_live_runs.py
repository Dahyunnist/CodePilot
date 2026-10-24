"""Compare paired live-model CSV runs across one controlled feature change."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import median


def compare_runs(
    selector_csv: Path,
    baseline_csv: Path,
    *,
    dimension: str = "context_selector",
) -> dict[str, object]:
    selector_rows = _read_rows(selector_csv)
    baseline_rows = _read_rows(baseline_csv)
    selector_manifest = _read_manifest(selector_csv)
    baseline_manifest = _read_manifest(baseline_csv)
    if dimension not in {"context_selector", "skill"}:
        raise ValueError("dimension must be context_selector or skill")
    if selector_manifest.get("model") != baseline_manifest.get("model"):
        raise ValueError("paired runs must use the same model")
    if dimension == "context_selector":
        if selector_manifest.get("context_selector_enabled") is not True:
            raise ValueError("selector run manifest must enable ContextSelector")
        if baseline_manifest.get("context_selector_enabled") is not False:
            raise ValueError("baseline run manifest must disable ContextSelector")
        if selector_manifest.get("context_selector_version") != "layered-context-v1":
            raise ValueError("selector manifest must pin the layered ContextSelector version")
        if baseline_manifest.get("context_selector_version") != "baseline":
            raise ValueError("baseline manifest must pin the baseline selector version")
        if selector_manifest.get("skill_id") != baseline_manifest.get("skill_id"):
            raise ValueError("context-selector pairs must use the same skill_id")
        selector_label, baseline_label = "enabled", "baseline"
    else:
        selector_skill = selector_manifest.get("skill_id")
        baseline_skill = baseline_manifest.get("skill_id")
        if not selector_skill or selector_skill == "none":
            raise ValueError("skill selector manifest must enable one named Skill")
        if baseline_skill != "none":
            raise ValueError("skill baseline manifest must disable Skill")
        if selector_manifest.get("context_selector_enabled") is not baseline_manifest.get(
            "context_selector_enabled"
        ) or selector_manifest.get("context_selector_version") != baseline_manifest.get(
            "context_selector_version"
        ):
            raise ValueError("skill pairs must use the same ContextSelector setting")
        selector_label, baseline_label = f"skill:{selector_skill}", "skill:none"
    paired_configuration = (
        "api_endpoint",
        "temperature",
        "agent_git_sha",
        "agent_worktree_diff_sha256",
        "execution",
        "docker_image",
        "max_total_tokens",
        "max_elapsed_seconds",
        "context_budget_chars",
        "max_steps",
        "max_input_tokens_per_request",
        "max_completion_tokens",
        "max_cost_reserve_usd",
    )
    if dimension == "context_selector":
        paired_configuration += ("skill_id",)
    for key in paired_configuration:
        if key not in selector_manifest or key not in baseline_manifest:
            raise ValueError(f"paired manifests are missing required setting: {key}")
        if selector_manifest[key] != baseline_manifest[key]:
            raise ValueError(f"paired runs must use the same {key}")
    selector_cases = _case_hashes(selector_manifest)
    baseline_cases = _case_hashes(baseline_manifest)
    if selector_cases != baseline_cases:
        raise ValueError("paired runs must use identical case metadata hashes")
    if set(selector_rows) != set(selector_cases) or set(baseline_rows) != set(baseline_cases):
        raise ValueError("each paired CSV must contain exactly its manifest cases")
    common = sorted(selector_rows.keys() & baseline_rows.keys())
    if not common:
        raise ValueError("paired runs have no common case IDs")
    wins = losses = ties = 0
    cost_deltas: list[float] = []
    elapsed_deltas: list[float] = []
    details = []
    failure_pairs: dict[str, int] = {}
    for case_id in common:
        selected_variant = selector_rows[case_id].get("context_selector_variant")
        baseline_variant = baseline_rows[case_id].get("context_selector_variant")
        selected_expected = (
            "enabled" if selector_manifest.get("context_selector_enabled") else "baseline"
        )
        baseline_expected = (
            "enabled" if baseline_manifest.get("context_selector_enabled") else "baseline"
        )
        if selected_variant != selected_expected:
            raise ValueError(f"selector CSV has the wrong context variant for {case_id}")
        if baseline_variant != baseline_expected:
            raise ValueError(f"baseline CSV has the wrong context variant for {case_id}")
        if selector_rows[case_id].get("skill_id") != selector_manifest.get("skill_id"):
            raise ValueError(f"selector CSV has the wrong skill_id for {case_id}")
        if baseline_rows[case_id].get("skill_id") != baseline_manifest.get("skill_id"):
            raise ValueError(f"baseline CSV has the wrong skill_id for {case_id}")
        selector_cost = _metric_float(selector_rows[case_id], "cost_usd_estimate", case_id)
        baseline_cost = _metric_float(baseline_rows[case_id], "cost_usd_estimate", case_id)
        selector_elapsed = _metric_float(
            selector_rows[case_id], "evaluation_elapsed_ms", case_id
        )
        baseline_elapsed = _metric_float(
            baseline_rows[case_id], "evaluation_elapsed_ms", case_id
        )
        selected = _truth(selector_rows[case_id].get("accepted"))
        base = _truth(baseline_rows[case_id].get("accepted"))
        if selected and not base:
            wins += 1
        elif base and not selected:
            losses += 1
        else:
            ties += 1
        cost_delta = selector_cost - baseline_cost
        elapsed_delta = selector_elapsed - baseline_elapsed
        cost_deltas.append(cost_delta)
        elapsed_deltas.append(elapsed_delta)
        selected_failure = _failure_label(selector_rows[case_id])
        baseline_failure = _failure_label(baseline_rows[case_id])
        pair_label = f"selector={selected_failure};baseline={baseline_failure}"
        failure_pairs[pair_label] = failure_pairs.get(pair_label, 0) + 1
        details.append(
            {
                "case_id": case_id,
                "selector_accepted": selected,
                "baseline_accepted": base,
                "selector_failure": selected_failure,
                "baseline_failure": baseline_failure,
                "selector_agent_tests_passed": _truth(
                    selector_rows[case_id].get("agent_test_ok")
                ),
                "baseline_agent_tests_passed": _truth(
                    baseline_rows[case_id].get("agent_test_ok")
                ),
                "selector_visible_tests_passed": _truth(
                    selector_rows[case_id].get("independent_visible_ok")
                ),
                "baseline_visible_tests_passed": _truth(
                    baseline_rows[case_id].get("independent_visible_ok")
                ),
                "selector_hidden_tests_passed": _truth(
                    selector_rows[case_id].get("hidden_ok")
                ),
                "baseline_hidden_tests_passed": _truth(
                    baseline_rows[case_id].get("hidden_ok")
                ),
                "cost_delta_usd": round(cost_delta, 8),
                "elapsed_delta_ms": round(elapsed_delta, 1),
            }
        )
    return {
        "dimension": dimension,
        "selector_variant": selector_label,
        "baseline_variant": baseline_label,
        "model": selector_manifest["model"],
        "paired_cases": len(common),
        "selector_wins": wins,
        "baseline_wins": losses,
        "ties": ties,
        "mcnemar_exact_p": _mcnemar_exact_p(wins, losses),
        "failure_attribution_pairs": dict(sorted(failure_pairs.items())),
        "median_cost_delta_usd": median(cost_deltas),
        "median_elapsed_delta_ms": median(elapsed_deltas),
        "details": details,
    }


def _failure_label(row: dict[str, str]) -> str:
    """Keep strict task status distinct from post-stop independent tests."""
    failure_type = (row.get("failure_type") or "").strip() or "none"
    status = (row.get("status") or "").strip() or "unknown"
    if _truth(row.get("accepted")):
        return "strict_success"
    post_budget = (row.get("post_budget_verification") or "").strip()
    if post_budget and post_budget != "not_run":
        return f"{failure_type}:{status}:post_budget_{post_budget}"
    return f"{failure_type}:{status}"


def _read_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {row["case_id"]: row for row in csv.DictReader(stream)}


def _read_manifest(csv_path: Path) -> dict[str, object]:
    manifest_path = csv_path.parent / "run_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing run manifest: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _case_hashes(manifest: dict[str, object]) -> dict[str, object]:
    return {
        str(case["case_id"]): case["metadata_sha256"]
        for case in manifest.get("cases", [])
    }


def _truth(value: object) -> bool:
    return str(value).strip().casefold() in {"true", "1", "yes"}


def _metric_float(row: dict[str, str], key: str, case_id: str) -> float:
    value = row.get(key)
    if value is None or not value.strip():
        raise ValueError(f"paired case {case_id} is missing metric {key}")
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"paired case {case_id} has invalid metric {key}") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"paired case {case_id} has invalid metric {key}")
    return result


def _mcnemar_exact_p(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = min(wins, losses)
    probability = sum(math.comb(discordant, index) for index in range(tail + 1)) / (
        2**discordant
    )
    return min(1.0, 2 * probability)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selector", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--dimension",
        choices=("context_selector", "skill"),
        default="context_selector",
    )
    args = parser.parse_args()
    result = compare_runs(args.selector, args.baseline, dimension=args.dimension)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
