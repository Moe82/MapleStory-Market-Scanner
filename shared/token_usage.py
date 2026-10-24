from shared.logging.logger import logger


def log_token_usage(usage):
    """Log input, output, and total tokens consumed by a Gemini request."""
    logger.info("_______________________________________")
    logger.info(f"Input tokens: {usage.prompt_token_count}")
    logger.info(f"Output tokens: {usage.candidates_token_count}")
    logger.info(f"Total tokens: {usage.total_token_count}")
    logger.info("_______________________________________")