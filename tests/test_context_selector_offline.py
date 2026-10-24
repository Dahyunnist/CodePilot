from evals.context_selector_offline import measure_pair


def test_offline_pair_measures_retention_without_model_calls():
    report = measure_pair(7_000)

    assert report["model_requests"] == 0
    assert report["model_cost_usd"] == 0
    assert report["model_efficacy_claimed"] is False
    assert report["baseline"]["test_result_intact"] is True
    assert report["selector"]["test_result_intact"] is True
    assert report["selector"]["test_evidence_retained_chars"] > report["baseline"]["test_evidence_retained_chars"]
    assert report["delta"]["test_evidence_retention_ratio"] > 1
