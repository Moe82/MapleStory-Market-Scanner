
"""Analyze pending MapleStory chat messages using Gemini."""

import time

import psycopg
from google.genai import errors
from pydantic import ValidationError
from database.accessors.chat_messages import (
    get_messages,
    get_message,
    update_message_status,
)
from database.accessors.item_listings import insert_item_listing

from analyzer import analyze_messages
from shared.logging import logger

SUCCESS_COOLDOWN = 245 # budget controll
BATCH_SIZE = 10 # number of ms chat messages to process per gemini request
MAX_RETRIES = 4
POLL_INTERVAL = 5

def save_analysis(message_id, raw_text, result):
    with psycopg.connect() as conn:
        # Lock and verify the message before saving
        message = get_message(message_id, conn, for_update=True)

        if message is None or message["status"] != "PENDING":
            return

        for listing in result.listings:
            # if listing.price is None:
            #     continue
            extra_info = {
                "price": listing.price,
                "quantity": listing.quantity,
                "intent": listing.intent,
                "attributes": listing.attributes,
                "needs_review": result.needs_review or listing.needs_review,
                "cleaned_text": result.cleaned_text,
                "player_name": listing.player_name,
            }

            insert_item_listing(
                message_id=message_id,
                raw_text=raw_text,
                name=listing.name,
                extra_info=extra_info,
                status="ANALYZED",
                observed_at=message["observed_at"],
                conn=conn,
            )

        update_message_status(message_id, "ANALYZED", conn)


def main():
    logger.info("Service started")

    while True:
        try:
            messages = get_messages(BATCH_SIZE)

            if len(messages) < BATCH_SIZE:
                time.sleep(POLL_INTERVAL)
                continue

            analysis = None
            cooldown = False

            # Retry temporary server errors 3 times then sleep 1hr.
            for attempt in range(MAX_RETRIES):
                try:
                    analysis = analyze_messages(messages)
                    break

                except errors.ClientError as error:
                    if error.code != 429:
                        raise

                    logger.warning("Gemini rate limit exceeded. Retrying in 24hr...")
                    time.sleep(86400)
                    cooldown = True
                    break

                except errors.ServerError as error:
                    if error.code != 503:
                        raise

                    if attempt == MAX_RETRIES - 1:
                        logger.warning("Gemini unavailable. Retrying in 1hr...")
                        time.sleep(3600)
                        cooldown = True
                        break

                    logger.warning("Gemini unavailable. Retrying in 5 seconds...")
                    time.sleep(5)

                except (ValidationError, ValueError) as error:
                    logger.warning(f"Invalid Gemini response: {error}")

                    with psycopg.connect() as conn:
                        for message in messages:
                            update_message_status(message["id"], "FAILED", conn)

                    break

            if cooldown or analysis is None:
                continue

            while True:
                try:
                    for result in analysis.messages:
                        original = messages[result.id - 1]
                        save_analysis(original["id"],original["raw_text"],result,)

                    break

                except psycopg.Error:
                    logger.exception("Database save failed. Retrying in 5 seconds...")
                    time.sleep(POLL_INTERVAL)

            logger.info(f"Processed {len(messages)} messages")
            time.sleep(SUCCESS_COOLDOWN)

        except Exception:
            logger.exception("Unexpected analyzer error")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
