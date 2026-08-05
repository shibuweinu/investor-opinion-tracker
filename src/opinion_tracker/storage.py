from __future__ import annotations

import sqlite3
from pathlib import Path

from .schemas import NormalizedPost


class Repository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("""CREATE TABLE IF NOT EXISTS posts (
            platform TEXT NOT NULL, platform_post_id TEXT NOT NULL, author_id TEXT NOT NULL,
            published_at TEXT NOT NULL, text TEXT NOT NULL, url TEXT NOT NULL,
            PRIMARY KEY(platform, platform_post_id))""")

    def upsert_posts(self, posts: list[NormalizedPost]) -> None:
        self.connection.executemany(
            "INSERT OR IGNORE INTO posts VALUES (?, ?, ?, ?, ?, ?)",
            [
                (p.platform, p.platform_post_id, p.author_id, p.published_at.isoformat(), p.text, p.url)
                for p in posts
            ],
        )
        self.connection.commit()

    def count_posts(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0])
