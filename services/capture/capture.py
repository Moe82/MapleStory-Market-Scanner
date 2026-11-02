import os
import cv2
from datetime import datetime, timezone
import numpy as np
import time
from pathlib import Path
import tempfile

from shared.logging import logger

INTERVAL = int(os.getenv("CAPTURE_INTERVAL", "5"))
APP_ENV = os.getenv("APP_ENV", "dev")

SCREENSHOTS_DIR = Path("/app/screenshots")
PENDING_EXTRACTION_DIR = SCREENSHOTS_DIR / "pending_extraction"
ORIGINAL_SCREENSHOT_DIR = SCREENSHOTS_DIR / "original"
PROCESSED_SCREENSHOT_DIR = SCREENSHOTS_DIR / "processed"
NO_TEXT_DETECTED_SCREENSHOT_DIR = SCREENSHOTS_DIR / "no_text_detected"


def find_bands(frame):
    """Detects colored bands and returns their coordinates."""

    detected = []

    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # In-game 'megaphone' messages are avaiable in 4 colors 
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

    for name, spec in MEGAPHONE_COLORS.items():
        # filter out colors outside the hsv lower and upper range.
        # Matching colors are turned white, nonmatching 
        # colors are turned into black
        mask = cv2.inRange(
            hsv,
            np.array(spec["hsv_lower"], dtype=np.uint8),
            np.array(spec["hsv_upper"], dtype=np.uint8),
        )

        # The text within a megaphone msg creates dark spots in the mask 
        # since the color of the texts is not a match. These dark spots
        # are filled in using morphological closing, which fills small gaps 
        # between nearby white pixels.
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (23, 3)),
        )

        # Use morphological opening to remove small white artifacts
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (21, 3)),
        )

        # The resulting mask should now contain only solid white regions.
        # Each region represents a single line in a message

        # Get the countours of these solid white regions
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in contours:
            rx, ry, rw, rh = cv2.boundingRect(contour)

            # Skip regions that are too short to be a megaphone msg
            if rh < 10:
                continue

            white_region = mask[ry:ry + rh, rx:rx + rw]
            total_area = rw * rh
            fraction = cv2.countNonZero(white_region) / total_area

            # reject if the rectangle has less then 55% matching area
            if fraction < 0.55:
                continue

            padding_y = 1

            detected.append((name, (
                0,
                max(0, ry - padding_y),
                width,
                min(height, ry + rh + padding_y),
            )))

    return sorted(detected, key=lambda entry: (entry[1][1], entry[1][0]))




def crop_has_valid_colors(image):
    MIN_LOCAL_COVERAGE = 0.08

    COLORS = {
        "pink": ((160, 35, 185), (175, 90, 240)),
        "cyan": ((78, 100, 170), (92, 190, 245)),
        "yellow": ((18, 200, 170), (28, 255, 255)),
        "blue": ((92, 20, 145), (110, 70, 210)),
    }

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # igore dark padding around a message
    bright = hsv[:, :, 2] >= 115
    ys, xs = np.where(bright)

    if len(ys) == 0:
        return False

    region = hsv[
        ys.min():ys.max() + 1,
        xs.min():xs.max() + 1
    ]

    # identify the dominiate megaphone type
    masks = {}

    for name, (lower, upper) in COLORS.items():
        masks[name] = cv2.inRange(
            region,
            np.array(lower, dtype=np.uint8),
            np.array(upper, dtype=np.uint8),
        )

    color = max(masks, key=lambda name: cv2.countNonZero(masks[name]))
    background_mask = (masks[color] > 0).astype(np.float32)

    height, width = background_mask.shape

    if height < 10 or width < 40:
        return False


    # define sliding window height and width

    window_width = min(width, max(40, round(width * 0.08)))
    window_height = min(height, max(10, round(height * 0.25)))

    # Calculate the fraction of pixels matching the dominant background color
    # within each sliding window. The result ranges from 0.0 to 1.0
    local_coverage = cv2.boxFilter(
        background_mask,
        -1,
        (window_width, window_height),
        normalize=True,
    )

    # Exclude window centers near image boundaries to avoid evaluating
    # windows that extend outside the image
    x_margin = window_width // 2
    y_margin = window_height // 2

    coverage = local_coverage[
        y_margin:height - y_margin,
        x_margin:width - x_margin,
    ]

    if coverage.size == 0:
        return False

    return float(coverage.min()) >= MIN_LOCAL_COVERAGE

def save_original_screenshot(path: str):
    frame = cv2.imread(str(path))
    if frame is None:
        logger.warning(f"Unable to decode {path.name}")
        return
    ORIGINAL_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    original_path = ORIGINAL_SCREENSHOT_DIR / path.name

    if not cv2.imwrite(str(original_path), frame):
        raise RuntimeError(f"Failed to save original: {original_path}")
    os.utime(original_path, (path.stat().st_mtime, path.stat().st_mtime))

def trim_crop(crop, color):
    """trims the upper and lower portions of crop """

    colors = {
        "pink": ((160, 35, 185), (175, 90, 240)),
        "cyan": ((78, 100, 170), (92, 190, 245)),
        "yellow": ((18, 200, 170), (28, 255, 255)),
        "blue": ((92, 20, 145), (110, 70, 210)),
    }

    lower, upper = colors[color]

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array(lower, dtype=np.uint8),
        np.array(upper, dtype=np.uint8),
    )

    # Find rows predominantly containing the message background
    row_coverage = (mask > 0).mean(axis=1)
    rows = np.flatnonzero(row_coverage >= 0.35)

    if len(rows) == 0:
        return None

    # Select the longest continuous group 
    groups = np.split(rows, np.where(np.diff(rows) > 1)[0] + 1)
    longest = max(groups, key=len)

    padding = 1
    top = max(0, int(longest[0]) - padding)
    bottom = min(crop.shape[0], int(longest[-1]) + 1 + padding)

    return crop[top:bottom]


def process_frame(path, chat_box_coords):
    """
    Reads a screenshot and detects and saves individual messages
    as cropped images awaiting text extraction (handled by the processor service)
    """
    frame = cv2.imread(str(path))

    if frame is None:
        logger.warning(f"Unable to decode {path.name}")
        return

    left, top, right, bottom = chat_box_coords
    frame = frame[top:bottom, left:right]


    # Detect and save cropped megaphone messages.
    bands = find_bands(frame)
    stem = path.stem # file name without extension

    for index, (name, (left, top, right, bottom)) in enumerate(bands):
        destination = (
            PENDING_EXTRACTION_DIR / f"{stem}_{index:02d}_{name}.png"
        )

        crop = frame[top:bottom, left:right]

        if not crop_has_valid_colors(crop):
            # try trimming the crop
            trimmed_crop = trim_crop(crop, name)

            # reject if trimming failed
            if trimmed_crop is None or trimmed_crop.size == 0:
                if APP_ENV == "dev":
                    cv2.imwrite(str(failed_destination), crop)
                continue

            crop = trimmed_crop

            # check again
            if not crop_has_valid_colors(crop):
                continue

        if not cv2.imwrite(str(destination), crop):
            logger.error(f"Failed to save crop: {destination.name}")
            continue
    logger.info(
        f"{path.name}: saved "
        f"{len(bands)} colored band(s)"
    )
    return len(bands)

def scan_frames(frame_folder, stream_mananger, channel, session_prefix):
    for path in sorted(frame_folder.glob("*.png")):
        try:
            save_original_screenshot(path)
            if (
                path.name.startswith(session_prefix)
                and stream_mananger.current_channel == channel
                and stream_mananger.current_channel_is_valid
                and stream_mananger.current_channel_chat_box_coords is not None
            ):
                process_frame(path, stream_mananger.current_channel_chat_box_coords)
        except Exception as error:
            logger.error(f"Processing {path.name} failed: {error}")
        finally:
            path.unlink(missing_ok=True)

def capture(frame_folder, stream_mananger, subprocess, active_processes, stop_event):
    channel = stream_mananger.current_channel
    url = f"https://www.twitch.tv/{channel}"

    # use current time to create unique id
    current_time = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    session_prefix = f"{channel}_{current_time}_"

    filename = str(frame_folder
        / f"{channel}_{current_time}_%Y%m%d_%H%M%S.png"
    )

    streamlink_cmd = ["streamlink","--loglevel","warning","--stdout",url,"best",]

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
            scan_frames(frame_folder, stream_mananger, channel, session_prefix)

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
        scan_frames(frame_folder, stream_mananger, channel, session_prefix)
    streamlink_errors.seek(0)
    offline = "No playable streams found" in streamlink_errors.read()
    if offline:
        logger.info(f"Stream OFFLINE: {channel}")
    streamlink_errors.close()
    logger.info("Capture session ended")
    return channel if offline else None
