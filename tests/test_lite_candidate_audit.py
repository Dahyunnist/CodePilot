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
    with pytest.raises(ValueError,match='fully evidenced reproducible'):
        validate_candidates(rows,source['tasks'])

def test_reproducible_candidate_requires_complete_revision_bound_evidence():
    source=json.loads(Path('evals/public_cases/cp2/frozen-selection.json').read_text(encoding='utf-8-sig'))
    rows=build_candidates(source)
    candidate=rows[0]
    candidate.update({
        'status':'candidate_reproducible',
        'issue_url':'https://github.com/django/django/issues/29529',
        'fix_commit_sha':'a'*40,
        'fix_commit_url':f"https://github.com/{candidate['repo']}/commit/"+'a'*40,
        'license_base_evidence':f"https://github.com/{candidate['repo']}/blob/{candidate['base_commit']}/LICENSE",
        'visible_test_command':'python -m pytest tests/model_fields/test_filepathfield.py -q',
        'hidden_test_command':'python -m pytest tests/model_fields/test_filepathfield.py -q',
        'hidden_test_source':{'files':candidate['hidden_test_files'],'patch_sha256':candidate['test_patch_sha256'],'provenance':'frozen_manifest'},
    })
    assert validate_candidates(rows,source['tasks'])

@pytest.mark.parametrize('field', ['issue_url','fix_commit_sha','fix_commit_url','license_base_evidence','visible_test_command','hidden_test_command','hidden_test_source'])
def test_reproducible_candidate_fails_when_any_required_evidence_is_missing(field):
    source=json.loads(Path('evals/public_cases/cp2/frozen-selection.json').read_text(encoding='utf-8-sig'))
    rows=build_candidates(source)
    candidate=rows[0]
    candidate.update({
        'status':'candidate_reproducible',
        'issue_url':'https://github.com/django/django/issues/29529',
        'fix_commit_sha':'a'*40,
        'fix_commit_url':f"https://github.com/{candidate['repo']}/commit/"+'a'*40,
        'license_base_evidence':f"https://github.com/{candidate['repo']}/blob/{candidate['base_commit']}/LICENSE",
        'visible_test_command':'python -m pytest tests/model_fields/test_filepathfield.py -q',
        'hidden_test_command':'python -m pytest tests/model_fields/test_filepathfield.py -q',
        'hidden_test_source':{'files':candidate['hidden_test_files'],'patch_sha256':candidate['test_patch_sha256'],'provenance':'frozen_manifest'},
    })
    candidate[field]=None
    with pytest.raises(ValueError,match='missing'):
        validate_candidates(rows,source['tasks'])

def test_license_evidence_must_point_to_same_repository_and_frozen_base():
    source=json.loads(Path('evals/public_cases/cp2/frozen-selection.json').read_text(encoding='utf-8-sig'))
    rows=build_candidates(source)
    candidate=rows[0]
    candidate.update({
        'status':'candidate_reproducible',
        'issue_url':'https://github.com/django/django/issues/29529',
        'fix_commit_sha':'a'*40,
        'fix_commit_url':f"https://github.com/{candidate['repo']}/commit/"+'a'*40,
        'license_base_evidence':'https://github.com/django/django/blob/'+'b'*40+'/LICENSE',
        'visible_test_command':'pytest -q',
        'hidden_test_command':'pytest -q',
        'hidden_test_source':{'files':candidate['hidden_test_files'],'patch_sha256':candidate['test_patch_sha256'],'provenance':'frozen_manifest'},
    })
    with pytest.raises(ValueError,match='match repository and base commit'):
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
