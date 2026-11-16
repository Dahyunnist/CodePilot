"""Minimal behavior extracted from Flask 1.0.1/1.0.2 routes_command."""
import click
from click.testing import CliRunner

@click.command()
def base_routes():
    rules = []
    max(len(rule.endpoint) for rule in rules)

@click.command()
def fixed_routes():
    rules = []
    if not rules:
        click.echo("No routes were registered.")
        return
    max(len(rule.endpoint) for rule in rules)

def test_flask_101_empty_routes_reproduces_max_error():
    result = CliRunner().invoke(base_routes)
    assert isinstance(result.exception, ValueError)
    assert "max() arg is an empty sequence" in str(result.exception)

def test_flask_102_empty_routes_reports_no_routes():
    result = CliRunner().invoke(fixed_routes)
    assert result.exit_code == 0
    assert result.output == "No routes were registered.\n"
