"""Score repair trajectories and audit offline policy-learning readiness."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    return str(value).strip().casefold() in {"true", "1", "yes"}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_splits(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for split in ("train", "validation", "test"):
        for case_id in data.get(split, []):
            if case_id in result:
                raise ValueError(f"case appears in multiple splits: {case_id}")
            result[case_id] = split
    return result


def read_trace(path_value: str) -> tuple[Counter[str], int]:
    if not path_value:
        return Counter(), 0
    path = Path(path_value)
    if not path.exists():
        return Counter(), 0
    counts: Counter[str] = Counter()
    policy_denials = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "tool_started":
            counts[str(event.get("tool", "unknown"))] += 1
        if (
            event.get("event") == "tool_finished"
            and event.get("error_type") == "PathPolicyError"
        ):
            policy_denials += 1
    return counts, policy_denials


def score_row(row: dict[str, Any], split: str) -> dict[str, Any]:
    status = str(row.get("status", ""))
    accepted = _bool(row.get("accepted")) is True
    tokens = int(_number(row.get("tokens")))
    elapsed_ms = int(_number(row.get("evaluation_elapsed_ms", row.get("elapsed_ms"))))
    tool_counts, policy_denials = read_trace(str(row.get("trace_file", "")))

    reward = 100.0 if accepted else 0.0
    penalties: dict[str, float] = {}
    if policy_denials:
        penalties["path_policy_denial"] = 100.0 * policy_denials
    if status == "budget_exceeded":
        penalties["budget_exceeded"] = 30.0
    elif status in {"max_steps", "max_elapsed"}:
        penalties["incomplete_run"] = 25.0
    if _bool(row.get("agent_test_ok")) is False:
        penalties["agent_tests_failed"] = 10.0
    if _bool(row.get("independent_visible_ok")) is False:
        penalties["visible_tests_failed"] = 20.0
    if _bool(row.get("hidden_ok")) is False:
        penalties["hidden_tests_failed"] = 20.0
    penalties["token_cost"] = min(20.0, tokens / 10_000 * 0.5)
    penalties["elapsed_time"] = min(10.0, elapsed_ms / 60_000)
    reward -= sum(penalties.values())

    return {
        "case_id": row.get("case_id", ""),
        "run_id": row.get("run_id", ""),
        "split": split,
        "status": status,
        "accepted": accepted,
        "reward": round(reward, 3),
        "tokens": tokens,
        "cost_usd_estimate": row.get("cost_usd_estimate", ""),
        "elapsed_ms": elapsed_ms,
        "path_policy_denials": policy_denials,
        "tool_calls": json.dumps(dict(sorted(tool_counts.items())), ensure_ascii=False),
        "penalties": json.dumps(penalties, sort_keys=True),
    }


def score_files(result_paths: Sequence[Path], split_path: Path) -> list[dict[str, Any]]:
    splits = load_splits(split_path)
    output: list[dict[str, Any]] = []
    for result_path in result_paths:
        with result_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                case_id = str(row.get("case_id", ""))
                output.append(score_row(row, splits.get(case_id, "unassigned")))
    return output


def write_report(rows: list[dict[str, Any]], output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    columns = [
        "case_id", "run_id", "split", "status", "accepted", "reward", "tokens",
        "cost_usd_estimate", "elapsed_ms", "path_policy_denials", "tool_calls", "penalties",
    ]
    with (output_root / "scores.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unique_cases: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        buckets[str(row["split"])].append(row)
        unique_cases[str(row["split"])].add(str(row["case_id"]))
    total_accepts = sum(row["accepted"] is True for row in rows)
    total_cost = sum(_number(row["cost_usd_estimate"]) for row in rows)
    total_tokens = sum(int(row["tokens"]) for row in rows)
    total_denials = sum(int(row["path_policy_denials"]) for row in rows)
    lines = [
        "# S10 轨迹评分与离线策略审计",
        "",
        f"- 轨迹数：{len(rows)}；唯一案例数：{len({str(row['case_id']) for row in rows})}",
        f"- 完整验收：{total_accepts}/{len(rows)}；总 Token：{total_tokens:,}；估算费用：${total_cost:.6f}",
        f"- 路径策略拒绝次数：{total_denials}",
        "- 分数：完整验收 +100；预算耗尽 -30；步数/时间未完成 -25；可见失败 -20；隐藏失败 -20；Agent 自测失败 -10；路径策略拒绝每次 -100；每 20,000 Token 扣 1 分（最多 20 分），每分钟扣 1 分（最多 10 分）。",
        "- 路径策略拒绝是轨迹中明确记录的 `PathPolicyError`；未记录的安全事件无法从旧轨迹推断。",
        "",
        "## 冻结划分",
        "",
        "| 划分 | 轨迹 | 唯一案例 | 平均分 | 验收数 |",
        "|---|---:|---:|---:|---:|",
    ]
    for split in ("train", "validation", "test", "unassigned"):
        group = buckets.get(split, [])
        mean = sum(float(row["reward"]) for row in group) / len(group) if group else 0.0
        accepted = sum(row["accepted"] is True for row in group)
        lines.append(
            f"| {split} | {len(group)} | {len(unique_cases.get(split, set()))} | "
            f"{mean:.2f} | {accepted} |"
        )
    lines.extend(
        [
            "",
            "## 离线策略学习结论",
            "",
            "当前结果只支持轨迹评分和错误分析，不能支持可信的离线强化学习结论。日志没有记录行为策略概率，也没有同一案例在不同策略下的配对结果；重复运行不能当作独立案例。需新增带策略版本、动作候选/概率、完整工具结果引用和人工验收标签的轨迹，再按冻结划分比较候选策略。",
            "",
        ]
    )
    (output_root / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--splits", type=Path, default=Path("evals/trajectory_splits/stage-s10-v1.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/trajectory-score-s10"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = score_files(args.results, args.splits)
    write_report(rows, args.output)
    print(f"评分轨迹：{len(rows)}；报告：{(args.output / 'summary.md').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
