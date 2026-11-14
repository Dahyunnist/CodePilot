"""Validate the shared v1 evaluation manifest emitted by evals.runner."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SENSITIVE = re.compile(r"api[_-]?key|token|secret|password|authorization|credential", re.I)
SHA256 = re.compile(r"^[a-f0-9]{64}$")
GIT_SHA = re.compile(r"^[a-f0-9]{40}$")
REQUIRED = {
    "schema_version", "project", "git_sha", "dataset_id", "dataset_sha256", "split",
    "model_id", "prompt_sha", "tool_schema_sha", "runtime_digest", "max_steps", "max_tokens",
    "scorer_sha", "gold_source", "cost_usd_estimate", "run_id", "trace_id", "started_at",
    "ended_at", "status",
}
NULLABLE_SHA_FIELDS = {"dataset_sha256", "prompt_sha", "tool_schema_sha", "runtime_digest", "scorer_sha"}


def validate(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["root:not_object"]
    errors = [f"missing:{key}" for key in sorted(REQUIRED - data.keys())]
    errors.extend(f"unsupported:{key}" for key in sorted(data.keys() - REQUIRED))
    for key in data:
        if key != "max_tokens" and SENSITIVE.search(str(key)):
            errors.append(f"sensitive_field:{key}")
    if data.get("schema_version") != 1:
        errors.append("invalid:schema_version")
    if data.get("project") != "CodePilot":
        errors.append("invalid:project")
    if data.get("model_id") != "scripted-oracle":
        errors.append("invalid:model_id")
    if "git_sha" in data and (not isinstance(data["git_sha"], str) or not GIT_SHA.fullmatch(data["git_sha"])):
        errors.append("invalid:git_sha")
    for key in NULLABLE_SHA_FIELDS & data.keys():
        value = data[key]
        if value is not None and (not isinstance(value, str) or not SHA256.fullmatch(value)):
            errors.append(f"invalid:{key}")
    for key in ("project", "dataset_id", "split", "model_id", "gold_source", "run_id", "trace_id"):
        if key in data and (not isinstance(data[key], str) or not data[key].strip()):
            errors.append(f"invalid:{key}")
    for key in ("max_steps", "max_tokens"):
        value = data.get(key)
        if value is not None and (type(value) is not int or value < 0):
            errors.append(f"invalid:{key}")
    cost = data.get("cost_usd_estimate")
    if cost is not None and (not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0):
        errors.append("invalid:cost_usd_estimate")
    if data.get("cost_usd_estimate") != 0:
        errors.append("scripted_oracle_cost_must_be_zero")
    if data.get("status") not in {"fixture", "running", "success", "failed", "blocked", "cancelled"}:
        errors.append("invalid:status")
    stamps: dict[str, datetime] = {}
    for key in ("started_at", "ended_at"):
        try:
            raw = data[key]
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
            stamps[key] = parsed
        except (KeyError, AttributeError, TypeError, ValueError):
            errors.append(f"invalid:{key}")
    if len(stamps) == 2 and stamps["ended_at"] < stamps["started_at"]:
        errors.append("invalid:time_order")
    return errors


def load(path: str | Path) -> list[str]:
    return validate(json.loads(Path(path).read_text(encoding="utf-8-sig")))
