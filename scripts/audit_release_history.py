"""Summarize release-history risks without printing matched values."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import PurePosixPath


TEXT_SUFFIXES = {
    ".bat", ".cfg", ".csv", ".env", ".example", ".ini", ".json", ".md",
    ".patch", ".ps1", ".py", ".sh", ".toml", ".txt", ".yaml", ".yml",
}
SECRET_PATTERNS = (
    re.compile(rb"(?i)sk-[a-z0-9_-]{20,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        rb"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key|password)"
        rb"\s*[:=]\s*[\"']([^\"'\r\n]{16,})[\"']"
    ),
)
FIXTURE_MARKERS = re.compile(
    rb"(?i)(?:test|fake|dummy|example|placeholder|redact|should.not|must.not|"
    rb"not.real|invalid|sample|secret|private|123456|abcdefabcdef)"
)
ABSOLUTE_PATH = re.compile(
    rb"(?i)[A-Z]:\\[A-Za-z0-9_.~-]{2,}(?:\\[^\\\s\"']+)*"
    rb"|/(?:Users|home)/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*"
)
PARTIAL_USAGE_PATH = "evals/public_cases/cp2/provider-usage-partial-2026-11-15.json"


def git(*args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _paths_for_ref(ref: str) -> tuple[set[str], set[str], dict[str, set[str]]]:
    rows = git("rev-list", "--objects", ref).decode("utf-8", "replace").splitlines()
    historical_paths: set[str] = set()
    text_blobs: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        oid, separator, path = row.partition(" ")
        if not separator:
            continue
        historical_paths.add(path)
        if PurePosixPath(path.lower()).suffix in TEXT_SUFFIXES:
            text_blobs[oid].add(path)
    current_paths = set(
        git("ls-tree", "-r", "--name-only", ref)
        .decode("utf-8", "replace")
        .splitlines()
    )
    return historical_paths, current_paths, text_blobs


def _scan_blobs(blob_paths: dict[str, set[str]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    blob_ids = sorted(blob_paths)
    for start in range(0, len(blob_ids), 128):
        batch = blob_ids[start : start + 128]
        output = git(
            "cat-file",
            "--batch",
            input_bytes=("".join(f"{oid}\n" for oid in batch)).encode(),
        )
        offset = 0
        for oid in batch:
            header_end = output.find(b"\n", offset)
            header = output[offset:header_end].split()
            offset = header_end + 1
            if len(header) != 3 or header[1] != b"blob":
                continue
            size = int(header[2])
            content = output[offset : offset + size]
            offset += size + 1
            credential_hits = 0
            fixture_hits = 0
            for pattern in SECRET_PATTERNS:
                matches = list(pattern.finditer(content))
                credential_hits += len(matches)
                for match in matches:
                    value = match.group(1) if match.lastindex else match.group(0)
                    fixture_hits += bool(FIXTURE_MARKERS.search(value))
            path_matches = list(ABSOLUTE_PATH.finditer(content))
            profile_paths = sum(
                match.group(0).lower().startswith(b"c:\\users\\")
                for match in path_matches
            )
            if credential_hits or path_matches:
                result[oid] = {
                    "credential_hits": credential_hits,
                    "fixture_hits": fixture_hits,
                    "absolute_path_hits": len(path_matches),
                    "profile_path_hits": profile_paths,
                }
    return result


def _artifact_path(path: str, category: str) -> bool:
    normalized = "/" + path.lower().lstrip("/")
    if category == "hidden":
        return "/hidden_tests/" in normalized or any(
            "holdout" in part for part in normalized.split("/")
        )
    return normalized.startswith("/reports/") or "/reports/" in normalized


def _usage_field_flags(ref: str) -> tuple[bool, bool]:
    try:
        value = json.loads(git("show", f"{ref}:{PARTIAL_USAGE_PATH}"))
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return False, False
    keys = {str(key).lower() for key in value} if isinstance(value, dict) else set()
    alias_present = any("api_key_name" in key or "alias" in key for key in keys)
    amount_present = any(
        "amount" in key or "cost" in key or "price" in key for key in keys
    )
    return alias_present, amount_present


def audit_ref(ref: str, shared_scan: dict[str, dict[str, int]], refs: dict[str, tuple[set[str], set[str], dict[str, set[str]]]]) -> None:
    historical_paths, current_paths, blob_paths = refs[ref]
    reachable_blobs = set(blob_paths)
    secret_blobs = {
        oid for oid in reachable_blobs if shared_scan.get(oid, {}).get("credential_hits", 0)
    }
    absolute_blobs = {
        oid for oid in reachable_blobs if shared_scan.get(oid, {}).get("absolute_path_hits", 0)
    }
    fixture_hits = sum(
        shared_scan[oid]["fixture_hits"] for oid in secret_blobs if oid in shared_scan
    )
    total_secret_hits = sum(
        shared_scan[oid]["credential_hits"] for oid in secret_blobs if oid in shared_scan
    )
    path_occurrences = sum(
        shared_scan[oid]["absolute_path_hits"] for oid in absolute_blobs if oid in shared_scan
    )
    profile_occurrences = sum(
        shared_scan[oid]["profile_path_hits"] for oid in absolute_blobs if oid in shared_scan
    )
    path_files = {
        path for oid in absolute_blobs for path in blob_paths.get(oid, set())
    }
    alias_field, amount_field = _usage_field_flags(ref)
    hidden_ever = sum(_artifact_path(path, "hidden") for path in historical_paths)
    hidden_now = sum(_artifact_path(path, "hidden") for path in current_paths)
    reports_ever = sum(_artifact_path(path, "reports") for path in historical_paths)
    reports_now = sum(_artifact_path(path, "reports") for path in current_paths)
    commit_count = git("rev-list", "--count", ref).decode().strip()
    print(
        f"ref={ref} commits={commit_count} historical_paths={len(historical_paths)} "
        f"current_paths={len(current_paths)} hidden_or_holdout_ever={hidden_ever} "
        f"current={hidden_now} reports_ever={reports_ever} current={reports_now} "
        f"credential_pattern_blobs={len(secret_blobs)} "
        f"credential_pattern_hits={total_secret_hits} fixture_marker_hits={fixture_hits} "
        f"absolute_path_blobs={len(absolute_blobs)} "
        f"absolute_path_files={len(path_files)} absolute_path_occurrences={path_occurrences} "
        f"profile_path_occurrences={profile_occurrences} "
        f"partial_usage_current={PARTIAL_USAGE_PATH in current_paths} "
        f"alias_field_current={alias_field} amount_or_cost_field_current={amount_field}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只输出 Git 发布历史中的风险计数，不输出匹配值。"
    )
    parser.add_argument("refs", nargs="+", help="要审计的本地 Git ref")
    args = parser.parse_args()
    refs = {}
    combined_blobs: dict[str, set[str]] = defaultdict(set)
    for ref in args.refs:
        historical, current, blobs = _paths_for_ref(ref)
        refs[ref] = (historical, current, blobs)
        for oid, paths in blobs.items():
            combined_blobs[oid].update(paths)
    scan = _scan_blobs(combined_blobs)
    for ref in args.refs:
        audit_ref(ref, scan, refs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
