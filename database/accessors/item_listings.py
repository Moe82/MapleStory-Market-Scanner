from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row

def insert_item_listing(
    message_id: int,
    raw_text: str,
    name: str,
    extra_info: dict,
    status: str,
    observed_at: datetime,
    conn: psycopg.Connection,
) -> None:
    """Insert a single item listing"""

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO item_listings (
                message_id,
                raw_text,
                analyzed_item_name,
                extra_info,
                status,
                observed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                message_id,
                raw_text,
                name,
                Jsonb(extra_info),
                status,
                observed_at,
            ),
        )


def get_analyzed_listings(limit: int) -> list[dict]:
    """Returns list of item listings awaiting resolution"""
    with psycopg.connect(row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, analyzed_item_name
                FROM item_listings
                WHERE status = 'ANALYZED'
                ORDER BY id
                LIMIT %s
                """,
                (limit,),
            )

            return cursor.fetchall()


def update_listing(
    listing_id: int,
    resolved_item_name: str | None,
    resolved_item_id: int | None,
    status: str,
) -> None:
    with psycopg.connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE item_listings
                SET resolved_item_name = %s,
                    resolved_item_id = %s,
                    status = %s
                WHERE id = %s
                """,
                (resolved_item_name, resolved_item_id, status, listing_id),
            )


def mark_listing_unresolved(listing_id: int) -> None:
    """Mark an item listing as unresolved."""

    with psycopg.connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE item_listings
                SET status = 'UNRESOLVED',
                    resolved_item_name = NULL,
                    resolved_item_id = NULL
                WHERE id = %s
                """,
                (listing_id,),
            )


def mark_listing_for_review(listing_id: int) -> None:
    """Mark an item listing as unresolved."""

    with psycopg.connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE item_listings
                SET status = 'REVIEW',
                    resolved_item_name = NULL,
                    resolved_item_id = NULL
                WHERE id = %s
                """,
                (listing_id,),
            )