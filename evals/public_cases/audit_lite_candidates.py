"""Audit candidate metadata from the existing frozen SWE-bench Lite manifest."""
import json,re
from pathlib import Path
SOURCE=Path("evals/public_cases/cp2/frozen-selection.json")
OUTPUT=Path("evals/public_cases/cp2/auditable-candidates-v1.json")
LICENSE_ALLOWLIST={"django/django":"BSD-3-Clause","pytest-dev/pytest":"MIT","pydata/xarray":"Apache-2.0","mwaskom/seaborn":"BSD-3-Clause","scikit-learn/scikit-learn":"BSD-3-Clause"}

def validate_candidates(rows, source_tasks):
    """Validate frozen metadata and require complete provenance before reproduction status."""
    expected={row["task_id"]:row for row in source_tasks}
    if len(rows)!=20 or len({row.get("instance_id") for row in rows})!=20 or set(expected)!={row.get("instance_id") for row in rows}:
        raise ValueError("candidate IDs/count mismatch")
    for row in rows:
        task=expected[row["instance_id"]]
        status=row.get("status")
        if status not in {"candidate_metadata_only", "candidate_reproducible"}:
            raise ValueError("candidate status must be metadata-only or fully evidenced reproducible")
        for field, source_field in (("repo","repo"),("base_commit","base_commit"),("license","license"),("gold_patch_sha256","gold_patch_sha256"),("test_patch_sha256","hidden_test_patch_sha256")):
            if row.get(field)!=task.get(source_field): raise ValueError(f"{row['instance_id']}: {field} mismatch")
        if row.get("hidden_test_files") != task.get("hidden_test_files"):
            raise ValueError(f"{row['instance_id']}: hidden test source mismatch")
        if row.get("license")!=LICENSE_ALLOWLIST.get(row.get("repo")):
            raise ValueError(f"{row['instance_id']}: unknown or mismatched license")
        if status == "candidate_metadata_only":
            if row.get("issue_url") is not None or row.get("issue_url_status")!="unverified_missing":
                raise ValueError(f"{row['instance_id']}: issue provenance status mismatch")
            evidence_fields=("fix_commit_sha", "fix_commit_url", "visible_test_command", "hidden_test_command", "license_base_evidence", "hidden_test_source")
            if any(row.get(field) for field in evidence_fields):
                raise ValueError("unverified execution evidence must not be asserted")
        else:
            _validate_reproducible_evidence(row)
        if not re.fullmatch(r"[0-9a-f]{40}",str(row.get("base_commit", ""))): raise ValueError("invalid base commit")
        for field in ("gold_patch_sha256","test_patch_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}",str(row.get(field,""))): raise ValueError(f"invalid {field}")
    return True

def _validate_reproducible_evidence(row):
    required=("issue_url", "fix_commit_sha", "fix_commit_url", "visible_test_command", "hidden_test_command", "license_base_evidence", "hidden_test_source")
    missing=[field for field in required if not row.get(field)]
    if missing:
        raise ValueError(f"{row['instance_id']}: reproducible candidate missing {', '.join(missing)}")
    if not re.fullmatch(r"https://(?:github\.com/[\w.-]+/[\w.-]+/issues/\d+|code\.django\.com/ticket/\d+)", str(row["issue_url"])):
        raise ValueError(f"{row['instance_id']}: invalid issue_url evidence URL")
    if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+/blob/[0-9a-f]{40}/(?:LICENSE|LICENSE\.md|LICENSE\.txt)", str(row["license_base_evidence"])):
        raise ValueError(f"{row['instance_id']}: invalid license_base_evidence URL")
    if not re.fullmatch(r"[0-9a-f]{40}", str(row["fix_commit_sha"])):
        raise ValueError(f"{row['instance_id']}: invalid fix commit SHA")
    if row["fix_commit_url"] != f"https://github.com/{row['repo']}/commit/{row['fix_commit_sha']}":
        raise ValueError(f"{row['instance_id']}: fix commit URL must identify repository and SHA")
    license_url=row["license_base_evidence"]
    if f"/{row['repo']}/blob/{row['base_commit']}/" not in license_url:
        raise ValueError(f"{row['instance_id']}: license evidence must match repository and base commit")
    for field in ("visible_test_command", "hidden_test_command"):
        if not isinstance(row[field], str) or not row[field].strip():
            raise ValueError(f"{row['instance_id']}: {field} must be a nonempty command")
    source=row["hidden_test_source"]
    if (not isinstance(source, dict) or source.get("files") != row.get("hidden_test_files")
            or source.get("patch_sha256") != row.get("test_patch_sha256")
            or source.get("provenance") != "frozen_manifest"):
        raise ValueError(f"{row['instance_id']}: hidden test source evidence mismatch")

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
