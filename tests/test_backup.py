"""deploy/remote/backup.py: consistent SQLite snapshots, retention, owner-only files, restore."""
import importlib.util
import sqlite3
import stat
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "remote_backup", Path(__file__).resolve().parents[1] / "deploy" / "remote" / "backup.py"
)
backup = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(backup)


@pytest.fixture
def cfg(tmp_path):
    data = tmp_path / "data" / "data.db"
    data.parent.mkdir()
    db = sqlite3.connect(data)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("CREATE TABLE t (v TEXT)")
    db.execute("INSERT INTO t VALUES ('before')")
    db.commit()
    db.close()
    (data.parent / "config.json").write_text('{"api_token": "change-me"}\n')
    return {
        "data": data,
        "config": data.parent / "config.json",
        "dir": tmp_path / "backups",
        "keep": 3,
        "time": "03:30",
    }


def _rows(path):
    db = sqlite3.connect(path)
    try:
        return [r[0] for r in db.execute("SELECT v FROM t ORDER BY rowid")]
    finally:
        db.close()


def test_backup_includes_uncheckpointed_wal_writes(cfg, tmp_path):
    # A writer holds the database open with changes still in the -wal file: a raw copy of data.db
    # would miss them; the online backup must not.
    live = sqlite3.connect(cfg["data"])
    live.execute("PRAGMA wal_autocheckpoint = 0")
    live.execute("INSERT INTO t VALUES ('in-wal')")
    live.commit()
    try:
        path = backup.make_backup(cfg, datetime(2026, 10, 30, 3, 30, tzinfo=UTC))
    finally:
        live.close()
    assert path.name == "speaker-20261030-033000.tar.gz"
    with tarfile.open(path) as tar:
        assert sorted(tar.getnames()) == ["config.json", "data.db"]
        assert all(m.mode == 0o600 for m in tar.getmembers())
        tar.extractall(tmp_path / "out", filter="data")
    assert _rows(tmp_path / "out" / "data.db") == ["before", "in-wal"]
    assert "change-me" in (tmp_path / "out" / "config.json").read_text()


def test_backup_files_are_owner_only(cfg):
    path = backup.make_backup(cfg)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(cfg["dir"].stat().st_mode) == 0o700
    assert [p.name for p in cfg["dir"].iterdir()] == [path.name]  # no temp files left behind


def test_backup_without_config_still_saves_database(cfg):
    cfg["config"].unlink()
    with tarfile.open(backup.make_backup(cfg)) as tar:
        assert tar.getnames() == ["data.db"]


def test_missing_database_fails_without_creating_one(cfg):
    cfg["data"].unlink()
    with pytest.raises(FileNotFoundError):
        backup.make_backup(cfg)
    assert not cfg["data"].exists()


def test_prune_keeps_the_newest(cfg):
    for day in range(1, 6):
        backup.make_backup(cfg, datetime(2026, 10, day, 3, 30, tzinfo=UTC))
    removed = backup.prune(cfg["dir"], cfg["keep"])
    assert [p.name for p in removed] == ["speaker-20261001-033000.tar.gz", "speaker-20261002-033000.tar.gz"]
    assert [p.name for p in backup.list_backups(cfg["dir"])] == [
        "speaker-20261003-033000.tar.gz",
        "speaker-20261004-033000.tar.gz",
        "speaker-20261005-033000.tar.gz",
    ]


def test_schedule_helpers(cfg):
    now = datetime(2026, 10, 30, 2, 0, tzinfo=UTC)
    assert backup.next_run(now, "03:30") == datetime(2026, 10, 30, 3, 30, tzinfo=UTC)
    assert backup.next_run(now.replace(hour=4), "03:30") == datetime(2026, 10, 31, 3, 30, tzinfo=UTC)
    assert backup.overdue(cfg["dir"], now)  # no backups yet
    backup.make_backup(cfg, datetime(2026, 10, 29, 3, 30, tzinfo=UTC))
    assert not backup.overdue(cfg["dir"], now)
    assert backup.overdue(cfg["dir"], datetime(2026, 10, 30, 4, 0, tzinfo=UTC))


def test_restore_puts_back_database_and_config_and_keeps_current(cfg):
    path = backup.make_backup(cfg)
    db = sqlite3.connect(cfg["data"])
    db.execute("INSERT INTO t VALUES ('after')")
    db.commit()
    db.close()
    cfg["config"].write_text("{}\n")
    stale_wal = cfg["data"].with_name("data.db-wal")
    stale_wal.write_bytes(b"stale")

    backup.restore(cfg, path.name, now=datetime(2026, 10, 30, 12, 0, tzinfo=UTC))

    assert _rows(cfg["data"]) == ["before"]
    assert "change-me" in cfg["config"].read_text()
    assert stat.S_IMODE(cfg["config"].stat().st_mode) == 0o600
    kept = cfg["data"].with_name("data.db.before-restore-20261030-120000")
    assert _rows(kept) == ["before", "after"]
    assert cfg["data"].with_name("data.db-wal.before-restore-20261030-120000").read_bytes() == b"stale"
    assert cfg["config"].with_name("config.json.before-restore-20261030-120000").read_text() == "{}\n"


def test_restore_rejects_unknown_or_path_names(cfg, tmp_path):
    with pytest.raises(FileNotFoundError):
        backup.restore(cfg, "speaker-nope.tar.gz")
    outside = tmp_path / "speaker-20261030-000000.tar.gz"
    outside.write_bytes(b"")
    with pytest.raises(FileNotFoundError):  # only names inside BACKUP_DIR are accepted
        backup.restore(cfg, str(outside))


def test_cli_now_and_list(cfg, monkeypatch, capsys):
    monkeypatch.setenv("DATA_PATH", str(cfg["data"]))
    monkeypatch.setenv("CONFIG_PATH", str(cfg["config"]))
    monkeypatch.setenv("BACKUP_DIR", str(cfg["dir"]))
    assert backup.main(["--list"]) == 0
    assert "no backups yet" in capsys.readouterr().out
    assert backup.main(["--now"]) == 0
    assert backup.main(["--list"]) == 0
    assert backup.PREFIX in capsys.readouterr().out
