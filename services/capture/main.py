
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from stream_discovery import discover_streams
from analyzer import analyze_stream
from shared.logging import logger
from capture import capture


INTERVAL = int(os.getenv("CAPTURE_INTERVAL", "5"))
SCREENSHOTS_DIR = Path("/app/screenshots")
PENDING_EXTRACTION_DIR = SCREENSHOTS_DIR / "pending_extraction"
ORIGINAL_SCREENSHOT_DIR = SCREENSHOTS_DIR / "original"
PROCESSED_SCREENSHOT_DIR = SCREENSHOTS_DIR / "processed"
NO_TEXT_DETECTED_SCREENSHOT_DIR = SCREENSHOTS_DIR / "no_text_detected"
RETRY_DELAY = 15

stop_event = threading.Event()
active_processes = []

def stop(signum, frame):
    stop_event.set()

    for process in active_processes:
        if process.poll() is None:
            process.terminate()

# ensure that streamlink and FFmpeg process exit cleanly
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)



class StreamManager:
    def __init__(self, validation_interval=300):
        self.channels = discover_streams()
        self.current_index = 0
        self.validation_interval = int(os.environ["STREAM_VALIDATION_INTERVAL"])
        self.stop_event = threading.Event()
        self.channel_started_at = time.time()
        self.last_analyzed_image = None
        self.missing_screenshots = 0
        self.last_cleanup = 0 # setting to zero so that file cleanup runs once on startup
        self.last_channels_refreash = time.time()

    @property
    def current_channel(self):
        if len(self.channels) == 0:
            return ""
        return self.channels[self.current_index]

    def validate_stream(self):
        logger.info(f"Validating {self.current_channel}")

        image_path = max(
            ORIGINAL_SCREENSHOT_DIR.glob(f"{self.current_channel}_*.png"),
            key=os.path.getmtime,
            default=None
        )

        if image_path is None:
            logger.warning("No screenshots found")
            return None

        if time.time() - os.path.getmtime(image_path) > 90:
            logger.warning("Screenshot is too old")
            return None

        if os.path.getmtime(image_path) < self.channel_started_at:
            logger.warning("Screenshot is from an old session")
            return None

        if image_path == self.last_analyzed_image:
            logger.info("Screenshot already analyzed")
            return None

        result = analyze_stream(image_path)
        self.last_analyzed_image = image_path

        return result

    def next_channel(self):
        if not self.channels:
            logger.warning("No channels available to switch to")
            return

        self.current_index = (self.current_index + 1) % len(self.channels)
        self.channel_started_at = time.time()
        self.last_analyzed_image = None
        logger.info(f"Switching to stream: {self.current_channel}")

    def refresh_channel_list(self):
        new_channels = discover_streams()
        self.last_channels_refreash = time.time()

        if new_channels:
            current_channel = self.current_channel
            self.channels = new_channels

            if current_channel in new_channels:
                self.current_index = new_channels.index(current_channel)
            else:
                self.current_index = 0
                self.channel_started_at = time.time()
                self.last_analyzed_image = None
                self.missing_screenshots = 0
            logger.info(f"Refreshed channels list: {len(self.channels)} total")

    def run(self):
        self.stop_event.wait(60) # give the initial run some time to gather screenshots

        while not self.stop_event.is_set():
            try:
                # delete old files once every hour
                if time.time() - self.last_cleanup >= 3600:
                    cleanup_old_screenshots()
                    self.last_cleanup = time.time()

                # refreash channel list every 3 hours
                if not self.channels or time.time() - self.last_channels_refreash >= 10800:
                    self.refresh_channel_list()

                if not self.channels:
                    logger.warning("No channels available. Retrying in 60 seconds...")
                    self.stop_event.wait(60)
                    continue

                result = self.validate_stream()

                if result == "ad":
                    self.missing_screenshots = 0
                    delay = 60

                elif result == "bad":
                    self.next_channel()
                    self.missing_screenshots = 0
                    delay = 60

                elif result == "good":
                    self.missing_screenshots = 0
                    delay = self.validation_interval

                elif result is None:
                    self.missing_screenshots += 1
                    logger.warning(f"No fresh screenshot ({self.missing_screenshots}/3)")

                    if self.missing_screenshots >= 3:
                        self.next_channel()
                        self.missing_screenshots = 0

                    delay = 60

                else:
                    logger.warning(f"Unexpected result: {result}")
                    delay = 60

            except Exception as error:
                logger.error(f"Validation error: {error}")
                delay = 60

            self.stop_event.wait(delay)

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()


def cleanup_old_screenshots():
    logger.info("Deleting old screenshots.")
    cutoff = time.time() - 86400  # 24 hours
    for folder in [
        ORIGINAL_SCREENSHOT_DIR,
        PENDING_EXTRACTION_DIR,
        PROCESSED_SCREENSHOT_DIR,
        NO_TEXT_DETECTED_SCREENSHOT_DIR,
    ]:
        for file in folder.glob("*.png"):
            if file.stat().st_mtime < cutoff:
                file.unlink()

def create_screenshot_directories():
    # recreating directories as git ignores empty folders
    PENDING_EXTRACTION_DIR.mkdir(parents=True, exist_ok=True)
    ORIGINAL_SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
    NO_TEXT_DETECTED_SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
    PROCESSED_SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)


def main():
    logger.info("Starting Capture Service")
    create_screenshot_directories()

    stream_manager = StreamManager()
    stream_manager.start()

    with tempfile.TemporaryDirectory(prefix="twitch_frames_") as folder:
        frame_folder = Path(folder)
        while not stop_event.is_set():
            try:
                if not stream_manager.channels:
                    stop_event.wait(RETRY_DELAY)
                    continue

                # returns channel name if its offline
                offline_channel = capture(frame_folder, stream_manager, subprocess, active_processes, stop_event)

                if (
                        offline_channel and 
                        stream_manager.current_channel == offline_channel and 
                        len(stream_manager.channels) > 1
                    ):
                        stream_manager.next_channel()
                        stop_event.wait(3)
                        continue
                
            except Exception as error:
                logger.error(f"Capture error: {error}")

            if not stop_event.is_set():
                logger.info(f"Retrying in {RETRY_DELAY}s")
                stop_event.wait(RETRY_DELAY)
    
    stream_manager.stop()
    logger.info("Capture Service Stopped")


if __name__ == "__main__":
    main()
