from __future__ import annotations

import click
from click.testing import CliRunner


class Decoder:
    pass


def test_class_flag_value_remains_class_when_defaulted() -> None:
    @click.command()
    @click.option("--decoder", "kind", flag_value=Decoder, type=click.UNPROCESSED, default=True)
    def command(kind: object) -> None:
        click.echo("class" if kind is Decoder else type(kind).__name__)

    result = CliRunner().invoke(command, [])

    assert result.exit_code == 0, result.output
    assert result.output == "class\n"


def test_class_flag_value_remains_class_when_option_is_used() -> None:
    @click.command()
    @click.option("--decoder", "kind", flag_value=Decoder, type=click.UNPROCESSED, default=True)
    def command(kind: object) -> None:
        click.echo("class" if kind is Decoder else type(kind).__name__)

    result = CliRunner().invoke(command, ["--decoder"])

    assert result.exit_code == 0, result.output
    assert result.output == "class\n"
