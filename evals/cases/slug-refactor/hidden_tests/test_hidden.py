from slugs import normalize_slug, user_slug


def test_shared_helper_is_available() -> None:
    assert normalize_slug(" Mixed_Name Value ") == "mixed-name-value"


def test_user_slug_uses_shared_underscore_behavior() -> None:
    assert user_slug("Ada_Lovelace") == "ada-lovelace"
