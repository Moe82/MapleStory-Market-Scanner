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
    player_name,
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
                message_observed_at,
                player_name
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                message_id,
                raw_text,
                name,
                Jsonb(extra_info),
                status,
                observed_at,
                player_name,
            )
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
                    status = %s,
                    message_resolved_at = CASE WHEN %s = 'RESOLVED' THEN NOW() ELSE NULL END
                WHERE id = %s
                """,
                (resolved_item_name, resolved_item_id, status, status, listing_id),
            )


def update_listing_status(listing_id: int, status: str) -> None:
    """Update an item listing's status and clear resolution data."""

    if status not in ("UNRESOLVED", "REVIEW", "FAILED"):
        raise ValueError(f"Invalid status: {status}")

    with psycopg.connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE item_listings
                SET status = %s,
                    resolved_item_name = NULL,
                    resolved_item_id = NULL,
                    message_resolved_at = NULL
                WHERE id = %s
                """,
                (status, listing_id),
            )

def has_matching_listing(analyzed_item_name: str, price: int | None, player_name: str, observed_at: datetime) -> int | None:
    """Return the chat message ID of a matching listing observed in the preceding 15 minutes."""

    with psycopg.connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT message_id
                FROM item_listings
                WHERE analyzed_item_name = %s
                  AND (extra_info->>'price')::BIGINT IS NOT DISTINCT FROM %s::BIGINT
                  AND player_name = %s
                  AND message_observed_at BETWEEN %s::TIMESTAMPTZ - INTERVAL '15 minutes' AND %s::TIMESTAMPTZ
                ORDER BY message_observed_at DESC
                LIMIT 1
                """,
                (analyzed_item_name, price, player_name, observed_at, observed_at),
            )

            result = cursor.fetchone()
            return result[0] if result else None