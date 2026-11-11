from hashlib import sha256
from scripts.fetch_cp2_dataset import canonicalize_rows, fetch_bytes, freeze_manifest
import pytest

def test_fetch_rejects_wrong_sha_before_write(tmp_path, monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def read(self): return b"parquet"
    monkeypatch.setattr("scripts.fetch_cp2_dataset.urllib.request.urlopen", lambda *a,**k: Response())
    dest=tmp_path/"x"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        fetch_bytes("https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite/resolve/b0dde10/data/test-00000-of-00001.parquet","b0dde10","0"*64,dest)
    assert not dest.exists()

def test_canonicalize_twenty_ids_and_freeze_separate_hashes(tmp_path):
    ids=[f"repo__p-{n}" for n in range(20)]
    payload=canonicalize_rows([{"instance_id":i,"repo":"repo"} for i in reversed(ids)],ids)
    rec=freeze_manifest("a"*64,payload,tmp_path/"freeze.json")
    assert rec["task_count"]==20 and rec["source_parquet_sha256"]=="a"*64
    assert rec["subset_json_sha256"]==sha256(payload).hexdigest()
    assert rec["source_parquet_sha256"] != rec["subset_json_sha256"]
