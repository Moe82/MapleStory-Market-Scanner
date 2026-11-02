
import os
import cv2
from pathlib import Path
from typing import Literal

from google.genai import types
from pydantic import BaseModel

from shared.prompts import STREAM_VALIDATION_PROMPT, CHAT_BOX_PROMPT
from shared.logging import logger
from shared.gemini import generate_json


MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


class Result(BaseModel):
    status: Literal["good", "bad", "ad"]
    reason: str
    usernames_readable: bool


class ChatBoxResult(BaseModel):
    box_2d: list[int]


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


def get_chat_box_coords(image_path: str) -> tuple[int, int, int, int] | None:
    logger.info(f"Locating chat box in screenshot: {image_path}")
    path = Path(image_path)

    frame = cv2.imread(str(path))
    if frame is None:
        raise ValueError(f"Unable to decode screenshot: {path}")

    height, width = frame.shape[:2]

    result = generate_json(
        model=MODEL,
        contents=[
            CHAT_BOX_PROMPT,
            types.Part.from_bytes(
                data=path.read_bytes(),
                mime_type="image/png",
            ),
        ],
        response_model=ChatBoxResult,
    )

    if not result.box_2d:
        logger.warning("Chat box not detected")
        return None

    if len(result.box_2d) != 4:
        raise ValueError(f"Invalid bounding box: {result.box_2d}")

    ymin, xmin, ymax, xmax = result.box_2d

    if not (0 <= xmin < xmax <= 1000 and 0 <= ymin < ymax <= 1000):
        raise ValueError(f"Invalid bounding box: {result.box_2d}")

    coordinates = (
        round(xmin * width / 1000),
        round(ymin * height / 1000),
        round(xmax * width / 1000),
        round(ymax * height / 1000),
    )

    logger.info(f"Chat box coordinates: {coordinates}")

    return coordinates
