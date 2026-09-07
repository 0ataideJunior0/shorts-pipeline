from __future__ import annotations

import http.client
import os
import time
from pathlib import Path

from shorts.config import Config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeAuthError(Exception):
    def __init__(self, message: str, *, reason: str = "missing") -> None:
        super().__init__(message)
        self.reason = reason


class YouTubeConfigError(Exception):
    pass


_HINT = "run: python -m shorts youtube auth"


def get_credentials(config: Config):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path: Path = config.youtube.token_path
    if not path.exists():
        raise YouTubeAuthError(f"no YouTube token - {_HINT}", reason="missing")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            raise YouTubeAuthError(
                f"YouTube token expired - {_HINT}", reason="expired"
            ) from exc
        path.write_text(creds.to_json())
        return creds
    raise YouTubeAuthError(f"YouTube token unusable - {_HINT}", reason="missing")


def authorize(config: Config):
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not config.youtube.client_secret:
        raise YouTubeConfigError("set [youtube] client_secret in config.toml")
    flow = InstalledAppFlow.from_client_secrets_file(
        config.youtube.client_secret, SCOPES
    )
    creds = flow.run_local_server(port=0)
    path: Path = config.youtube.token_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json())
    os.chmod(path, 0o600)
    return creds


def youtube_service(credentials):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def channel_title(credentials) -> str:
    resp = (
        youtube_service(credentials)
        .channels()
        .list(mine=True, part="snippet")
        .execute()
    )
    items = resp.get("items", [])
    return items[0]["snippet"]["title"] if items else ""


def insert_video(service, *, mp4_path: Path, body: dict, max_retries: int = 5) -> dict:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(mp4_path), mimetype="video/*", resumable=True)
    request = service.videos().insert(
        part="snippet,status", body=body, media_body=media
    )
    response = None
    tries = 0
    while response is None:
        try:
            _status, response = request.next_chunk()
        except HttpError as exc:
            if getattr(exc.resp, "status", None) in (500, 502, 503, 504) and tries < max_retries:
                tries += 1
                time.sleep(2 ** tries)
                continue
            raise
        except (ConnectionError, TimeoutError, http.client.HTTPException):
            if tries < max_retries:
                tries += 1
                time.sleep(2 ** tries)
                continue
            raise
    return {"video_id": response["id"], "url": f"https://youtu.be/{response['id']}"}
