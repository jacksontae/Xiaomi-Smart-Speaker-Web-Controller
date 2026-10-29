"""SQLite storage for accounts, sessions, playlists, quick phrases and the activity log.

Every call opens its own short-lived connection, so the store is safe to use from any thread.
Writes that check-then-change (last-admin guard, reorder, first-run setup) run in one
`BEGIN IMMEDIATE` transaction so concurrent requests can't both pass the check.
"""
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1
SESSION_TTL = 30 * 24 * 3600
ACTIVITY_KEEP = 5000

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'operator', 'viewer')),
    password_hash TEXT NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS playlist_items (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('youtube', 'url', 'tts')),
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    duration REAL,
    thumbnail TEXT,
    lang TEXT
);
CREATE INDEX IF NOT EXISTS playlist_items_order ON playlist_items(playlist_id, position);
CREATE TABLE IF NOT EXISTS phrases (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    lang TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT
);
"""

ITEM_COLUMNS = "id, kind, title, source, duration, thumbnail, lang"


class Conflict(Exception):
    """A guard refused the change (maps to HTTP 409)."""


def now_iso():
    return datetime.now(UTC).isoformat(timespec="seconds")


def _user(row):
    if row is None:
        return None
    return {
        "id": row["id"], "username": row["username"], "display_name": row["display_name"], "role": row["role"],
        "disabled": bool(row["disabled"]), "created_at": row["created_at"], "last_login_at": row["last_login_at"],
    }


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self._coalesce = {}  # (actor, action) -> (row id, time) of the last coalesced activity row
        self._coalesce_lock = threading.Lock()
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA journal_mode = WAL")  # readers don't block the writer; persists in the file
        finally:
            db.close()
        with self.tx(immediate=True) as db:
            for statement in SCHEMA.split(";"):  # executescript() would commit our transaction
                if statement.strip():
                    db.execute(statement)
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def tx(self, immediate=False):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            db.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def schema_version(self):
        with self.tx() as db:
            return db.execute("PRAGMA user_version").fetchone()[0]

    # --- Users ---

    def user_count(self):
        with self.tx() as db:
            return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def create_first_admin(self, username, display_name, password_hash):
        """Create the first admin; None if someone else already finished setup."""
        with self.tx(immediate=True) as db:
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return None
            return self._insert_user(db, username, display_name, "admin", password_hash)

    def create_user(self, username, display_name, role, password_hash):
        with self.tx(immediate=True) as db:
            if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                raise Conflict("Username is already taken")
            return self._insert_user(db, username, display_name, role, password_hash)

    @staticmethod
    def _insert_user(db, username, display_name, role, password_hash):
        cur = db.execute(
            "INSERT INTO users (username, display_name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, display_name, role, password_hash, now_iso()),
        )
        return _user(db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())

    def list_users(self):
        with self.tx() as db:
            return [_user(r) for r in db.execute("SELECT * FROM users ORDER BY id")]

    def get_user(self, user_id):
        with self.tx() as db:
            return _user(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def credentials(self, username):
        """(user, password_hash) for a login attempt, or (None, None)."""
        with self.tx() as db:
            row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return (_user(row), row["password_hash"]) if row else (None, None)

    def password_hash(self, user_id):
        with self.tx() as db:
            row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        return row and row[0]

    def update_user(self, user_id, changes):
        """Apply {display_name, role, password_hash, disabled}; refuses to drop the last enabled admin."""
        with self.tx(immediate=True) as db:
            row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                return None
            losing_admin = row["role"] == "admin" and not row["disabled"] and (
                changes.get("role", "admin") != "admin" or changes.get("disabled", False)
            )
            if losing_admin:
                self._check_other_admin(db, user_id)
            for column in ("display_name", "role", "password_hash", "disabled"):
                if column in changes:
                    value = int(changes[column]) if column == "disabled" else changes[column]
                    db.execute(f"UPDATE users SET {column} = ? WHERE id = ?", (value, user_id))
            return _user(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def delete_user(self, user_id):
        with self.tx(immediate=True) as db:
            row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                return False
            if row["role"] == "admin" and not row["disabled"]:
                self._check_other_admin(db, user_id)
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True

    @staticmethod
    def _check_other_admin(db, user_id):
        others = db.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND disabled = 0 AND id != ?", (user_id,)
        ).fetchone()[0]
        if not others:
            raise Conflict("Can't remove, disable or demote the last enabled admin")

    def mark_login(self, user_id):
        with self.tx() as db:
            db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_iso(), user_id))

    # --- Sessions (only the sha256 of the cookie value is stored) ---

    def create_session(self, token_hash, user_id):
        now = time.time()
        with self.tx() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            db.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token_hash, user_id, now_iso(), now + SESSION_TTL),
            )

    def session_user(self, token_hash):
        """(user, expires_at) for a live session of an enabled user, else (None, None)."""
        with self.tx() as db:
            row = db.execute(
                "SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
                (token_hash,),
            ).fetchone()
        if row is None or row["expires_at"] < time.time() or row["disabled"]:
            return None, None
        return _user(row), row["expires_at"]

    def touch_session(self, token_hash):
        with self.tx() as db:
            expires = time.time() + SESSION_TTL
            db.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?", (expires, token_hash))

    def delete_session(self, token_hash):
        with self.tx() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def delete_sessions(self, user_id, keep=None):
        with self.tx() as db:
            db.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash IS NOT ?", (user_id, keep))

    # --- Playlists ---

    def list_playlists(self):
        with self.tx() as db:
            rows = db.execute(
                """SELECT p.id, p.name, p.updated_at,
                          (SELECT COUNT(*) FROM playlist_items i WHERE i.playlist_id = p.id) AS item_count,
                          (SELECT COALESCE(SUM(duration), 0) FROM playlist_items i WHERE i.playlist_id = p.id)
                              AS total_duration,
                          (SELECT thumbnail FROM playlist_items i WHERE i.playlist_id = p.id
                              AND thumbnail IS NOT NULL ORDER BY position, id LIMIT 1) AS cover
                   FROM playlists p ORDER BY p.name COLLATE NOCASE, p.id"""
            ).fetchall()
        return [dict(r) | {"total_duration": float(r["total_duration"])} for r in rows]

    def get_playlist(self, playlist_id, db=None):
        if db is None:
            with self.tx() as db:
                return self.get_playlist(playlist_id, db)
        row = db.execute("SELECT id, name, updated_at FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        if row is None:
            return None
        items = db.execute(
            f"SELECT {ITEM_COLUMNS} FROM playlist_items WHERE playlist_id = ? ORDER BY position, id", (playlist_id,)
        ).fetchall()
        return dict(row) | {"items": [dict(i) for i in items]}

    def create_playlist(self, name):
        now = now_iso()
        with self.tx() as db:
            cur = db.execute("INSERT INTO playlists (name, created_at, updated_at) VALUES (?, ?, ?)", (name, now, now))
            return self.get_playlist(cur.lastrowid, db)

    def rename_playlist(self, playlist_id, name):
        with self.tx() as db:
            db.execute("UPDATE playlists SET name = ?, updated_at = ? WHERE id = ?", (name, now_iso(), playlist_id))
            return self.get_playlist(playlist_id, db)

    def delete_playlist(self, playlist_id):
        with self.tx() as db:
            return db.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,)).rowcount > 0

    def add_item(self, playlist_id, item, max_items):
        with self.tx(immediate=True) as db:
            if not db.execute("SELECT 1 FROM playlists WHERE id = ?", (playlist_id,)).fetchone():
                return None
            count, last = db.execute(
                "SELECT COUNT(*), COALESCE(MAX(position), -1) FROM playlist_items WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()
            if count >= max_items:
                raise Conflict(f"A playlist holds at most {max_items} items")
            cur = db.execute(
                "INSERT INTO playlist_items (playlist_id, position, kind, title, source, duration, thumbnail, lang)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (playlist_id, last + 1, item["kind"], item["title"], item["source"], item.get("duration"),
                 item.get("thumbnail"), item.get("lang")),
            )
            db.execute("UPDATE playlists SET updated_at = ? WHERE id = ?", (now_iso(), playlist_id))
            return dict(db.execute(f"SELECT {ITEM_COLUMNS} FROM playlist_items WHERE id = ?", (cur.lastrowid,))
                        .fetchone())

    def delete_item(self, playlist_id, item_id):
        with self.tx() as db:
            gone = db.execute(
                "DELETE FROM playlist_items WHERE id = ? AND playlist_id = ?", (item_id, playlist_id)
            ).rowcount
            if gone:
                db.execute("UPDATE playlists SET updated_at = ? WHERE id = ?", (now_iso(), playlist_id))
            return gone > 0

    def reorder(self, playlist_id, item_ids):
        """Set the order; item_ids must be exactly the playlist's current ids."""
        with self.tx(immediate=True) as db:
            if not db.execute("SELECT 1 FROM playlists WHERE id = ?", (playlist_id,)).fetchone():
                return None
            current = [r[0] for r in db.execute("SELECT id FROM playlist_items WHERE playlist_id = ?", (playlist_id,))]
            if len(item_ids) != len(current) or set(item_ids) != set(current):
                raise Conflict("item_ids must list exactly the playlist's current items")
            db.executemany(
                "UPDATE playlist_items SET position = ? WHERE id = ?", [(pos, i) for pos, i in enumerate(item_ids)]
            )
            db.execute("UPDATE playlists SET updated_at = ? WHERE id = ?", (now_iso(), playlist_id))
            return self.get_playlist(playlist_id, db)

    # --- Quick phrases ---

    def list_phrases(self):
        with self.tx() as db:
            rows = db.execute(
                "SELECT p.id, p.text, p.lang, u.display_name AS created_by"
                " FROM phrases p LEFT JOIN users u ON u.id = p.created_by ORDER BY p.id"
            ).fetchall()
        return [dict(r) for r in rows]

    def add_phrase(self, text, lang, user_id):
        with self.tx() as db:
            cur = db.execute(
                "INSERT INTO phrases (text, lang, created_by, created_at) VALUES (?, ?, ?, ?)",
                (text, lang, user_id, now_iso()),
            )
            row = db.execute(
                "SELECT p.id, p.text, p.lang, u.display_name AS created_by"
                " FROM phrases p LEFT JOIN users u ON u.id = p.created_by WHERE p.id = ?",
                (cur.lastrowid,),
            ).fetchone()
        return dict(row)

    def delete_phrase(self, phrase_id):
        with self.tx() as db:
            return db.execute("DELETE FROM phrases WHERE id = ?", (phrase_id,)).rowcount > 0

    # --- Activity ---

    def log(self, actor, action, detail=None, coalesce=0):
        """Record an event. With coalesce=N, a repeat within N seconds updates the previous row's detail."""
        now = time.time()
        with self._coalesce_lock, self.tx() as db:
            if coalesce:
                last = self._coalesce.get((actor, action))
                if last and now - last[1] < coalesce:
                    updated = db.execute("UPDATE activity SET detail = ? WHERE id = ?", (detail, last[0])).rowcount
                    if updated:
                        return
            cur = db.execute(
                "INSERT INTO activity (at, actor, action, detail) VALUES (?, ?, ?, ?)",
                (now_iso(), actor, action, detail),
            )
            if coalesce:
                self._coalesce[(actor, action)] = (cur.lastrowid, now)
            db.execute(
                "DELETE FROM activity WHERE id <= (SELECT id FROM activity ORDER BY id DESC LIMIT 1 OFFSET ?)",
                (ACTIVITY_KEEP,),
            )

    def activity(self, limit=50, before_id=None):
        with self.tx() as db:
            rows = db.execute(
                "SELECT id, at, actor, action, detail FROM activity WHERE id < ? ORDER BY id DESC LIMIT ?",
                (before_id if before_id is not None else 2**62, limit),
            ).fetchall()
        return [dict(r) for r in rows]
