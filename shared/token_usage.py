import os
import time
from shared.logging import logger

last_log = None
input_tokens = 0
output_tokens = 0
total_tokens = 0

def log_token_usage(usage):
    """Log input, output, and total tokens consumed by Gemini requests."""
    global last_log, input_tokens, output_tokens, total_tokens

    if os.getenv("LOG_TOKEN_USAGE", "true").lower() == "true":
        logger.info("_______________________________________")
        logger.info(f"Input tokens: {usage.prompt_token_count}")
        logger.info(f"Output tokens: {usage.candidates_token_count}")
        logger.info(f"Total tokens: {usage.total_token_count}")
        logger.info("_______________________________________")


    if os.getenv("LOG_TOKEN_USAGE_INTERVAL", "false").lower() == "true":
        now = time.time()

        if last_log is None:
            last_log = now

        input_tokens += usage.prompt_token_count or 0
        output_tokens += usage.candidates_token_count or 0
        total_tokens += usage.total_token_count or 0

        if now - last_log < 15:
            return

        usage_input = input_tokens
        usage_output = output_tokens
        usage_total = total_tokens

        input_tokens = output_tokens = total_tokens = 0
        last_log = now
        logger.info("_______________________________________")
        logger.info(f"Input tokens: {usage_input}")
        logger.info(f"Output tokens: {usage_output}")
        logger.info(f"Total tokens: {usage_total}")
        logger.info("_______________________________________")