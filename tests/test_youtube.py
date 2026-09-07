import json
import types

import pytest

from shorts.youtube import SCOPES, YouTubeAuthError, get_credentials


class _Cfg:
    def __init__(self, token_path):
        self.youtube = types.SimpleNamespace(
            token_path=token_path, client_secret=None, category_id=22
        )


def _valid_token(path):
    path.write_text(json.dumps({
        "token": "at", "refresh_token": "rt", "client_id": "cid",
        "client_secret": "csec", "scopes": SCOPES,
        "token_uri": "https://oauth2.googleapis.com/token",
    }))


def test_scopes_exact():
    assert SCOPES == ["https://www.googleapis.com/auth/youtube.upload"]


def test_get_credentials_missing_file_raises(tmp_path):
    with pytest.raises(YouTubeAuthError) as ei:
        get_credentials(_Cfg(tmp_path / "nope.json"))
    assert ei.value.reason == "missing"


def test_get_credentials_valid_returned_as_is(tmp_path, monkeypatch):
    tok = tmp_path / "tok.json"
    _valid_token(tok)

    class FakeCreds:
        valid = True
        expired = False
        refresh_token = "rt"
        def to_json(self): return "{}"

    monkeypatch.setattr(
        "google.oauth2.credentials.Credentials.from_authorized_user_file",
        staticmethod(lambda *a, **k: FakeCreds()),
    )
    creds = get_credentials(_Cfg(tok))
    assert isinstance(creds, FakeCreds)


def test_get_credentials_refreshes_and_rewrites(tmp_path, monkeypatch):
    tok = tmp_path / "tok.json"
    _valid_token(tok)
    calls = {"refresh": 0}

    class FakeCreds:
        valid = False
        expired = True
        refresh_token = "rt"
        def refresh(self, _request): calls["refresh"] += 1
        def to_json(self): return '{"token": "new"}'

    monkeypatch.setattr(
        "google.oauth2.credentials.Credentials.from_authorized_user_file",
        staticmethod(lambda *a, **k: FakeCreds()),
    )
    get_credentials(_Cfg(tok))
    assert calls["refresh"] == 1
    assert tok.read_text() == '{"token": "new"}'


def test_get_credentials_refresh_error_is_expired(tmp_path, monkeypatch):
    from google.auth.exceptions import RefreshError
    tok = tmp_path / "tok.json"
    _valid_token(tok)

    class FakeCreds:
        valid = False
        expired = True
        refresh_token = "rt"
        def refresh(self, _request): raise RefreshError("bad")
        def to_json(self): return "{}"

    monkeypatch.setattr(
        "google.oauth2.credentials.Credentials.from_authorized_user_file",
        staticmethod(lambda *a, **k: FakeCreds()),
    )
    with pytest.raises(YouTubeAuthError) as ei:
        get_credentials(_Cfg(tok))
    assert ei.value.reason == "expired"
