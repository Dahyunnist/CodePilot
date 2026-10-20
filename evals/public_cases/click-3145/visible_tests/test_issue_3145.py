import click


class PrefixFallbackContext(click.Context):
    def lookup_default(self, name: str, call: bool = False):
        default = super().lookup_default(name, call=call)
        if default is not None:
            return default
        prefix, _, option = name.partition("_")
        group = getattr(self, "default_map", {}).get(prefix)
        if group:
            return group.get(option)
        return default


def test_missing_value_allows_prefix_default_fallback():
    context = PrefixFallbackContext(click.Command("get-views"), info_name=None)
    context.default_map = {"app": {"email": "prefix@example.com"}}

    assert context.lookup_default("app_email", call=False) == "prefix@example.com"


def test_missing_value_without_prefix_fallback_is_none():
    context = PrefixFallbackContext(click.Command("get-views"), info_name=None)
    context.default_map = {}

    assert context.lookup_default("app_email", call=False) is None
