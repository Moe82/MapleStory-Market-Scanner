
import json
from typing import Literal

from pydantic import BaseModel, field_validator  # used for data validation

from shared.prompts import LISTING_ANALYSIS_PROMPT
from shared.gemini import generate_json


MODEL = "gemini-3.1-flash-lite"


class ItemListing(BaseModel):
    name: str
    player_name: str | None = None
    price: int | None = None
    quantity: int | None = None
    intent: Literal["BUY", "SELL", "TRADE", "UNKNOWN"]
    attributes: dict[str, int] = {}
    needs_review: bool = False

    @field_validator("attributes", mode="before") # 'mode:before': runs transformation logic (normalize_attributes) prior to type conversion
    @classmethod
    def normalize_attributes(cls, value):
        if not isinstance(value, dict):
            return value

        return {
            key: (
                int(number[:-1])
                if isinstance(number, str)
                and number.endswith("%")
                and number[:-1].strip().isdigit()
                else number
            )
            for key, number in value.items()
        }


class AnalyzedMessage(BaseModel):
    id: int
    cleaned_text: str
    listings: list[ItemListing]
    needs_review: bool = False


class AnalysisResult(BaseModel):
    messages: list[AnalyzedMessage]



def analyze_messages(messages: list[dict]) -> AnalysisResult:
    if not messages:
        return AnalysisResult(messages=[])

    payload = []
    for index, message in enumerate(messages, start=1):
      payload.append({
          "id": index,
          "text": message["raw_text"]
      })

    result = generate_json(
        model=MODEL,
        contents=(
            "Analyze these messages and return JSON matching this structure:\n"
            '{"messages":[{"id":1,"cleaned_text":"...",'
            '"listings":[{"name":"...","price":null,'
            '"quantity":null,"intent":"SELL",'
            '"player_name":"...",'
            '"attributes":{"attack":10},'
            '"needs_review":false}],'
            '"needs_review":false}]}\n\n'
            "Messages:\n"
            + json.dumps(payload, ensure_ascii=False)
        ),
        response_model=AnalysisResult,
        system_instruction=LISTING_ANALYSIS_PROMPT,
        enforce_schema=False,
    )

    expected_ids = set(range(1, len(messages) + 1))
    actual_ids = [message.id for message in result.messages]

    if (
        len(actual_ids) != len(messages)
        or set(actual_ids) != expected_ids
    ):
        raise ValueError(
            "Gemini returned missing or duplicate message IDs"
        )

    return result
