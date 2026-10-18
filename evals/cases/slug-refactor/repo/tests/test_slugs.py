from slugs import project_slug, user_slug


def test_project_slug_normalizes_spaces_and_underscores() -> None:
    assert project_slug("My_Project Name") == "my-project-name"


def test_user_slug_normalizes_spaces() -> None:
    assert user_slug("Ada Lovelace") == "ada-lovelace"
