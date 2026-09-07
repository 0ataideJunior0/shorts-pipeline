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


class _FakeResp:
    def __init__(self, status): self.status = status


class _FakeHttpError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.resp = _FakeResp(status)


class _FakeRequest:
    """next_chunk() yields (None, response) after `fail_times` transient errors."""
    def __init__(self, fail_times=0, status=503):
        self.fail_times = fail_times
        self.status = status
        self.calls = 0

    def next_chunk(self):
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise _FakeHttpError(self.status)
        return (None, {"id": "vid123"})


class _FakeService:
    def __init__(self, request): self._request = request
    def videos(self): return self
    def insert(self, **_kw): return self._request


def test_insert_video_success(tmp_path, monkeypatch):
    import shorts.youtube as yt
    monkeypatch.setattr(yt, "MediaFileUpload", None, raising=False)
    # patch the lazy imports inside insert_video
    monkeypatch.setattr(
        "googleapiclient.http.MediaFileUpload",
        lambda *a, **k: object(), raising=False,
    )
    monkeypatch.setattr("googleapiclient.errors.HttpError", _FakeHttpError, raising=False)
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"x")
    res = yt.insert_video(_FakeService(_FakeRequest()), mp4_path=mp4, body={"snippet": {}})
    assert res == {"video_id": "vid123", "url": "https://youtu.be/vid123"}


def test_insert_video_retries_transient(tmp_path, monkeypatch):
    import shorts.youtube as yt
    monkeypatch.setattr(
        "googleapiclient.http.MediaFileUpload", lambda *a, **k: object(), raising=False,
    )
    monkeypatch.setattr("googleapiclient.errors.HttpError", _FakeHttpError, raising=False)
    monkeypatch.setattr(yt.time, "sleep", lambda _s: None)
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"x")
    req = _FakeRequest(fail_times=2, status=503)
    res = yt.insert_video(_FakeService(req), mp4_path=mp4, body={"snippet": {}})
    assert res["video_id"] == "vid123"
    assert req.calls == 3


def test_insert_video_non_transient_reraises(tmp_path, monkeypatch):
    import shorts.youtube as yt
    monkeypatch.setattr(
        "googleapiclient.http.MediaFileUpload", lambda *a, **k: object(), raising=False,
    )
    monkeypatch.setattr("googleapiclient.errors.HttpError", _FakeHttpError, raising=False)
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"x")
    with pytest.raises(_FakeHttpError):
        yt.insert_video(_FakeService(_FakeRequest(fail_times=1, status=400)),
                        mp4_path=mp4, body={"snippet": {}})
