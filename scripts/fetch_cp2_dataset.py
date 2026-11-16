"""Fetch and freeze SWE-bench Lite CP-2 data; dry-run unless --fetch is passed."""
import argparse, hashlib, json, urllib.request
from pathlib import Path

REVISION = "b0dde1093fe417d83b7184254edf8199c1f0dff5"
SOURCE_SHA256 = "438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3"
URL = f"https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite/resolve/{REVISION}/data/test-00000-of-00001.parquet"
MANIFEST = Path("evals/public_cases/cp2/frozen-selection.json")
DEST = Path(".tmp/cp2-swebench-lite-v1/test.parquet")
FREEZE = Path(".tmp/cp2-swebench-lite-v1/freeze.json")
LICENSES = {
    "django/django": "BSD-3-Clause",
    "mwaskom/seaborn": "BSD-3-Clause",
    "pydata/xarray": "Apache-2.0",
    "pytest-dev/pytest": "MIT",
    "scikit-learn/scikit-learn": "BSD-3-Clause",
}

def fetch_bytes(url, revision, sha256, dest):
    if revision != REVISION or REVISION not in url or not url.endswith("/data/test-00000-of-00001.parquet"):
        raise ValueError("source URL/revision mismatch")
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if sha256 and digest != sha256:
        raise ValueError(f"source SHA-256 mismatch: {digest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return data, digest

def canonicalize_rows(rows, selection_tasks, candidates):
    selection = {task["task_id"]: task for task in selection_tasks}
    candidate_map = {task["instance_id"]: task for task in candidates}
    if len(selection) != len(selection_tasks):
        raise ValueError("duplicate selection task IDs")
    if len(selection) != 20:
        raise ValueError("expected exactly the frozen 20 task IDs")
    if set(selection) != set(candidate_map) or len(candidate_map) != len(candidates):
        raise ValueError("selection and candidate IDs must match exactly without duplicates")

    wanted = set(selection)
    selected = {}
    for row in rows:
        task_id = row.get("instance_id")
        if task_id not in wanted:
            continue
        if task_id in selected:
            raise ValueError(f"{task_id}: duplicate dataset row")
        selected[task_id] = row
    if set(selected) != wanted:
        raise ValueError("dataset is missing frozen task IDs")

    safe_rows = []
    for task_id in sorted(wanted):
        row, expected, candidate = selected[task_id], selection[task_id], candidate_map[task_id]
        for source in (expected, candidate):
            if source.get("repo") not in LICENSES or source.get("license") != LICENSES[source["repo"]]:
                raise ValueError(f"{task_id}: repository license is not allowlisted")
        if expected["repo"] != candidate["repo"] or expected["base_commit"] != candidate["base_commit"]:
            raise ValueError(f"{task_id}: selection/candidate source mismatch")
        if expected.get("license") != candidate.get("license"):
            raise ValueError(f"{task_id}: selection/candidate license mismatch")
        if row.get("repo") != expected["repo"] or row.get("base_commit") != expected["base_commit"]:
            raise ValueError(f"{task_id}: dataset repository/base commit mismatch")

        problem = row.get("problem_statement")
        patch, test_patch = row.get("patch"), row.get("test_patch")
        if not isinstance(problem, str) or not problem.strip():
            raise ValueError(f"{task_id}: problem statement missing")
        if not isinstance(patch, str) or not patch.strip() or not isinstance(test_patch, str) or not test_patch.strip():
            raise ValueError(f"{task_id}: gold or hidden test patch missing")
        problem_sha = hashlib.sha256(problem.encode()).hexdigest()
        patch_sha = hashlib.sha256(patch.encode()).hexdigest()
        test_sha = hashlib.sha256(test_patch.encode()).hexdigest()
        if problem_sha != expected.get("problem_statement_sha256"):
            raise ValueError(f"{task_id}: problem statement hash mismatch")
        if patch_sha != expected.get("gold_patch_sha256") or patch_sha != candidate.get("gold_patch_sha256"):
            raise ValueError(f"{task_id}: gold patch hash mismatch")
        if test_sha != expected.get("hidden_test_patch_sha256") or test_sha != candidate.get("test_patch_sha256"):
            raise ValueError(f"{task_id}: hidden test patch hash mismatch")

        # Keep only prompt-safe task data. Never serialize patches, eval scripts, or image setup metadata.
        safe_rows.append({
            "instance_id": task_id,
            "repo": row["repo"],
            "base_commit": row["base_commit"],
            "created_at": row.get("created_at"),
            "version": row.get("version"),
            "problem_statement": problem,
        })
    payload = json.dumps(safe_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return payload

def freeze_manifest(source_sha256, subset_bytes, dest=FREEZE):
    if source_sha256 != SOURCE_SHA256:
        raise ValueError("source Parquet SHA-256 does not match pinned Hugging Face LFS object")
    record = {"asset":"cp2-swebench-lite-v1", "dataset":"SWE-bench/SWE-bench_Lite", "revision":REVISION,
              "source_url":URL, "source_file":"data/test-00000-of-00001.parquet",
              "source_parquet_sha256":source_sha256,
              "subset_json_sha256":hashlib.sha256(subset_bytes).hexdigest(), "task_count":20,
              "subset_json":subset_bytes.decode("utf-8")}
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=False, indent=2)+"\n"
    try:
        with dest.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except FileExistsError as exc:
        raise ValueError("freeze already exists; use verify, never overwrite") from exc
    return record

def verify_manifest(source_sha256, subset_bytes, path=FREEZE):
    record = json.loads(path.read_text(encoding="utf-8"))
    if source_sha256 != SOURCE_SHA256:
        raise ValueError("source Parquet SHA-256 does not match pinned Hugging Face LFS object")
    if record.get("dataset") != "SWE-bench/SWE-bench_Lite" or record.get("revision") != REVISION or record.get("source_url") != URL:
        raise ValueError("sealed source dataset/revision/URL mismatch")
    if record["source_parquet_sha256"] != source_sha256:
        raise ValueError("sealed source Parquet SHA-256 mismatch")
    if record["subset_json_sha256"] != hashlib.sha256(subset_bytes).hexdigest():
        raise ValueError("sealed subset JSON SHA-256 mismatch")
    if record["task_count"] != 20:
        raise ValueError("sealed task count mismatch")
    tasks = json.loads(subset_bytes)
    if len(tasks) != 20 or len({task.get("instance_id") for task in tasks}) != 20:
        raise ValueError("sealed subset has wrong task count or duplicate IDs")
    allowed_keys = {"instance_id", "repo", "base_commit", "created_at", "version", "problem_statement"}
    if any(set(task) != allowed_keys for task in tasks):
        raise ValueError("sealed subset contains hidden evaluation material or wrong task count")
    return record

def ensure_private_output_dir(path):
    root = Path(".tmp").resolve()
    target = path.resolve()
    if root not in target.parents:
        raise ValueError("freeze output must stay under ignored .tmp/")

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--fetch", action="store_true"); parser.add_argument("--source-file", type=Path); parser.add_argument("--mirror-url", help="mirror URL for the exact pinned Parquet path/revision"); parser.add_argument("--output-dir", type=Path, default=DEST.parent); parser.add_argument("--expected-source-sha256"); parser.add_argument("--mode", choices=("freeze", "verify"), default="verify"); args=parser.parse_args()
    if not args.fetch:
        print(f"dry-run: {URL} -> {DEST}; pass --fetch to download")
        return 0
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit("缺少可选依赖：pip install -r requirements-bench.txt") from exc
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    candidates=json.loads(Path("evals/public_cases/cp2/auditable-candidates-v1.json").read_text(encoding="utf-8-sig"))
    if args.source_file:
        data=args.source_file.read_bytes(); digest=hashlib.sha256(data).hexdigest()
        if not args.expected_source_sha256 or digest != args.expected_source_sha256:
            raise SystemExit(f"source SHA-256 mismatch: {digest}")
        source_path=args.source_file
    else:
        data, digest=fetch_bytes(args.mirror_url or URL, REVISION, args.expected_source_sha256 or SOURCE_SHA256, DEST)
        source_path=DEST
    rows=pq.read_table(source_path).to_pylist()
    subset=canonicalize_rows(rows, manifest["tasks"], candidates)
    ensure_private_output_dir(args.output_dir)
    freeze_path=args.output_dir/"freeze.json"
    if args.mode == "freeze":
        freeze_manifest(digest, subset, freeze_path)
        print(f"frozen 20 tasks; parquet_sha256={digest}; subset_sha256={hashlib.sha256(subset).hexdigest()}")
    else:
        verify_manifest(digest, subset, freeze_path)
        print("verified sealed 20-task asset")
    return 0
if __name__ == "__main__": raise SystemExit(main())
