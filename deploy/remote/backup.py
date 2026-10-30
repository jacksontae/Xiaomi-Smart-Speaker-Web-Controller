"""Nightly backups of the speaker service's database and settings (runs as the `backup` compose service).

Each backup is one gzip tarball, `speaker-YYYYMMDD-HHMMSS.tar.gz`, holding `data.db` (a consistent copy
made with SQLite's online backup API while the service keeps running; never a raw file copy) and
`config.json`. Files are written owner-only (0600, directory 0700) because they hold password hashes,
session data and the API token. Only the newest BACKUP_KEEP backups are kept.

    python backup.py --daemon            every day at BACKUP_TIME (HH:MM, UTC); also at start-up when the
                                         newest backup is older than a day (e.g. the VM was off at night)
    python backup.py --now               one backup now
    python backup.py --list
    python backup.py --restore NAME      stop the service first; the current files are kept as *.before-restore-*

Paths and settings come from the environment: DATA_PATH, CONFIG_PATH (as for the service), BACKUP_DIR,
BACKUP_KEEP (default 14) and BACKUP_TIME (default 03:30).
"""

import argparse
import os
import sqlite3
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

PREFIX, SUFFIX = "speaker-", ".tar.gz"
DAY = timedelta(days=1)


def log(msg: str) -> None:
    print(f"[backup] {msg}", flush=True)


def settings() -> dict:
    return {
        "data": Path(os.environ.get("DATA_PATH", "/data/data.db")),
        "config": Path(os.environ.get("CONFIG_PATH", "/data/config.json")),
        "dir": Path(os.environ.get("BACKUP_DIR", "/backups")),
        "keep": max(1, int(os.environ.get("BACKUP_KEEP", "14"))),
        "time": os.environ.get("BACKUP_TIME", "03:30"),
    }


def list_backups(backup_dir: Path) -> list[Path]:
    """Oldest first; the timestamp in the name sorts correctly as text."""
    if not backup_dir.is_dir():
        return []
    return sorted(p for p in backup_dir.iterdir() if p.name.startswith(PREFIX) and p.name.endswith(SUFFIX))


def snapshot_db(src_path: Path, dst_path: Path) -> None:
    """Copy a live SQLite database (WAL included) page by page, then check the copy."""
    # Opened read-write like the service (same user): a read-only open of a WAL database fails while the
    # service is stopped and no -shm file exists. The backup itself only reads.
    src = sqlite3.connect(src_path, timeout=30)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
        result = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"backup copy failed its integrity check: {result}")
    finally:
        dst.close()
        src.close()


def _add_file(tar: tarfile.TarFile, path: Path, name: str) -> None:
    info = tar.gettarinfo(str(path), arcname=name)
    info.mode, info.uid, info.gid, info.uname, info.gname = 0o600, 0, 0, "", ""
    with path.open("rb") as f:
        tar.addfile(info, f)


def make_backup(cfg: dict, now: datetime | None = None) -> Path:
    """Write one backup atomically (temp file, then rename) and return its path."""
    now = now or datetime.now(UTC)
    backup_dir: Path = cfg["dir"]
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.chmod(0o700)
    if not cfg["data"].exists():
        raise FileNotFoundError(f"no database at {cfg['data']}")
    final = backup_dir / f"{PREFIX}{now:%Y%m%d-%H%M%S}{SUFFIX}"
    with tempfile.TemporaryDirectory(dir=backup_dir, prefix=".tmp-") as tmp:
        db_copy = Path(tmp) / "data.db"
        snapshot_db(cfg["data"], db_copy)
        partial = Path(tmp) / "backup.tar.gz"
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as raw, tarfile.open(fileobj=raw, mode="w:gz") as tar:
            _add_file(tar, db_copy, "data.db")
            if cfg["config"].exists():
                _add_file(tar, cfg["config"], "config.json")
        os.replace(partial, final)
    return final


def prune(backup_dir: Path, keep: int) -> list[Path]:
    old = list_backups(backup_dir)[:-keep]
    for p in old:
        p.unlink()
    return old


def run_once(cfg: dict) -> Path:
    path = make_backup(cfg)
    removed = prune(cfg["dir"], cfg["keep"])
    log(f"wrote {path.name} ({path.stat().st_size} bytes); removed {len(removed)} old")
    return path


def backup_time(name: str) -> datetime:
    return datetime.strptime(name[len(PREFIX) : -len(SUFFIX)], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)


def next_run(now: datetime, at: str) -> datetime:
    hour, minute = (int(x) for x in at.split(":"))
    run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return run if run > now else run + DAY


def overdue(backup_dir: Path, now: datetime) -> bool:
    backups = list_backups(backup_dir)
    return not backups or now - backup_time(backups[-1].name) > DAY


def daemon(cfg: dict) -> None:
    next_run(datetime.now(UTC), cfg["time"])  # fail fast on a bad BACKUP_TIME
    log(f"daily at {cfg['time']} UTC into {cfg['dir']}, keeping {cfg['keep']}")
    if overdue(cfg["dir"], datetime.now(UTC)):
        _safe_run(cfg)
    while True:
        wait = (next_run(datetime.now(UTC), cfg["time"]) - datetime.now(UTC)).total_seconds()
        time.sleep(max(1.0, wait))
        _safe_run(cfg)


def _safe_run(cfg: dict) -> None:
    try:
        run_once(cfg)
    except Exception as e:  # keep the schedule; the next night tries again
        log(f"FAILED: {e}")


def restore(cfg: dict, name: str, now: datetime | None = None) -> None:
    """Put a backup's data.db (and config.json) back. The service must be stopped."""
    src = cfg["dir"] / Path(name).name
    if not src.is_file():
        raise FileNotFoundError(f"no backup {src}")
    stamp = f"{(now or datetime.now(UTC)):%Y%m%d-%H%M%S}"
    targets = {"data.db": cfg["data"], "config.json": cfg["config"]}
    with tarfile.open(src, "r:gz") as tar:
        members = {m.name: m for m in tar.getmembers() if m.name in targets and m.isfile()}
        if "data.db" not in members:
            raise ValueError(f"{src.name} has no data.db")
        for arcname, member in members.items():
            dest: Path = targets[arcname]
            data = tar.extractfile(member).read()
            staged = dest.with_name(f".{dest.name}.restore")
            fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            if arcname == "data.db":
                check = sqlite3.connect(staged)
                ok = check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                check.close()
                if not ok:
                    staged.unlink()
                    raise RuntimeError(f"{src.name}: data.db failed its integrity check; nothing restored")
                # A WAL left from the current database must not be replayed onto the restored one.
                for extra in ("-wal", "-shm"):
                    side = dest.with_name(dest.name + extra)
                    if side.exists():
                        side.rename(side.with_name(f"{side.name}.before-restore-{stamp}"))
            if dest.exists():
                dest.rename(dest.with_name(f"{dest.name}.before-restore-{stamp}"))
            os.replace(staged, dest)
            log(f"restored {arcname} -> {dest}")


def main(argv: list[str] | None = None) -> int:
    old_umask = os.umask(0o077)  # nothing this writes is meant for other users
    try:
        return _main(argv)
    finally:
        os.umask(old_umask)


def _main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--daemon", action="store_true")
    group.add_argument("--now", action="store_true")
    group.add_argument("--list", action="store_true")
    group.add_argument("--restore", metavar="NAME")
    args = parser.parse_args(argv)
    cfg = settings()
    if args.daemon:
        daemon(cfg)
    elif args.now:
        run_once(cfg)
    elif args.list:
        backups = list_backups(cfg["dir"])
        for p in backups:
            print(f"{p.name}  {p.stat().st_size:>10} bytes")
        if not backups:
            print("no backups yet")
    else:
        restore(cfg, args.restore)
    return 0


if __name__ == "__main__":
    sys.exit(main())
