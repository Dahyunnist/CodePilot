import json
from pathlib import Path
import pytest
from evals.public_cases.audit_lite_candidates import build_candidates, validate_candidates

def test_lite_candidate_audit_keeps_twenty_and_does_not_invent_issue_urls():
    source=json.loads(Path('evals/public_cases/cp2/frozen-selection.json').read_text(encoding='utf-8-sig'))
    rows=build_candidates(source)
    assert len(rows)==20
    assert all(row['base_commit'] and row['gold_patch_sha256'] and row['test_patch_sha256'] and row['license'] for row in rows)
    assert all(row['issue_url'] is None and row['related_issue_url'] is None and row['source_pr_url'] for row in rows)
    assert all(row['issue_url_status']=='unverified_missing' for row in rows)
    assert all(row['status']=='candidate_metadata_only' for row in rows)
    assert all(row['benchmark']=='SWE-bench Lite; not Verified; not blind' for row in rows)
    assert validate_candidates(rows,source['tasks'])

def test_all_candidates_fail_closed_if_marked_runnable_without_evidence():
    source=json.loads(Path('evals/public_cases/cp2/frozen-selection.json').read_text(encoding='utf-8-sig'))
    rows=build_candidates(source)
    rows[0]['status']='runnable'
    with pytest.raises(ValueError,match='metadata-only'):
        validate_candidates(rows,source['tasks'])

def test_candidate_license_must_match_source_and_independent_allowlist():
    source=json.loads(Path('evals/public_cases/cp2/frozen-selection.json').read_text(encoding='utf-8-sig'))
    rows=build_candidates(source)
    rows[0]['license']='MIT'
    with pytest.raises(ValueError,match='license mismatch'):
        validate_candidates(rows,source['tasks'])

def test_first_django_candidate_remains_pending_without_reproduction_evidence():
    source=json.loads(Path('evals/public_cases/cp2/frozen-selection.json').read_text(encoding='utf-8-sig'))
    candidate=json.loads(Path('evals/public_cases/cp2/auditable-candidates-v1.json').read_text(encoding='utf-8-sig'))[0]
    task=next(item for item in source['tasks'] if item['task_id']==candidate['instance_id'])
    assert candidate['instance_id']=='django__django-10924'
    for key in ('repo','base_commit','license','gold_patch_sha256'):
        assert candidate[key] == task[key]
    assert candidate['test_patch_sha256'] == task['hidden_test_patch_sha256']
    assert candidate['source_pr_url'] == task['pull_request_url']
    assert candidate['issue_url'] is None
    assert candidate['status']=='candidate_metadata_only'
    assert 'fix_commit_sha' not in candidate
    assert 'visible_test_command' not in candidate
