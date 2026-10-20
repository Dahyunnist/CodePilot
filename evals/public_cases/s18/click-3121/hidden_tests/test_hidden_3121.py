from __future__ import annotations

import click
from click.testing import CliRunner


class Handler:
    pass


def test_default_map_override_and_callable_keep_existing_behavior() -> None:
    @click.command()
    @click.option("--handler", "kind", flag_value=Handler, type=click.UNPROCESSED, default=True)
    def command(kind: object) -> None:
        click.echo("class" if kind is Handler else type(kind).__name__)

    runner = CliRunner()
    override = runner.invoke(command, [], default_map={"kind": "configured"})
    callable_override = runner.invoke(
        command, [], default_map={"kind": lambda: "from callable"}
    )

    assert override.exit_code == 0, override.output
    assert override.output == "str\n"
    assert callable_override.exit_code == 0, callable_override.output
    assert callable_override.output == "str\n"
