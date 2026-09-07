from click.testing import CliRunner

import shorts.cli as cli


def _no_config(monkeypatch):
    # bypass load_config; the commands only need cfg.youtube for these paths
    import types
    fake = types.SimpleNamespace(youtube=types.SimpleNamespace(
        client_secret=None, token_path=None, category_id=22))
    monkeypatch.setattr(cli, "_config", lambda ctx: fake)


def test_youtube_status_connected(monkeypatch):
    _no_config(monkeypatch)
    import shorts.youtube as yt
    monkeypatch.setattr(yt, "get_credentials", lambda c: object())
    monkeypatch.setattr(yt, "channel_title", lambda c: "My Channel")
    r = CliRunner().invoke(cli.cli, ["youtube", "status"])
    assert r.exit_code == 0
    assert "connected: My Channel" in r.output


def test_youtube_status_needs_auth(monkeypatch):
    _no_config(monkeypatch)
    import shorts.youtube as yt
    def boom(c):
        raise yt.YouTubeAuthError("YouTube token expired - run: python -m shorts youtube auth",
                                  reason="expired")
    monkeypatch.setattr(yt, "get_credentials", boom)
    r = CliRunner().invoke(cli.cli, ["youtube", "status"])
    assert r.exit_code == 0
    assert "run: python -m shorts youtube auth" in r.output


def test_publish_invokes_run(monkeypatch):
    _no_config(monkeypatch)
    monkeypatch.setattr(cli, "_resolve", lambda cfg, name: f"project:{name}")
    import shorts.publish as pub
    seen = {}
    monkeypatch.setattr(pub, "run",
        lambda project, config, *, slugs, force: seen.update(project=project, slugs=slugs, force=force))
    r = CliRunner().invoke(cli.cli, ["publish", "demo", "--slug", "01-x", "--slug", "02-y", "--force"])
    assert r.exit_code == 0
    assert seen == {"project": "project:demo", "slugs": ["01-x", "02-y"], "force": True}
