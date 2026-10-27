
"""Database operations for chat messages table"""

from datetime import datetime
from psycopg.rows import dict_row
import psycopg


def insert_message(raw_text: str, observed_at: datetime) -> None:
    """Insert a single chat message"""

    with psycopg.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_messages (raw_text, observed_at)
                VALUES (%s, %s)
                """,
                (raw_text, observed_at),
            )



def insert_messages(messages: list[dict]) -> None:
    """Insert all messages in a single transaction."""

    with psycopg.connect() as connection:
        with connection.cursor() as cursor:
            for message in messages:
                cursor.execute(
                    """
                    INSERT INTO chat_messages (raw_text, observed_at)
                    VALUES (%s, %s)
                    """,
                    (message["raw_text"], message["observed_at"]),
                )


def get_messages(limit: int) -> list[dict]:
    """Returns list of pending messages"""
    with psycopg.connect(row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, raw_text
                FROM chat_messages
                WHERE status = 'PENDING'
                ORDER BY id
                LIMIT %s
                """,
                (limit,),
            )

            return cursor.fetchall()

def get_message(message_id: int, conn: psycopg.Connection, for_update: bool = False,) -> dict | None:
    """Retrieve a message (optionally locking it for an update)."""

    query = """
        SELECT *
        FROM chat_messages
        WHERE id = %s
    """

    if for_update:
        query += " FOR UPDATE"

    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, (message_id,))
        return cursor.fetchone()


def update_message_status(message_id: int, status: str, conn: psycopg.Connection) -> None:
    """Update a chat message's processing status."""

    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE chat_messages
            SET status = %s
            WHERE id = %s
            """,
            (status, message_id),
        )


def delete_all_messages() -> None:
    with psycopg.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                TRUNCATE TABLE chat_messages RESTART IDENTITY CASCADE
                """
            )