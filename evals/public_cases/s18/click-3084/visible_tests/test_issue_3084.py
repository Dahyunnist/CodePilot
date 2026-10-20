from __future__ import annotations

import click
from click.testing import CliRunner


def test_optional_flag_value_uses_flag_value_when_present() -> None:
    @click.command()
    @click.option("--name", is_flag=False, flag_value="Flag", default="Default")
    def command(name: str) -> None:
        click.echo(name)

    result = CliRunner().invoke(command, ["--name"])

    assert result.exit_code == 0, result.output
    assert result.output == "Flag\n"


def test_optional_flag_value_keeps_explicit_and_default_values() -> None:
    @click.command()
    @click.option("--name", is_flag=False, flag_value="Flag", default="Default")
    def command(name: str) -> None:
        click.echo(name)

    runner = CliRunner()
    explicit = runner.invoke(command, ["--name", "Chosen"])
    default = runner.invoke(command, [])

    assert explicit.exit_code == 0, explicit.output
    assert explicit.output == "Chosen\n"
    assert default.exit_code == 0, default.output
    assert default.output == "Default\n"
