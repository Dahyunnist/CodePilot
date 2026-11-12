"""Audit candidate metadata from the existing frozen SWE-bench Lite manifest."""
import json,re
from pathlib import Path
SOURCE=Path("evals/public_cases/cp2/frozen-selection.json")
OUTPUT=Path("evals/public_cases/cp2/auditable-candidates-v1.json")

def build_candidates(data):
    out=[]
    for task in data["tasks"]:
        out.append({"instance_id":task["task_id"],"repo":task["repo"],
          "issue_url":task.get("issue_url") or None,
          "issue_url_status":"source_manifest" if task.get("issue_url") else "unverified_missing",
          "source_pr_url":task.get("pull_request_url"),
          "related_issue_url":None,
          "base_commit":task["base_commit"],"license":task.get("license"),
          "gold_patch_sha256":task.get("gold_patch_sha256"),
          "test_patch_sha256":task.get("hidden_test_patch_sha256"),
          "hidden_test_files":task.get("hidden_test_files",[]),
          "fail_to_pass_count":task.get("fail_to_pass_count"),
          "pass_to_pass_count":task.get("pass_to_pass_count"),
          "docker_image":task.get("docker_image"),"status":"candidate_metadata_only",
          "benchmark":"SWE-bench Lite; not Verified; not blind"})
    if len(out)!=20 or len({x['instance_id'] for x in out})!=20: raise ValueError("expected 20 unique task IDs")
    for row in out:
        if not row['license'] or not row['base_commit'] or not row['gold_patch_sha256'] or not row['test_patch_sha256'] or not row['docker_image']:
            row['status']='excluded_missing_metadata'
    return out

def main():
    data=json.loads(SOURCE.read_text(encoding='utf-8-sig')); OUTPUT.write_text(json.dumps(build_candidates(data),ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(f"wrote {OUTPUT}: 20 metadata candidates; no issue URL reachability verified")
if __name__=='__main__': main()
