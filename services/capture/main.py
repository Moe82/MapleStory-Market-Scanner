
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from stream_discovery import discover_streams
from analyzer import analyze_stream
from shared.logging import logger




INTERVAL = int(os.getenv("CAPTURE_INTERVAL", "5"))
SCREENSHOTS_DIR = Path("/app/screenshots")

PENDING_EXTRACTION_DIR = SCREENSHOTS_DIR / "pending_extraction"
ORIGINAL_SCREENSHOT_DIR = SCREENSHOTS_DIR / "original"
PROCESSED_SCREENSHOT_DIR = SCREENSHOTS_DIR / "processed"
NO_TEXT_DETECTED_SCREENSHOT_DIR = SCREENSHOTS_DIR / "no_text_detected"

RETRY_DELAY = 15

# an array of 4 values (left, top, right,bottm) defining the chat region
# We pass these values to openCV to restrict the area it searches which
# greatly improves results. 
# TODO: optimize region values
CHAT_MESSAGE_REGION = tuple(
    float(n.strip())
    for n in os.getenv("CHAT_ROI", "0,0.45,1,1").split(",")
)



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


def find_bands(frame):
    """Detects colored maplestory megaphone messages returns coordinates"""
    MEGAPHONE_COLORS = {
        "pink": {
            "hex": "#DBA6BB",
            "hsv_lower": (160, 35, 185),
            "hsv_upper": (175, 90, 240),
        },
        "cyan": {
            "hex": "#5CDBC6",
            "hsv_lower": (78, 100, 170),
            "hsv_upper": (92, 190, 245),
        },
        "yellow": {
            "hex": "#E4B203",
            "hsv_lower": (18, 200, 170),
            "hsv_upper": (28, 255, 255),
        },
        "blue": {
            "hex": "#98ACB5",
            "hsv_lower": (92, 20, 145),
            "hsv_upper": (110, 70, 210),
        },
    }


    height, width = frame.shape[:2]

    x1, y1, x2, y2 = (
        int(CHAT_MESSAGE_REGION[0] * width),
        int(CHAT_MESSAGE_REGION[1] * height),
        int(CHAT_MESSAGE_REGION[2] * width),
        int(CHAT_MESSAGE_REGION[3] * height),
    )

    region = frame[y1:y2, x1:x2]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    found = []

    for name, spec in MEGAPHONE_COLORS.items():
        mask = cv2.inRange(
            hsv,
            np.array(spec["hsv_lower"], dtype=np.uint8),
            np.array(spec["hsv_upper"], dtype=np.uint8),
        )

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(
                cv2.MORPH_RECT, (23, 3)
            ),
        )

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(
                cv2.MORPH_RECT, (21, 3)
            ),
        )

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        for contour in contours:
            rx, ry, rw, rh = cv2.boundingRect(contour)

            if rw < max(160, int(width * 0.15)) or rh < 10:
                continue

            fraction = (
                cv2.countNonZero(
                    mask[ry:ry + rh, rx:rx + rw]
                )
                / (rw * rh)
            )

            if fraction < 0.55:
                continue

            padding_x = 4
            padding_y = 3

            left = max(0, x1 + rx - padding_x)
            top = max(0, y1 + ry - padding_y)
            right = min(width, x1 + rx + rw + padding_x)
            bottom = min(height, y1 + ry + rh + padding_y)

            found.append(
                (name, (left, top, right, bottom))
            )

    return sorted(
        found,
        key=lambda entry: (
            entry[1][1],
            entry[1][0],
        ),
    )



def process_frame(path):
    """
    Reads a screenshot, saves the original, and detects and saves individual messages
    as cropped images awaiting text extraction.
    """
    frame = cv2.imread(str(path))

    if frame is None:
        logger.warning(f"Unable to decode {path.name}")
        return

    
    ORIGINAL_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    original_path = ORIGINAL_SCREENSHOT_DIR / path.name

    if not cv2.imwrite(str(original_path), frame):
        raise RuntimeError(f"Failed to save original: {original_path}")

    # Detect and save cropped megaphone messages.
    bands = find_bands(frame)
    stem = path.stem

    for index, (name, (left, top, right, bottom)) in enumerate(bands):
        destination = (
            PENDING_EXTRACTION_DIR / f"{stem}_{index:02d}_{name}.png"
        )

        crop = frame[top:bottom, left:right]

        if not cv2.imwrite(str(destination), crop):
            logger.error(f"Failed to save crop: {destination.name}")

    logger.info(
        f"{path.name}: saved original + "
        f"{len(bands)} colored band(s)"
    )


def scan_frames(frame_folder):
    for path in sorted(frame_folder.glob("*.png")):
        try:
            process_frame(path)
        except Exception as error:
            logger.error(f"Processing {path.name} failed: {error}")
        finally:
            path.unlink(missing_ok=True)


def capture(frame_folder, stream_mananger):
    channel = stream_mananger.current_channel
    url = f"https://www.twitch.tv/{channel}"

    # use current time to create unique id
    current_time = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")

    filename = str(frame_folder
        / f"{channel}_{current_time}_%Y%m%d_%H%M%S.png"
    )

    streamlink_cmd = [
        "streamlink",
        "--loglevel",
        "warning",
        "--stdout",
        url,
        "best",
    ]

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        f"fps=1/{INTERVAL}",
        "-fps_mode",
        "vfr",
        "-c:v",
        "png",
        "-f",
        "image2",
        "-strftime",
        "1",
        "-atomic_writing",
        "1",
        filename,
    ]

    logger.info(f"Connecting to {url}")

    streamlink_errors = tempfile.TemporaryFile(mode="w+t")
    streamlink = subprocess.Popen(streamlink_cmd,stdout=subprocess.PIPE,stderr=streamlink_errors,)

    ffmpeg = None

    try:
        # converts livestream video into a PNG screenshot every INTERVAL seconds
        ffmpeg = subprocess.Popen(
            ffmpeg_cmd,
            stdin=streamlink.stdout,
        )

        streamlink.stdout.close()

        active_processes.extend((streamlink, ffmpeg))

        while not stop_event.wait(0.5):
            scan_frames(frame_folder)

            if stream_mananger.current_channel != channel:
                logger.info("Channel changed, restarting capture.")
                break

            if streamlink.poll() is not None or ffmpeg.poll() is not None:
                break

    finally:
        for process in (ffmpeg, streamlink):
            if process is not None and process.poll() is None:
                process.terminate()

        for process in (ffmpeg, streamlink):
            if process is not None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        active_processes.clear()
        scan_frames(frame_folder)
    streamlink_errors.seek(0)
    offline = "No playable streams found" in streamlink_errors.read()
    if offline:
        logger.info(f"Stream OFFLINE: {channel}")
    streamlink_errors.close()
    logger.info("Capture session ended")
    return channel if offline else None




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
                if time.time() - self.last_channels_refreash >= 10800:
                    self.refresh_channel_list()

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
                offline_channel = capture(frame_folder, stream_manager)
                if (offline_channel and 
                    stream_manager.current_channel == offline_channel and 
                    len(stream_manager.channels) > 1):
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