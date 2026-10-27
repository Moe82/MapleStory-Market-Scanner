
"""Resolve multiple MapleStory item names using Gemini."""

import json

from google import genai
from google.genai import types
from pydantic import BaseModel
from database.accessors.items import get_item_name
from database.accessors.item_listings import update_listing
from shared.prompts import ITEM_RESOLUTION_PROMPT

MODEL = "gemini-3.1-flash-lite"

client = genai.Client()


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

    response = client.models.generate_content(
        model=MODEL,
        contents=json.dumps(payload),
        config=types.GenerateContentConfig(
            system_instruction=ITEM_RESOLUTION_PROMPT,
            response_mime_type="application/json",
            response_schema=BatchResolutionResult,
            temperature=0,
        ),
    )

    if not response.text:
        raise ValueError("Gemini returned an empty response")


    usage = response.usage_metadata
    
    print(f"Input tokens: {usage.prompt_token_count}")
    print(f"Output tokens: {usage.candidates_token_count}")
    print(f"Total tokens: {usage.total_token_count}")

    
    result = BatchResolutionResult.model_validate_json(response.text)

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
            print(f"Failed item: {original['analyzed_item_name']}")
            print(f"Gemini selected: {resolution.item_id}")

            # strange case were gemini returns an item ID that was not provided o.O
            # query the table and check if this happens to be the right item ID
            # TODO: add validation logic.
            item_name = get_item_name(resolution.item_id)
            if (item_name):
                print(
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

        # NEW: Get the resolved item name from the candidate list.
        resolution.item_name = next(
            (
                candidate["name"]
                for candidate in original["candidates"]
                if candidate["id"] == resolution.item_id
            ),
            None,
        )

    return result
