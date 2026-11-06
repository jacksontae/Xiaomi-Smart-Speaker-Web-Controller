"""My files: uploaded audio, checked by content, with a size limit and a quota."""
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import HTTPException, Query, Request

from server import config, core
from server.access import Who, media_url, operator_api, record, viewer_api
from server.accounts import can_see, owns, personal_owner, with_rights
from server.auth import ROLE_RANK
from server.config import FILE_TYPES, UPLOAD_TITLE_MAX
from server.playback import play_source
from server.schemas import FilePatch, FilePlayBody, clean_text

# --- My files (uploaded audio) ---

def sniff_audio(head):
    """FILE_TYPES extension for the audio format these first bytes start, or None."""
    if head.startswith(b"ID3"):
        return ".mp3"
    if len(head) >= 2 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0:
        return ".aac"  # ADTS frame (layer bits 00)
    if len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0 and head[1] & 0x06:
        return ".mp3"  # MPEG audio frame without an ID3 tag
    if head[4:8] == b"ftyp":
        return ".m4a"
    if head.startswith(b"OggS"):
        return ".ogg"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return ".wav"
    if head.startswith(b"fLaC"):
        return ".flac"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return ".webm"
    return None


def can_edit_file(row, who):
    """Admins any file; a personal file its owner; a shared one the operator who uploaded it."""
    if who.role == "admin" or owns(row, who):
        return True
    return (row["owner_id"] is None and ROLE_RANK[who.role] >= ROLE_RANK["operator"]
            and who.user is not None and row["uploader_id"] == who.user["id"])


def public_file(row, who):
    return with_rights({k: v for k, v in row.items() if k != "stored_name"}, who, can_edit_file)


def file_or_404(file_id, who):
    """The file if the caller may see it, else 404 (someone else's personal file looks missing)."""
    row = core.db.get_file(file_id)
    if row is None or not can_see(row, who):
        raise HTTPException(404, "No such file")
    return row


def check_file_owner(row, who):
    if not can_edit_file(row, who):
        raise HTTPException(403, "Only the member who uploaded this file or an admin can change it")


@viewer_api.get("/files")
async def list_files(who: Who):
    return {
        "items": [public_file(r, who) for r in core.db.list_files() if can_see(r, who)],
        "used": core.db.files_size(),
        "quota": config.UPLOAD_QUOTA,
        "max_size": config.UPLOAD_MAX,
        "types": sorted(FILE_TYPES),
    }


@viewer_api.post("/files")
async def upload_file(
    request: Request,
    who: Who,
    name: Annotated[str, Query(min_length=1, max_length=255)],
    duration: Annotated[float | None, Query(ge=0, le=24 * 3600)] = None,
    personal: bool = False,
):
    """The request body is the audio file itself (not a form); `name` is its original file name and
    `duration` (seconds, optional) what the browser measured. The format is checked from the content.
    A viewer's upload is personal; operators and admins share theirs unless `personal=1`."""
    owner_id = personal_owner(who, personal)
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > config.UPLOAD_MAX:
        raise HTTPException(413, f"Files can be at most {config.UPLOAD_MAX // (1024 * 1024)} MB")
    room = config.UPLOAD_QUOTA - core.db.files_size()
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    part = config.MEDIA_DIR / f".upload-{secrets.token_hex(8)}.part"
    size, head = 0, b""
    try:
        with part.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > config.UPLOAD_MAX:
                    raise HTTPException(413, f"Files can be at most {config.UPLOAD_MAX // (1024 * 1024)} MB")
                if size > room:
                    raise HTTPException(507, "Not enough upload space left; delete some files first")
                if len(head) < 64:
                    head = (head + chunk)[:64]
                f.write(chunk)  # small chunks to the local disk; not worth a thread hop each
        if not size:
            raise HTTPException(400, "The file is empty")
        ext = sniff_audio(head)
        if ext is None:
            raise HTTPException(415, f"Not a supported audio file (use {', '.join(sorted(FILE_TYPES))})")
        stored = f"{secrets.token_urlsafe(12)}{ext}"
        part.rename(config.MEDIA_DIR / stored)
    finally:
        part.unlink(missing_ok=True)
    original = Path(name.replace("\\", "/")).name.strip()[:255] or "upload"
    title = Path(original).stem.strip()[:UPLOAD_TITLE_MAX] or "Untitled"
    row = core.db.add_file(stored, title, original, FILE_TYPES[ext], size, duration, who.user and who.user["id"],
                           owner_id)
    record(who, "file upload", f"{title} ({size // 1024} KB)")
    return public_file(row, who)


@viewer_api.patch("/files/{file_id}")
async def rename_file(file_id: int, body: FilePatch, who: Who):
    row = file_or_404(file_id, who)
    check_file_owner(row, who)
    title = clean_text(body.title, "title", UPLOAD_TITLE_MAX)
    record(who, "file rename", f"{row['title']} -> {title}"[:200])
    return public_file(core.db.rename_file(file_id, title), who)


@viewer_api.delete("/files/{file_id}", status_code=204)
async def delete_file(file_id: int, who: Who):
    row = file_or_404(file_id, who)
    check_file_owner(row, who)
    if core.db.delete_file(file_id) is None:
        raise HTTPException(404, "No such file")
    (config.MEDIA_DIR / row["stored_name"]).unlink(missing_ok=True)
    record(who, "file delete", row["title"])


@operator_api.post("/files/{file_id}/play")
async def play_file(file_id: int, body: FilePlayBody, who: Who):
    row = file_or_404(file_id, who)
    if not (config.MEDIA_DIR / row["stored_name"]).is_file():
        raise HTTPException(410, "The file is missing from the server's disk")
    url = media_url(f"/media/{row['stored_name']}")
    return await play_source(url, row["content_type"], row["title"], body.volume, who, "file play")
