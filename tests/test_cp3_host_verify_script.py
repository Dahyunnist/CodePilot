from scripts.verify_cp3_cli_e2e import NODE_IDS, TESTS, _failure_class


def test_host_verification_script_targets_only_the_seven_cli_e2e_cases():
    assert len(TESTS) == 7
    assert all(node.startswith("tests/test_cli_e2e.py::") for node in NODE_IDS)


def test_host_verification_failure_classification_does_not_return_raw_details():
    secret = "sk-local-secret-value"
    private_path = r"C:\Users\private\project"
    result = _failure_class(
        f"NtCreateDirectoryObject 0xC0000022 {private_path} {secret}"
    )

    assert result == "host_acl_blocked"
    assert secret not in result
    assert private_path not in result


def test_host_verification_classifies_non_acl_failure_without_echoing_output():
    secret = "token=private-value"
    result = _failure_class(f"AssertionError {secret}")

    assert result == "test_failure"
    assert secret not in result
