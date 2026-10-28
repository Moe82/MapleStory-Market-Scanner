
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
POLL_INTERVAL = 5

def save_analysis(message_id, raw_text, result):
    with psycopg.connect() as conn:
        # Lock and verify the message before saving
        message = get_message(message_id, conn, for_update=True)

        if message is None or message["status"] != "PENDING":
            return

        for listing in result.listings:
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
        messages = []

        try:
            messages = get_messages(BATCH_SIZE)

            if len(messages) < BATCH_SIZE:
                time.sleep(POLL_INTERVAL)
                continue

            try:
                analysis = analyze_messages(messages)

            except errors.ClientError as error:
                if error.code != 429:
                    raise

                logger.warning("Gemini rate limit exceeded. Retrying in 24hr...")
                time.sleep(86400)
                continue

            except errors.ServerError as error:
                if error.code != 503:
                    raise

                logger.warning("Gemini unavailable. Retrying in 1hr...")
                time.sleep(3600)
                continue

            except (ValidationError, ValueError) as error:
                logger.warning(f"Invalid Gemini response: {error}")

                with psycopg.connect() as conn:
                    for message in messages:
                        update_message_status(message["id"], "FAILED", conn)

                continue

            for result in analysis.messages:
                original = messages[result.id - 1]

                try:
                    save_analysis(original["id"],original["raw_text"],result,)

                except (psycopg.DataError, psycopg.IntegrityError):
                    logger.exception(f"Database rejected message {original['id']}. Marking FAILED.")

                    with psycopg.connect() as conn:
                        update_message_status(original["id"], "FAILED", conn)

            logger.info(f"Processed {len(messages)} messages")
            time.sleep(SUCCESS_COOLDOWN)

        except psycopg.OperationalError:
            logger.exception("Database connection failed. Retrying in 5 seconds...")
            time.sleep(POLL_INTERVAL)

        except Exception:
            logger.exception("Unexpected analyzer error. Marking batch FAILED.")

            if messages:
                try:
                    with psycopg.connect() as conn:
                        for message in messages:
                            current = get_message(message["id"], conn, for_update=True)
                            if current is not None and current["status"] == "PENDING":
                                update_message_status(message["id"], "FAILED", conn)

                except psycopg.Error:
                    logger.exception("Failed to mark batch FAILED.")

            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
