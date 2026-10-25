"""Shared logging utility for all services."""

import logging
import os
import sys
import time

SERVICE_NAME = os.getenv("SERVICE_NAME", "maplestory")

logger = logging.getLogger(SERVICE_NAME)
logger.setLevel(logging.INFO)
logger.propagate = False # prevent duplicate logs from being printed by the base logger.

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    logging.Formatter(
        "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
    )
)
handler.formatter.converter = time.gmtime

if not logger.handlers:
    logger.addHandler(handler)







    