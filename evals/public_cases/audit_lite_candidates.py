"""Audit candidate metadata from the existing frozen SWE-bench Lite manifest."""
import json,re
from pathlib import Path
SOURCE=Path("evals/public_cases/cp2/frozen-selection.json")
OUTPUT=Path("evals/public_cases/cp2/auditable-candidates-v1.json")
LICENSE_ALLOWLIST={"django/django":"BSD-3-Clause","pytest-dev/pytest":"MIT","pydata/xarray":"Apache-2.0","mwaskom/seaborn":"BSD-3-Clause","scikit-learn/scikit-learn":"BSD-3-Clause"}

def validate_candidates(rows, source_tasks):
    """Fail closed: metadata candidates cannot become runnable without execution evidence."""
    expected={row["task_id"]:row for row in source_tasks}
    if len(rows)!=20 or len({row.get("instance_id") for row in rows})!=20 or set(expected)!={row.get("instance_id") for row in rows}:
        raise ValueError("candidate IDs/count mismatch")
    for row in rows:
        task=expected[row["instance_id"]]
        if row.get("status")!="candidate_metadata_only":
            raise ValueError("candidate status must remain metadata-only pending execution evidence")
        for field, source_field in (("repo","repo"),("base_commit","base_commit"),("license","license"),("gold_patch_sha256","gold_patch_sha256"),("test_patch_sha256","hidden_test_patch_sha256")):
            if row.get(field)!=task.get(source_field): raise ValueError(f"{row['instance_id']}: {field} mismatch")
        if row.get("license")!=LICENSE_ALLOWLIST.get(row.get("repo")):
            raise ValueError(f"{row['instance_id']}: unknown or mismatched license")
        if row.get("issue_url") is not None or row.get("issue_url_status")!="unverified_missing":
            raise ValueError(f"{row['instance_id']}: issue provenance status mismatch")
        if not re.fullmatch(r"[0-9a-f]{40}",str(row.get("base_commit", ""))): raise ValueError("invalid base commit")
        for field in ("gold_patch_sha256","test_patch_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}",str(row.get(field,""))): raise ValueError(f"invalid {field}")
        if row.get("fix_commit_sha") or row.get("visible_test_command") or row.get("hidden_test_command") or row.get("license_base_evidence"):
            raise ValueError("unverified execution evidence must not be asserted")
    return True

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
    data=json.loads(SOURCE.read_text(encoding='utf-8-sig')); rows=build_candidates(data); validate_candidates(rows,data["tasks"]); OUTPUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(f"wrote {OUTPUT}: 20 metadata candidates; no issue URL reachability verified")
if __name__=='__main__': main()
