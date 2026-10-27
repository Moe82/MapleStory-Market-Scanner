import psycopg
from psycopg.types.json import Jsonb

def get_all_items() -> list[dict]:
    """ Return list of all items in the database """
    with psycopg.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, category, metadata
                    FROM items
                """)
    
                rows = cursor.fetchall()
    
    return [
        {
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "metadata": row[3],
        }
        for row in rows
    ]


def get_item_name(item_id: int) -> str | None:
    """ Fetch item name using its ID"""
    with psycopg.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM items WHERE id = %s",
                (item_id,),
            )

            row = cursor.fetchone()

    return row[0] if row else None


def insert_item(
    maplestory_id: int,
    name: str,
    region: str,
    version: str,
    category: str | None = None,
    subcategory: str | None = None,
    description: str | None = None,
    icon_path: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Insert an item and return its database ID."""
    with psycopg.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO items (
                    maplestory_id,
                    name,
                    category,
                    subcategory,
                    description,
                    icon_path,
                    metadata,
                    region,
                    version,
                    last_synced_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
                """,
                (
                    maplestory_id,
                    name,
                    category,
                    subcategory,
                    description,
                    icon_path,
                    Jsonb(metadata if metadata is not None else {}),
                    region,
                    version,
                ),
            )

            return cursor.fetchone()[0]



def is_item_synced(maplestory_id: int, region: str, version: str) -> bool:
    with psycopg.connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM items
                WHERE maplestory_id = %s
                  AND region = %s
                  AND version = %s
                  AND last_synced_at IS NOT NULL
                """,
                (maplestory_id, region, version),
            )
            return cursor.fetchone() is not None