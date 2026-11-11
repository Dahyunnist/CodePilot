"""Fetch and freeze SWE-bench Lite CP-2 data; dry-run unless --fetch is passed."""
import argparse, hashlib, json, os, urllib.request
from pathlib import Path

REVISION = "b0dde10"
URL = f"https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite/resolve/{REVISION}/data/test-00000-of-00001.parquet"
MANIFEST = Path("evals/public_cases/cp2/frozen-selection.json")
DEST = Path(".tmp/cp2-swebench-lite-v1/test.parquet")
FREEZE = Path(".tmp/cp2-swebench-lite-v1/freeze.json")

def fetch_bytes(url, revision, sha256, dest):
    if revision != REVISION or url != URL:
        raise ValueError("source URL/revision mismatch")
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if sha256 and digest != sha256:
        raise ValueError(f"source SHA-256 mismatch: {digest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return data, digest

def canonicalize_rows(rows, expected_ids):
    selected = {row["instance_id"]: row for row in rows if row.get("instance_id") in set(expected_ids)}
    if set(selected) != set(expected_ids) or len(expected_ids) != 20:
        raise ValueError("expected exactly the frozen 20 task IDs")
    payload = json.dumps([selected[key] for key in sorted(selected)], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return payload

def freeze_manifest(source_sha256, subset_bytes, dest=FREEZE):
    record = {"asset":"cp2-swebench-lite-v1", "dataset":"SWE-bench/SWE-bench_Lite", "revision":REVISION,
              "source_file":"data/test-00000-of-00001.parquet", "source_parquet_sha256":source_sha256,
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
    if record["source_parquet_sha256"] != source_sha256:
        raise ValueError("sealed source Parquet SHA-256 mismatch")
    if record["subset_json_sha256"] != hashlib.sha256(subset_bytes).hexdigest():
        raise ValueError("sealed subset JSON SHA-256 mismatch")
    if record["task_count"] != 20:
        raise ValueError("sealed task count mismatch")
    return record

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--fetch", action="store_true"); parser.add_argument("--mode", choices=("freeze", "verify"), default="verify"); args=parser.parse_args()
    if not args.fetch:
        print(f"dry-run: {URL} -> {DEST}; pass --fetch to download")
        return 0
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit("缺少可选依赖：pip install -r requirements-bench.txt") from exc
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8-sig")); ids=[t["task_id"] for t in manifest["tasks"]]
    data, digest=fetch_bytes(URL, REVISION, None, DEST)
    rows=pq.read_table(DEST).to_pylist(); subset=canonicalize_rows(rows, ids)
    if args.mode == "freeze":
        freeze_manifest(digest, subset)
        print(f"frozen 20 tasks; parquet_sha256={digest}; subset_sha256={hashlib.sha256(subset).hexdigest()}")
    else:
        verify_manifest(digest, subset)
        print("verified sealed 20-task asset")
    return 0
if __name__ == "__main__": raise SystemExit(main())
