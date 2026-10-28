
import os
from pathlib import Path
from typing import Literal

from google.genai import types
from pydantic import BaseModel

from shared.prompts import STREAM_VALIDATION_PROMPT
from shared.logging import logger
from shared.gemini import generate_json


MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


class Result(BaseModel):
    status: Literal["good", "bad", "ad"]
    reason: str
    usernames_readable: bool

def analyze_stream(image_path: str | Path) -> Literal["good", "bad", "ad"]:
    logger.info(f"Analyzing screenshot at path: {image_path}")
    path = Path(image_path)

    result = generate_json(
        model=MODEL,
        contents=[
            STREAM_VALIDATION_PROMPT,
            types.Part.from_bytes(
                data=path.read_bytes(),
                mime_type="image/png",
            ),
        ],
        response_model=Result,
    )

    logger.info(f"Result: {result.status}")
    logger.info(f"Reason: {result.reason}")
    

    if result.status == "good" and not result.usernames_readable:
        logger.warning("Gemini return incorrect status. Updating status to 'bad'")
        result.status = "bad"

    return result.status
