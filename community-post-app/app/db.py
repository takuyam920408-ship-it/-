"""投稿履歴の SQLite。ネタ被り防止とリサイクル判定に使う。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    image_url     TEXT,
    image_file    TEXT,
    template_id   TEXT,
    template_type TEXT,
    phrase        TEXT,
    text          TEXT NOT NULL,
    work_id       TEXT,
    episode       TEXT,
    status        TEXT NOT NULL DEFAULT 'posted'
);
CREATE INDEX IF NOT EXISTS idx_posts_created  ON posts(created_at);
CREATE INDEX IF NOT EXISTS idx_posts_source   ON posts(source_url);
CREATE INDEX IF NOT EXISTS idx_posts_template ON posts(template_id);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def record_post(**fields) -> int:
    fields.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    fields.setdefault("status", "posted")
    columns = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO posts ({columns}) VALUES ({marks})", tuple(fields.values())
        )
        return cur.lastrowid


def recent_template_ids(limit: int = 8) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT template_id FROM posts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [r["template_id"] for r in rows if r["template_id"]]


def recent_phrases(work_id: str | None, limit: int = 10) -> list[str]:
    with connect() as conn:
        if work_id:
            rows = conn.execute(
                "SELECT phrase FROM posts WHERE work_id = ? ORDER BY id DESC LIMIT ?",
                (work_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT phrase FROM posts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [r["phrase"] for r in rows if r["phrase"]]


def source_used(source_url: str, within_days: int = 90) -> dict | None:
    """同じ元記事を最近使っていないか。ネタ被りの警告に使う。"""
    since = (datetime.now() - timedelta(days=within_days)).isoformat(timespec="seconds")
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM posts WHERE source_url = ? AND created_at >= ?"
            " ORDER BY id DESC LIMIT 1",
            (source_url, since),
        ).fetchone()
    return dict(row) if row else None


def image_used(image_url: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM posts WHERE image_url = ? ORDER BY id DESC LIMIT 1", (image_url,)
        ).fetchone()
    return dict(row) if row else None


def history(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_post(post_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
