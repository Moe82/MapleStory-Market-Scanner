
import os
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

from shared.prompts import STREAM_VALIDATION_PROMPT
from shared.logging import logger
from shared.token_usage import log_token_usage


MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


class Result(BaseModel):
    status: Literal["good", "bad", "ad"]
    reason: str


def analyze_stream(image_path: str | Path) -> Literal["good", "bad", "ad"]:
    print(f"Analyzing screenshot at path: {image_path}")
    path = Path(image_path)

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            STREAM_VALIDATION_PROMPT,
            types.Part.from_bytes(
                data=path.read_bytes(),
                mime_type="image/png",
            ),
        ],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=Result,
        ),
    )


    log_token_usage(response.usage_metadata)

    result = response.parsed
    logger.info(f"Result: {result.status}")
    logger.info(f"Reason: {result.reason}")
    return result.status
