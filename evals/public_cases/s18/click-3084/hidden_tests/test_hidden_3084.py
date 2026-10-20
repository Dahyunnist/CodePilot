from __future__ import annotations

import click
from click.testing import CliRunner


def test_optional_flag_value_does_not_consume_next_option() -> None:
    @click.command()
    @click.option("--name", is_flag=False, flag_value="Flag", default="Default")
    @click.option("--loud", is_flag=True)
    def command(name: str, loud: bool) -> None:
        click.echo(f"{name}:{loud}")

    result = CliRunner().invoke(command, ["--name", "--loud"])

    assert result.exit_code == 0, result.output
    assert result.output == "Flag:True\n"
