
import os
import cv2
from datetime import datetime, timezone
import numpy as np
from pathlib import Path
import tempfile

from shared.logging import logger

# an array of 4 values (left, top, right,bottm) defining the chat region
# We pass these values to openCV to restrict the area it searches which
# greatly improves results. 
# TODO: optimize region values
CHAT_MESSAGE_REGION = tuple(
    float(n.strip())
    for n in os.getenv("CHAT_ROI", "0,0.45,1,1").split(",")
)

INTERVAL = int(os.getenv("CAPTURE_INTERVAL", "5"))
SCREENSHOTS_DIR = Path("/app/screenshots")
PENDING_EXTRACTION_DIR = SCREENSHOTS_DIR / "pending_extraction"
ORIGINAL_SCREENSHOT_DIR = SCREENSHOTS_DIR / "original"
PROCESSED_SCREENSHOT_DIR = SCREENSHOTS_DIR / "processed"
NO_TEXT_DETECTED_SCREENSHOT_DIR = SCREENSHOTS_DIR / "no_text_detected"


def find_chat_button(frame, bands):
    """Locate the blue chat tab below the megaphone messages.

    Returns (x, y, width, height) in full-screen coordinates, or None.
    A candidate must be a blue rectangle immediately beneath the chat area.
    """
    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    mask = cv2.inRange(
        hsv,
        np.array([95, 65, 45], dtype=np.uint8),
        np.array([115, 220, 210], dtype=np.uint8),
    )
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (11, 5)),
    )

    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    candidates = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        if w < max(25, int(width * 0.018)) or h < max(8, int(height * 0.008)):
            continue
        if not 2.5 <= w / h <= 7:
            continue

        coverage = cv2.countNonZero(mask[y:y + h, x:x + w]) / (w * h)
        if coverage < 0.55:
            continue

        # Check that a real megaphone band sits above and near this button.
        distances = []
        for _, (band_left, _, _, band_bottom) in bands:
            vertical_gap = y - band_bottom
            horizontal_gap = band_left - x

            if (0 <= vertical_gap <= max(8 * h, int(height * 0.15))
                    and -0.5 * w <= horizontal_gap <= 1.5 * w):
                distances.append(
                    vertical_gap / max(h, 1)
                    + abs(horizontal_gap - 0.3 * w) / max(w, 1)
                )

        if distances:
            candidates.append((min(distances) - coverage, (x, y, w, h)))

    return min(candidates, default=(None, None))[1]


def find_chat_left(frame, button, bands, colors):
    """Find the actual colored-message left edge close to the chat button.

    Unlike fixed padding, this checks where each message background begins.
    The button only narrows the search; its own left edge isn't used as the crop.
    """
    if button is None:
        return None

    button_x, button_y, button_w, button_h = button
    scan_left = max(0, button_x - int(button_w * 0.1))
    scan_right = min(frame.shape[1], button_x + button_w)

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    edges = []

    for name, (_, top, right, bottom) in bands:
        # Exclude colored UI below the chat tab and unrelated regions.
        if top >= button_y or bottom > button_y + button_h or right <= scan_left:
            continue

        spec = colors[name]
        mask = cv2.inRange(
            hsv[top:bottom, scan_left:scan_right],
            np.array(spec["hsv_lower"], dtype=np.uint8),
            np.array(spec["hsv_upper"], dtype=np.uint8),
        )

        # A continuous vertical colored edge should be visible across much
        # of the message height, even when its username obscures other pixels.
        coverage = np.mean(mask > 0, axis=0)
        for col in range(len(coverage) - 3):
            if coverage[col] >= 0.65 and coverage[col:col + 3].mean() >= 0.4:
                edges.append(scan_left + col)
                break

    return int(round(float(np.median(edges)))) if edges else None


def find_bands(frame):
    """Detect colored megaphone bands and return their crop coordinates."""
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
    detected = []

    for name, spec in MEGAPHONE_COLORS.items():
        mask = cv2.inRange(
            hsv,
            np.array(spec["hsv_lower"], dtype=np.uint8),
            np.array(spec["hsv_upper"], dtype=np.uint8),
        )

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (23, 3)),
        )

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (21, 3)),
        )

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in contours:
            rx, ry, rw, rh = cv2.boundingRect(contour)

            if rw < max(160, int(width * 0.15)) or rh < 10:
                continue

            fraction = cv2.countNonZero(
                mask[ry:ry + rh, rx:rx + rw]
            ) / (rw * rh)

            if fraction < 0.55:
                continue

            padding_x = 4
            padding_y = 1

            detected.append((name, (
                x1 + rx,
                max(0, y1 + ry - padding_y),
                min(width, x1 + rx + rw + padding_x),
                min(height, y1 + ry + rh + padding_y),
            )))

    button = find_chat_button(frame, detected)
    chat_left = find_chat_left(frame, button, detected, MEGAPHONE_COLORS)

    found = []
    for name, (band_left, top, right, bottom) in detected:
        if button is not None and top >= button[1]:
            continue  # the chat toolbar isn't a megaphone message

        padding_left = 100  # fallback if the chat button/edge isn't detected
        left = max(0, chat_left - 3) if chat_left is not None else max(0, band_left - padding_left)

        if left < right:
            found.append((name, (left, top, right, bottom)))

    return sorted(found, key=lambda entry: (entry[1][1], entry[1][0]))


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


def capture(frame_folder, stream_mananger, subprocess, active_processes, stop_event):
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
