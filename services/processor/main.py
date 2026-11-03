import time
import os
import shutil
import cv2
from collections import deque
import numpy as np
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime, timezone

from screenshot_processor import process_screenshot
from database.accessors.chat_messages import insert_messages, delete_all_messages
from shared.logging import logger

IMAGE_DIR = Path("/app/screenshots")
UNPROCESSED_DIR = IMAGE_DIR / "pending_extraction"
PROCESSED_DIR = IMAGE_DIR / "processed"
FAILED_DIR = IMAGE_DIR / "no_text_detected"
DEBUG_DIR = IMAGE_DIR / "debug"

APP_ENV = os.getenv("APP_ENV", "dev")


class ScreenshotQueue:
    """Detect duplicate screenshots"""
    def __init__(self, window_seconds=60, pixel_threshold=25, max_changed_fraction=0.001):
        self.window_seconds = window_seconds
        self.pixel_threshold = pixel_threshold
        self.max_changed_fraction = max_changed_fraction
        self.queue = deque()

    def expire(self, captured_at):
        while self.queue and captured_at - self.queue[0][0] > self.window_seconds:
            self.queue.popleft()

    def normalize(self, crop):
        return cv2.resize(
            cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY),
            (512, 48),
            interpolation=cv2.INTER_AREA,
        )

    def is_duplicate(self, crop: np.ndarray, captured_at: float) -> bool:
        self.expire(captured_at)

        if crop is None or crop.size == 0:
            return False

        screenshot = self.normalize(crop)

        for _, previous in self.queue:
            changed_fraction = (
                np.count_nonzero(cv2.absdiff(screenshot, previous) > self.pixel_threshold)
                / screenshot.size
            )

            if changed_fraction <= self.max_changed_fraction:
                # Refresh the history for screenshots already processed.
                self.queue.append((captured_at, screenshot))
                return True

        return False

    def add(self, crop: np.ndarray, captured_at: float):
        self.expire(captured_at)
        self.queue.append((captured_at, self.normalize(crop)))


class MessageQueue:
    def __init__(self):
        self.queue = []
        self.window = 60  # 60 seconds
        self.similarity_threshold = 0.90  # TODO: needs testing

    def expire(self, captured_at):
        now = datetime.fromtimestamp(captured_at, timezone.utc)
        self.queue = [
            message
            for message in self.queue
            if (now - message["observed_at"]).total_seconds() < self.window
        ]

    def is_duplicate(self, message, captured_at):
        self.expire(captured_at)

        for msg in self.queue:
            similarity = SequenceMatcher(None, message["raw_text"], msg["raw_text"]).ratio()

            if similarity >= self.similarity_threshold:
                return True

        self.queue.append({
            "observed_at": datetime.fromtimestamp(captured_at, timezone.utc),
            "raw_text": message["raw_text"],
        })
        return False


def main():
    logger.info("MapleStory Processer running\n")

    PROCESSED_DIR.mkdir(exist_ok=True, parents=True)
    FAILED_DIR.mkdir(exist_ok=True, parents=True)

    message_queue = MessageQueue()
    screenshot_queue = ScreenshotQueue()

    while True:
        for image_path in sorted(
            UNPROCESSED_DIR.glob("*.png"),
            key=lambda path: path.stat().st_mtime,
        ):
            try:
                # Step 1: Confirm screenshot is not a duplicate.
                frame = cv2.imread(str(image_path))
                captured_at = image_path.stat().st_mtime

                if frame is None:
                    logger.warning(f"Unable to read cropped image: {image_path.name}")
                    shutil.move(str(image_path), str(FAILED_DIR / image_path.name))
                    continue

                if screenshot_queue.is_duplicate(frame, captured_at):
                    image_path.unlink()
                    continue

                # Step 2: Extract messages.
                messages = process_screenshot(str(image_path))

                # Step 3: Handle screenshots with no messages.
                if not messages:
                    if APP_ENV == "dev":
                        shutil.move(str(image_path), str(FAILED_DIR / image_path.name))
                    continue

                # step 4: Filter out duplicate messages.
                unique_messages = []

                for msg in messages:
                    if not message_queue.is_duplicate(msg, captured_at):
                        msg["screenshot_filename"] = image_path.name
                        unique_messages.append(msg)

                # Step 5: Insert messages into database.
                if unique_messages:
                    insert_messages(unique_messages)

                # Step 6: Record successfully processed screenshot.
                screenshot_queue.add(frame, captured_at)

                # Step 7: Archive processed screenshot
                shutil.move(str(image_path), str(PROCESSED_DIR / image_path.name))
            
            except Exception as error:
                logger.exception(f"Failed to process {image_path.name}: {error}")
        time.sleep(1)


if __name__ == "__main__":
    main()