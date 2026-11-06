"""Request bodies, and the text check the endpoints share."""
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

# --- Request bodies ---

Role = Literal["admin", "operator", "viewer"]
Repeat = Literal["off", "all", "one"]


class SayBody(BaseModel):
    text: str
    lang: str | None = None  # defaults to settings.tts_lang
    volume: float | None = None


class PlayBody(BaseModel):
    url: str
    content_type: str = "audio/mp3"
    volume: float | None = None


class YoutubeBody(BaseModel):
    query: str  # search words or a YouTube URL
    volume: float | None = None


class VolumeBody(BaseModel):
    level: float


class SeekBody(BaseModel):
    position: float


class SetupBody(BaseModel):
    api_token: str
    username: str
    display_name: str = ""
    password: str


class LoginBody(BaseModel):
    username: str
    password: str


class GoogleBody(BaseModel):
    credential: str = Field(max_length=8192)  # the ID token from Google Identity Services


class PasskeyBody(BaseModel):
    credential: dict  # the PublicKeyCredential from the browser, as JSON (base64url fields)
    name: str | None = None  # registration only; defaults to "Passkey"


class PasskeyName(BaseModel):
    name: str


class MeBody(BaseModel):
    display_name: str


class DeleteMeBody(BaseModel):
    confirm: str = Field(max_length=64)  # the member's username


class PasswordBody(BaseModel):
    current: str
    new: str


class NewUserBody(BaseModel):
    username: str
    display_name: str = ""
    password: str
    role: Role


class UserPatch(BaseModel):
    display_name: str | None = None
    role: Role | None = None
    password: str | None = None
    disabled: bool | None = None


class PlaylistBody(BaseModel):
    name: str


class NewPlaylistBody(PlaylistBody):
    personal: bool = False  # operators and admins: a personal playlist (a viewer's always is)


class ItemBody(BaseModel):
    """`source` per kind: youtube = URL/id/words, url/podcast = audio URL, tts = text,
    radio = radio-browser station uuid or stream URL, file = id of an uploaded file."""
    kind: Literal["youtube", "url", "tts", "radio", "podcast", "file"]
    source: str
    title: str | None = None
    lang: str | None = None
    thumbnail: str | None = None  # radio (stream URL) and podcast items
    duration: float | None = Field(None, ge=0)  # podcast items
    content_type: str | None = None  # radio (stream URL) and podcast items


class StationBody(BaseModel):
    """A radio-browser station (uuid) or a stream URL of your own (url + name)."""
    uuid: str | None = None
    url: str | None = None
    name: str | None = None
    content_type: str | None = None
    favicon: str | None = None


class RadioPlayBody(StationBody):
    favorite_id: int | None = None
    volume: float | None = Field(None, ge=0, le=1)


class EpisodePlayBody(BaseModel):
    url: str  # the episode's enclosure URL
    title: str
    thumbnail: str | None = None
    content_type: str | None = None
    volume: float | None = Field(None, ge=0, le=1)


class SubBody(BaseModel):
    """Follow a show; without a title the feed is read for its details."""
    feed_url: str
    title: str | None = None
    author: str | None = None
    artwork: str | None = None


class FilePatch(BaseModel):
    title: str


class FilePlayBody(BaseModel):
    volume: float | None = Field(None, ge=0, le=1)


class OrderBody(BaseModel):
    item_ids: list[int]


class PlayPlaylistBody(BaseModel):
    start_index: int = 0
    shuffle: bool = False
    repeat: Repeat = "off"


class JumpBody(BaseModel):
    index: int


class QueuePatch(BaseModel):
    shuffle: bool | None = None
    repeat: Repeat | None = None


class PhraseBody(BaseModel):
    text: str
    lang: str | None = None


class ScheduleBody(BaseModel):
    """POST takes the whole schedule, PATCH any subset; either way the result is validated as a whole."""
    name: str | None = None
    enabled: bool | None = None
    action: str | None = None
    text: str | None = None
    lang: str | None = None
    playlist_id: int | None = None
    shuffle: bool | None = None
    volume: float | None = None
    time: str | None = None
    days: list[int] | None = None
    date: str | None = None


def clean_text(value, field, max_len):
    value = value.strip()
    if not value:
        raise HTTPException(400, f"{field} is empty")
    if len(value) > max_len:
        raise HTTPException(400, f"{field} is longer than {max_len} characters")
    return value
