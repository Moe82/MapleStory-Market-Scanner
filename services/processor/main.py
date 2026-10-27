
import time
import os
import shutil
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


class MessageQueue:
    def __init__(self):
        self.queue = []
        self.window = 60  # 60 seconds
        self.similarity_threshold = 0.90  # TODO: needs testing

    def expire(self):
        now = datetime.now(timezone.utc)
        self.queue = [
            message
            for message in self.queue
            if (now - message["observed_at"]).total_seconds() < self.window
        ]

    def add(self, message):
        self.expire()



        for msg in self.queue:
            similarity = SequenceMatcher(None, message["raw_text"], msg["raw_text"]).ratio()

            if similarity >= self.similarity_threshold:
                return False

        self.queue.append({
            "observed_at": datetime.now(timezone.utc),
            "raw_text": message["raw_text"],
        })
        return True



def main():
    logger.info("MapleStory Processer running\n")

    PROCESSED_DIR.mkdir(exist_ok=True, parents=True)
    FAILED_DIR.mkdir(exist_ok=True, parents=True)

    message_queue = MessageQueue()

    while True:
        for image_path in sorted(
            UNPROCESSED_DIR.glob("*.png"),
            key=lambda path: path.stat().st_mtime,
        ):
            try:
                # Step 1: Extract messages.
                messages = process_screenshot(str(image_path))

                # Step 2: Handle screenshots with no messages.
                if not messages:
                    shutil.move(str(image_path), str(FAILED_DIR / image_path.name))
                    continue

                # Filter duplicate messages.
                unique_messages = []

                for msg in messages:
                    if message_queue.add(msg):
                        unique_messages.append(msg)

                # Step 3: Insert messages into database.
                if unique_messages:
                    insert_messages(unique_messages)

                # Step 4: Archive processed screenshot.
                shutil.move(str(image_path), str(PROCESSED_DIR / image_path.name))
            except Exception as error:
                logger.exception(f"Failed to process {image_path.name}: {error}")
        time.sleep(1)



if __name__ == "__main__":
    main()
