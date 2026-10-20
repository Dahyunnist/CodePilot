import click


def test_missing_lookup_default_returns_none_for_both_call_modes():
    context = click.Context(click.Command("hidden"), info_name=None)
    context.default_map = {}

    assert context.lookup_default("missing", call=False) is None
    assert context.lookup_default("missing", call=True) is None


def test_explicit_default_and_callable_default_are_preserved():
    context = click.Context(click.Command("hidden"), info_name=None)
    context.default_map = {
        "plain": "explicit",
        "callable": lambda: "called",
    }

    assert context.lookup_default("plain", call=False) == "explicit"
    assert context.lookup_default("callable", call=False) is not None
    assert context.lookup_default("callable", call=True) == "called"


def test_explicit_none_default_remains_none():
    context = click.Context(click.Command("hidden"), info_name=None)
    context.default_map = {"explicit_none": None}

    assert context.lookup_default("explicit_none", call=False) is None
