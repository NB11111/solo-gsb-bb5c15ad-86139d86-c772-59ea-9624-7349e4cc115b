"""SQLite 连接与建表。数据库初始化在应用启动时执行。"""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "data/lab.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL CHECK (kind IN ('raw', 'mix')),
    name       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recipe_items (
    mix_id        INTEGER NOT NULL REFERENCES batches (id),
    ingredient_id INTEGER NOT NULL REFERENCES batches (id),
    portions      INTEGER NOT NULL CHECK (portions > 0),
    PRIMARY KEY (mix_id, ingredient_id)
);
"""


def init_db() -> None:
    """创建数据目录并建表（幂等）。"""
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
