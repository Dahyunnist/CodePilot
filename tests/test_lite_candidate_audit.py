import json
from pathlib import Path
from evals.public_cases.audit_lite_candidates import build_candidates

def test_lite_candidate_audit_keeps_twenty_and_does_not_invent_issue_urls():
    source=json.loads(Path('evals/public_cases/cp2/frozen-selection.json').read_text(encoding='utf-8-sig'))
    rows=build_candidates(source)
    assert len(rows)==20
    assert all(row['base_commit'] and row['gold_patch_sha256'] and row['test_patch_sha256'] and row['license'] for row in rows)
    assert all(row['issue_url'] is None and row['related_issue_url'] is None and row['source_pr_url'] for row in rows)
    assert all(row['issue_url_status']=='unverified_missing' for row in rows)
    assert all(row['status']=='candidate_metadata_only' for row in rows)
    assert all(row['benchmark']=='SWE-bench Lite; not Verified; not blind' for row in rows)
