from hashlib import sha256
import json
from scripts.fetch_cp2_dataset import (
    REVISION,
    SOURCE_SHA256,
    URL,
    canonicalize_rows,
    fetch_bytes,
    freeze_manifest,
    verify_manifest,
)
import pytest

def test_fetch_rejects_wrong_sha_before_write(tmp_path, monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def read(self): return b"parquet"
    monkeypatch.setattr("scripts.fetch_cp2_dataset.urllib.request.urlopen", lambda *a,**k: Response())
    dest=tmp_path/"x"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        fetch_bytes(URL, REVISION,"0"*64,dest)
    assert not dest.exists()

def test_fetch_rejects_short_revision_and_wrong_pinned_hash(tmp_path):
    with pytest.raises(ValueError, match="URL/revision mismatch"):
        fetch_bytes(URL.replace(REVISION, "b0dde10"), "b0dde10", SOURCE_SHA256, tmp_path/"short.parquet")
    with pytest.raises(ValueError, match="pinned Hugging Face LFS object"):
        freeze_manifest("0"*64, b"[]", tmp_path/"wrong.json")

def test_fetch_accepts_configured_mirror_only_for_pinned_revision(tmp_path, monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def read(self): return b"payload"
    monkeypatch.setattr("scripts.fetch_cp2_dataset.urllib.request.urlopen", lambda *a,**k: Response())
    mirror = f"https://mirror.example/hf/datasets/SWE-bench/SWE-bench_Lite/resolve/{REVISION}/data/test-00000-of-00001.parquet"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        fetch_bytes(mirror, REVISION, SOURCE_SHA256, tmp_path/"mirror.parquet")
    assert not (tmp_path/"mirror.parquet").exists()

def test_canonicalize_twenty_ids_and_freeze_separate_hashes(tmp_path):
    selection, candidates, rows = _valid_fixture()
    payload=canonicalize_rows(list(reversed(rows)), selection, candidates)
    rec=freeze_manifest(SOURCE_SHA256,payload,tmp_path/"freeze.json")
    assert rec["task_count"]==20 and rec["source_parquet_sha256"]==SOURCE_SHA256
    assert rec["subset_json_sha256"]==sha256(payload).hexdigest()
    assert rec["source_parquet_sha256"] != rec["subset_json_sha256"]
    assert rec["revision"] == REVISION
    assert rec["source_url"] == URL
    tasks=json.loads(payload)
    assert len(tasks) == 20
    assert all(not ({"patch", "test_patch", "eval_script"} & task.keys()) for task in tasks)

def _valid_fixture():
    selection, candidates, rows = [], [], []
    for number in range(20):
        task_id=f"django__django-{10000+number}"
        problem, patch, test_patch=f"problem-{number}", f"gold-{number}", f"test-{number}"
        gold_sha=sha256(patch.encode()).hexdigest()
        test_sha=sha256(test_patch.encode()).hexdigest()
        selection.append({
            "task_id":task_id,"repo":"django/django","license":"BSD-3-Clause",
            "base_commit":f"commit-{number}",
            "problem_statement_sha256":sha256(problem.encode()).hexdigest(),
            "gold_patch_sha256":gold_sha,"hidden_test_patch_sha256":test_sha,
        })
        candidates.append({
            "instance_id":task_id,"repo":"django/django","license":"BSD-3-Clause",
            "base_commit":f"commit-{number}","gold_patch_sha256":gold_sha,
            "test_patch_sha256":test_sha,
        })
        rows.append({
            "instance_id":task_id,"repo":"django/django","base_commit":f"commit-{number}",
            "problem_statement":problem,"patch":patch,"test_patch":test_patch,
            "eval_script":"private-eval",
        })
    return selection,candidates,rows

@pytest.mark.parametrize("tamper", ["repo","base_commit","problem","gold","hidden","license","duplicate"])
def test_canonicalize_rejects_tampering_before_freeze_file(tamper,tmp_path):
    selection,candidates,rows=_valid_fixture()
    if tamper == "repo": rows[0]["repo"]="attacker/repo"
    elif tamper == "base_commit": rows[0]["base_commit"]="other"
    elif tamper == "problem": rows[0]["problem_statement"] += " changed"
    elif tamper == "gold": rows[0]["patch"] += " changed"
    elif tamper == "hidden": rows[0]["test_patch"] += " changed"
    elif tamper == "license": candidates[0]["license"]="Unknown"
    elif tamper == "duplicate": rows.append(dict(rows[0]))
    with pytest.raises(ValueError):
        subset=canonicalize_rows(rows,selection,candidates)
        freeze_manifest(SOURCE_SHA256,subset,tmp_path/"freeze.json")
    assert not (tmp_path/"freeze.json").exists()

def test_canonicalize_rejects_duplicate_manifests_and_missing_patches():
    selection,candidates,rows=_valid_fixture()
    with pytest.raises(ValueError,match="duplicate selection"):
        canonicalize_rows(rows,selection+[selection[0]],candidates)
    selection,candidates,rows=_valid_fixture()
    rows[0]["test_patch"]=""
    with pytest.raises(ValueError,match="patch missing"):
        canonicalize_rows(rows,selection,candidates)

def test_freeze_is_create_once_and_verify_rejects_changes(tmp_path):
    from scripts.fetch_cp2_dataset import freeze_manifest, verify_manifest
    from hashlib import sha256
    dest=tmp_path/"freeze.json"
    selection,candidates,rows=_valid_fixture()
    subset=canonicalize_rows(rows,selection,candidates)
    freeze_manifest(SOURCE_SHA256, subset, dest)
    assert verify_manifest(SOURCE_SHA256, subset, dest)["task_count"] == 20
    with pytest.raises(ValueError, match="never overwrite"):
        freeze_manifest(SOURCE_SHA256, b"different", dest)
    with pytest.raises(ValueError, match="pinned Hugging Face LFS object"):
        freeze_manifest("b"*64, subset, tmp_path/"wrong.json")
    with pytest.raises(ValueError, match="pinned Hugging Face LFS object"):
        verify_manifest("b"*64, subset, dest)
    with pytest.raises(ValueError, match="subset JSON SHA"):
        verify_manifest(SOURCE_SHA256, b"[1]", dest)

def test_frozen_record_pins_source_hash_revision_and_is_not_legacy_selection_metadata(tmp_path):
    from scripts.fetch_cp2_dataset import verify_manifest
    selection,candidates,rows=_valid_fixture()
    subset = canonicalize_rows(rows,selection,candidates)
    path = tmp_path / "freeze.json"
    record = freeze_manifest(SOURCE_SHA256, subset, path)
    loaded = verify_manifest(SOURCE_SHA256, subset, path)
    assert loaded["source_parquet_sha256"] == SOURCE_SHA256
    assert loaded["revision"] == "b0dde1093fe417d83b7184254edf8199c1f0dff5"
    assert "dataset_source_sha256" not in loaded
    record["revision"] = "b0dde10"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="dataset/revision/URL"):
        verify_manifest(SOURCE_SHA256, subset, path)

def test_legacy_selection_and_holdout_source_fingerprints_remain_historical():
    from pathlib import Path
    root = Path(__file__).parents[1] / "evals/public_cases/cp2"
    selection = json.loads((root / "frozen-selection.json").read_text(encoding="utf-8"))
    holdout = json.loads((root / "holdout-h3.json").read_text(encoding="utf-8"))
    assert selection["dataset_revision"] == "SWE-bench/SWE-bench_Lite:test"
    assert selection["dataset_source_sha256"] == "5cb74f0feb564d6c6bf3f51725384ca646b854d2713d62e86227a29af61d1a92"
    assert holdout["dataset_source_sha256"] == selection["dataset_source_sha256"]
    assert selection["dataset_source_sha256"] != SOURCE_SHA256
