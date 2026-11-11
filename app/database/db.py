
from pathlib import Path

import aiosqlite


class Database:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    async def initialize(self) -> None:
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_username
                ON users(username)
            """)

            await db.commit()

    async def save_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                INSERT INTO users (
                    telegram_id,
                    username,
                    first_name
                )
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id)
                DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (telegram_id, username, first_name),
            )

            await db.commit()

    async def get_user_count(self) -> int:
        async with aiosqlite.connect(self.database_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM users"
            ) as cursor:
                result = await cursor.fetchone()

        return int(result[0]) if result else 0
