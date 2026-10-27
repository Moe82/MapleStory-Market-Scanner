
"""Extract messages from cropped MapleStory screenshots using PaddleOCR."""

import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from shared.logging import logger
from paddleocr import PaddleOCR
import cv2

ocr = PaddleOCR(
    lang="en",
    ocr_version="PP-OCRv6",
    text_detection_model_name="PP-OCRv6_medium_det",
    text_recognition_model_name="PP-OCRv6_medium_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)

DEBUG_PROCESSOR = os.getenv("DEBUG_PROCESSOR", "false").lower() == "true"

def group_lines(detections: list[dict]) -> list[dict]:
    """Combine text fragments returned from paddleocr into complete visual txt lines"""

    if not detections:
        return []

    typical_height = median(d["height"] for d in detections)
    tolerance = max(4, typical_height * 0.3)

    # sort fragments by position
    def sort_key(d):
        return (d["y"] + d["height"] / 2, d["x"])
    detections.sort(key=sort_key)

    rows = []

    for detection in detections:
        center = detection["y"] + detection["height"] / 2

        # find a row at approximately the same height
        row = next(
            (
                row for row in rows
                if abs(row["center"] - center) <= tolerance
            ),
            None,
        )

        if row is None:
            rows.append({
                "center": center,
                "items": [detection],
            })
        else:
            row["items"].append(detection)

    # Build complete text lines
    lines = []

    for row in sorted(rows, key=lambda r: r["center"]):
        items = sorted(row["items"], key=lambda d: d["x"])

        lines.append({
            "text": " ".join(item["text"] for item in items),
            "x": min(item["x"] for item in items),
        })

    return lines


def split_messages(lines: list[dict]) -> list[str]:
    """Separate messages using horizontal position"""

    if not lines:
        return []

    messages = []
    current = []
    start_x = None

    for line in lines:
        text = line["text"].strip()

        if not text:
            continue

        x = line["x"]

        # If a message is split over two lines, the second lines 
        # starts about 15-30 pixels to the right of first
        is_multi_line = (
            start_x is not None
            and 15 <= x - start_x <= 30
        )

        if current and not is_multi_line:
            messages.append("\n".join(current))
            current = []
            start_x = None

        if start_x is None:
            start_x = x

        current.append(text)

    if current:
        messages.append("\n".join(current))

    return messages


def extract_lines(image_path: str) -> list[dict]:
    """
    Extract text fragments and the coordinates of the box that surounds the text
    """

    detections = []

    for result in ocr.predict(image_path):
        data = result.json["res"]

        for text, box in zip(data["rec_texts"], data["rec_boxes"]):
            if not text.strip():
                continue

            x1, y1, x2, y2 = map(int, box)

            detections.append({
                "text": text.strip(),
                "x": x1,
                "y": y1,
                "height": y2 - y1,
            })

    return detections



def process_screenshot(image_path: str) -> list[dict]:
    """Extract messages and prepare them for database insertion."""

    detections = extract_lines(image_path)
    lines = group_lines(detections)
    messages = split_messages(lines)

    observed_at = datetime.fromtimestamp(
        Path(image_path).stat().st_mtime,
        tz=timezone.utc,
    )

    logger.info(f"Processing: {Path(image_path).name}")

    for index, message in enumerate(messages, start=1):
        logger.info(f"Message {index}: {message!r}")

    return [
        {
            "raw_text": message,
            "observed_at": observed_at,
        }
        for message in messages
    ]
