"""Slug formatting helpers."""


def user_slug(name: str) -> str:
    return name.strip().lower().replace(" ", "-")


def project_slug(name: str) -> str:
    return name.strip().lower().replace("_", "-")
