import pytest

from codepilot.security import is_sensitive_file, redact_sensitive_text


@pytest.mark.parametrize(
    "path",
    [
        ".aws/credentials",
        ".aws/config",
        ".ssh/id_rsa",
        ".ssh/id_ed25519",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "credentials.json",
        "secrets.json",
        "private.p12",
    ],
)
def test_common_credential_paths_are_sensitive(path):
    assert is_sensitive_file(path)


@pytest.mark.parametrize("path", ["src/credentials_loader.py", "docs/secrets.md"])
def test_noncredential_paths_are_not_overclassified(path):
    assert not is_sensitive_file(path)


def test_redactor_covers_cloud_and_compound_credential_labels():
    values = {
        "aws_secret_access_key": "FAKE_AWS_SECRET_0123456789",
        "client_secret": "FAKE_CLIENT_SECRET_0123456789",
        "credentials": "FAKE_CREDENTIALS_0123456789",
        "token": "FAKE_SESSION_TOKEN_0123456789",
        "authorization": "Basic ZmFrZTpmYWtl",
    }
    text = "\n".join(f"{key}={value}" for key, value in values.items())

    redacted = redact_sensitive_text(text)

    assert all(value not in redacted for value in values.values())
    assert redacted.count("[REDACTED]") == len(values)
