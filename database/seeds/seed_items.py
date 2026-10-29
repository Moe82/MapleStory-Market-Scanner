import os
import sys
import base64
import time
from pathlib import Path

import psycopg
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from database.accessors.items import insert_item, is_item_synced
from shared.logging import logger


REGION = os.getenv("REGION_TO_SEED", "MCW")
VERSION = os.getenv("VERSION_TO_SEED", "1")

API = f"https://maplestory.io/api/{REGION}/{VERSION}/item"
ICON_DIR = ROOT / "data/items/icons" / REGION / VERSION


def main():
    logger.info(f"Running items table seeder. Region:{REGION}, Version:{VERSION}")
    response = requests.get(API, timeout=120)
    response.raise_for_status()
    items = response.json()

    if not isinstance(items, list) or not items:
        raise ValueError("Expected a nonempty list of items from MapleStory.IO")

    ICON_DIR.mkdir(parents=True, exist_ok=True)

    with psycopg.connect() as conn:
        for index, item in enumerate(items, 1):
            item_id = item["id"]

            print(f"\r{index}/{len(items)} ({index / len(items):.1%})", end="", flush=True)

            try:
                # skip items already imported successfully
                if is_item_synced(item_id, REGION, VERSION) and (ICON_DIR / f"{item_id}.png").exists():
                    continue

                response = requests.get(f"{API}/{item_id}", timeout=60)
                response.raise_for_status()
                detail = response.json()

                info = dict(detail.get("metaInfo") or {})
                encoded_icon = info.pop("icon", None)
                info.pop("iconRaw", None)

                for key in (
                    "requiredJobs",
                    "requiredLevel",
                    "requiredGender",
                    "isCash",
                    "equipGroup",
                ):
                    value = detail.get(key, item.get(key))
                    if value is not None:
                        info[key] = value

                icon_path = None

                if encoded_icon:
                    icon_bytes = base64.b64decode(encoded_icon.split(",")[-1])
                else:
                    image_response = requests.get(
                        f"{API}/{item_id}/icon",
                        timeout=60,
                    )
                    icon_bytes = image_response.content if image_response.ok else b""

                if icon_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                    (ICON_DIR / f"{item_id}.png").write_bytes(icon_bytes)
                    icon_path = f"/items/icons/{REGION}/{VERSION}/{item_id}.png"

                description = detail.get("description") or {}
                type_info = detail.get("typeInfo") or item.get("typeInfo") or {}

                name = (
                    description.get("name")
                    if isinstance(description, dict)
                    else None
                )
                name = name or detail.get("name") or item["name"]

                desc = (
                    description.get("description")
                    if isinstance(description, dict)
                    else description
                )
                desc = desc if desc is not None else detail.get(
                    "desc", item.get("desc")
                )

                insert_item(
                    maplestory_id=item_id,
                    name=name,
                    region=REGION,
                    version=VERSION,
                    category=type_info.get("overallCategory"),
                    subcategory=type_info.get("subCategory")
                    or type_info.get("category"),
                    description=desc,
                    icon_path=icon_path,
                    metadata=info,
                )

            except (
                requests.RequestException,
                ValueError,
                KeyError,
                TypeError,
                psycopg.Error,
            ) as error:
                logger.warning(f"Failed item {item_id}: {error}")
            time.sleep(0.1)  # avoid hammering the api


if __name__ == "__main__":
    main()