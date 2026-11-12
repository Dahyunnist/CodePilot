"""Fetch and freeze SWE-bench Lite CP-2 data; dry-run unless --fetch is passed."""
import argparse, hashlib, json, os, urllib.request
from pathlib import Path

REVISION = "b0dde1093fe417d83b7184254edf8199c1f0dff5"
SOURCE_SHA256 = "438e281d80587aa7be470896ce410557002fde02d2ceee3e099331d308f62dd3"
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
    return record

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--fetch", action="store_true"); parser.add_argument("--source-file", type=Path); parser.add_argument("--output-dir", type=Path, default=DEST.parent); parser.add_argument("--expected-source-sha256"); parser.add_argument("--mode", choices=("freeze", "verify"), default="verify"); args=parser.parse_args()
    if not args.fetch:
        print(f"dry-run: {URL} -> {DEST}; pass --fetch to download")
        return 0
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit("缺少可选依赖：pip install -r requirements-bench.txt") from exc
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8-sig")); ids=[t["task_id"] for t in manifest["tasks"]]
    if args.source_file:
        data=args.source_file.read_bytes(); digest=hashlib.sha256(data).hexdigest()
        if not args.expected_source_sha256 or digest != args.expected_source_sha256:
            raise SystemExit(f"source SHA-256 mismatch: {digest}")
        source_path=args.source_file
    else:
        data, digest=fetch_bytes(URL, REVISION, args.expected_source_sha256, DEST)
        source_path=DEST
    rows=pq.read_table(source_path).to_pylist(); subset=canonicalize_rows(rows, ids)
    freeze_path=args.output_dir/"freeze.json"
    if args.mode == "freeze":
        freeze_manifest(digest, subset, freeze_path)
        print(f"frozen 20 tasks; parquet_sha256={digest}; subset_sha256={hashlib.sha256(subset).hexdigest()}")
    else:
        verify_manifest(digest, subset, freeze_path)
        print("verified sealed 20-task asset")
    return 0
if __name__ == "__main__": raise SystemExit(main())
