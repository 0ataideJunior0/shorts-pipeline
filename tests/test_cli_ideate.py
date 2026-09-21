import pytest
from click.testing import CliRunner

import shorts.cli as cli


@pytest.fixture
def runner():
    return CliRunner()


def test_ideate_with_count(runner, monkeypatch):
    monkeypatch.setattr(cli, "_config", lambda ctx: object())
    monkeypatch.setattr(cli, "_resolve", lambda cfg, name: f"project:{name}")
    seen = {}

    def fake_run(project, config, *, force, count=None):
        seen["project"] = project
        seen["config"] = config
        seen["force"] = force
        seen["count"] = count

    monkeypatch.setattr(cli.ideate_stage, "run", fake_run)

    r = runner.invoke(cli.cli, ["ideate", "demo", "--count", "4"])
    assert r.exit_code == 0
    assert seen["project"] == "project:demo"
    assert seen["force"] is False
    assert seen["count"] == 4


def test_ideate_without_count(runner, monkeypatch):
    monkeypatch.setattr(cli, "_config", lambda ctx: object())
    monkeypatch.setattr(cli, "_resolve", lambda cfg, name: f"project:{name}")
    seen = {}

    def fake_run(project, config, *, force, count=None):
        seen["project"] = project
        seen["config"] = config
        seen["force"] = force
        seen["count"] = count

    monkeypatch.setattr(cli.ideate_stage, "run", fake_run)

    r = runner.invoke(cli.cli, ["ideate", "demo"])
    assert r.exit_code == 0
    assert seen["project"] == "project:demo"
    assert seen["force"] is False
    assert seen["count"] is None


def test_ideate_with_count_zero(runner, monkeypatch):
    monkeypatch.setattr(cli, "_config", lambda ctx: object())
    monkeypatch.setattr(cli, "_resolve", lambda cfg, name: f"project:{name}")

    r = runner.invoke(cli.cli, ["ideate", "demo", "--count", "0"])
    assert r.exit_code != 0


def test_ideate_with_force_and_count(runner, monkeypatch):
    monkeypatch.setattr(cli, "_config", lambda ctx: object())
    monkeypatch.setattr(cli, "_resolve", lambda cfg, name: f"project:{name}")
    seen = {}

    def fake_run(project, config, *, force, count=None):
        seen["project"] = project
        seen["config"] = config
        seen["force"] = force
        seen["count"] = count

    monkeypatch.setattr(cli.ideate_stage, "run", fake_run)

    r = runner.invoke(cli.cli, ["ideate", "demo", "--force", "--count", "2"])
    assert r.exit_code == 0
    assert seen["project"] == "project:demo"
    assert seen["force"] is True
    assert seen["count"] == 2
