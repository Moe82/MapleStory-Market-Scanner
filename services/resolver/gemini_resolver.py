
"""Resolve multiple MapleStory item names using Gemini."""

import json

from pydantic import BaseModel

from database.accessors.items import get_item_name
from database.accessors.item_listings import update_listing
from shared.prompts import ITEM_RESOLUTION_PROMPT
from shared.gemini import generate_json
from shared.logging import logger

MODEL = "gemini-3.1-flash-lite"


class ItemResolution(BaseModel):
    id: int
    item_id: int | None
    listing_id: int | None = None
    item_name: str | None = None  # NEW


class BatchResolutionResult(BaseModel):
    resolutions: list[ItemResolution]


def resolve_with_gemini(items: list[dict]) -> BatchResolutionResult:

    if not items:
        return BatchResolutionResult(resolutions=[])

    payload = [
        {
            "id": index,
            "listing_id": item["listing_id"],
            "name": item["analyzed_item_name"],
            "candidates": [
                {
                    "id": candidate["id"],
                    "name": candidate["name"],
                }
                for candidate in item["candidates"]
            ],
        }
        for index, item in enumerate(items, start=1)
    ]

    result = generate_json(
        model=MODEL,
        contents=json.dumps(payload),
        response_model=BatchResolutionResult,
        system_instruction=ITEM_RESOLUTION_PROMPT,
    )

    expected_ids = set(range(1, len(items) + 1))
    returned_ids = [resolution.id for resolution in result.resolutions]

    if (
        len(returned_ids) != len(items)
        or set(returned_ids) != expected_ids
    ):
        raise ValueError("Gemini returned invalid batch IDs")

    # Validate candidate IDs against their corresponding item.
    for resolution in result.resolutions[:]:
        original = items[resolution.id - 1]

        valid_ids = {
            candidate["id"]
            for candidate in original["candidates"]
        }

        if (
            resolution.item_id is not None
            and resolution.item_id not in valid_ids
        ):
            # strange case were gemini returns an item ID that was not provided o.O
            # query the table and check if this happens to be the right item ID
            # TODO: add validation logic.
            logger.warning(f"Failed item: {original['analyzed_item_name']}")
            logger.warning(f"Gemini selected: {resolution.item_id}")
            item_name = get_item_name(resolution.item_id)
            if (item_name):
                logger.warning(
                    f"Candidate mis match: "
                    f"{original['analyzed_item_name']} -> {item_name} "
                    f"(ID: {resolution.item_id})"
                )
                # mark listing for review
                update_listing(original["listing_id"], item_name, resolution.item_id, "REVIEW")
                result.resolutions.remove(resolution)
                continue
            else:
                raise ValueError(
                    f"Gemini returned unknown item ID {resolution.item_id}"
                )


        resolution.listing_id = original["listing_id"]

        resolution.item_name = next(
            (
                candidate["name"]
                for candidate in original["candidates"]
                if candidate["id"] == resolution.item_id
            ),
            None,
        )

    return result
