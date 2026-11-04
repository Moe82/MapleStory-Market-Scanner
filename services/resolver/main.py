
"""Retrieve potential MapleStory item matches from the items table"""

import psycopg
import time
import re
import heapq
from rank_bm25 import BM25Okapi
from rapidfuzz import process, fuzz, utils
from database.accessors.items import get_all_items
from database.accessors.item_listings import get_analyzed_listings, update_listing, update_listing_status
from gemini_resolver import resolve_with_gemini
from shared.logging import logger


BATCH_SIZE = 10
MAX_BATCH_WAIT = 10
MAX_FAILED_BATCH_WAIT = 30


class ItemResolver:
    """ Uses BM25 as the primary ranking function and fuzzy matching as backup """
    def __init__(self):
        self.items = get_all_items()
        self.names = [item["name"] for item in self.items]

        self.bm25_queue = []
        self.bm25_queue_started_at = None

        self.fuzzy_queue = []
        self.fuzzy_queue_started_at = None

        self.name_tokens = [re.findall(r"[a-z]+", name.lower()) for name in self.names]
        self.name_token_sets = [set(tokens) for tokens in self.name_tokens]
        self.bm25 = BM25Okapi(self.name_tokens)

    def find_candidates(self, item: str, limit: int = 10) -> list[dict]:
        """Find catalog items whose names most closely match an (AI analyzed) item name"""

        # find the closest matches
        query_tokens = set(re.findall(r"[a-z]+", item.lower()))
        scores = self.bm25.get_scores(list(query_tokens))

        matches = heapq.nlargest(
            limit,
            enumerate(scores),
            key=lambda match: (
                len(query_tokens & self.name_token_sets[match[0]]),
                match[1],
            ),
        )

        return [
            {
                **self.items[index],
                "similarity": round(float(score), 2),
            }
            for index, score in matches
            if query_tokens & self.name_token_sets[index]
        ]

    def find_fuzzy_candidates(self, item: str, limit: int = 10) -> list[dict]:
        """Find fuzzy catalog matches when BM25 cannot resolve an item."""

        aliases = {
            "kfan": "Korean Fan",
        }

        query = aliases.get(item.lower().strip(), item)

        matches = process.extract(
            query,
            self.names,
            scorer=fuzz.WRatio,
            processor=utils.default_process,
            limit=limit,
        )

        return [
            {
                **self.items[index],
                "similarity": round(score, 2),
            }
            for _, score, index in matches
        ]

    def process_queue(self, fuzzy=False):
        queue = self.fuzzy_queue if fuzzy else self.bm25_queue

        if not queue:
            return

        try:
            results = resolve_with_gemini(queue)
        except ValueError:
            logger.exception("Gemini resolver returned an invalid response. Marking batch unresolved.")
            for item in queue:
                update_listing_status(item["listing_id"], "FAILED")

            if fuzzy:
                self.fuzzy_queue = []
                self.fuzzy_queue_started_at = None
            else:
                self.bm25_queue = []
                self.bm25_queue_started_at = None
            return

        # Clear the processed queue before moving failed BM25 items to fuzzy
        if fuzzy:
            self.fuzzy_queue = []
            self.fuzzy_queue_started_at = None
        else:
            self.bm25_queue = []
            self.bm25_queue_started_at = None

        for result in results.resolutions:
            original_name = queue[result.id - 1]["analyzed_item_name"]

            if result.item_id is None:
                if fuzzy:
                    print(f"Unresolved (fuzzy): {original_name}")
                    update_listing_status(result.listing_id, "UNRESOLVED")
                else:
                    print(f"Unresolved (BM25), trying fuzzy: {original_name}")
                    self.retry_with_fuzzy(original_name, result.listing_id)
                continue

            print(f"Resolved ({'fuzzy' if fuzzy else 'BM25'}): {original_name} -> {result.item_name}")
            update_listing(result.listing_id, result.item_name, result.item_id, 'RESOLVED')

    def enqueue_resolution(self, analyzed_item_name: str, listing_id: int, candidates, fuzzy=False):
        if any(item["listing_id"] == listing_id for item in self.bm25_queue + self.fuzzy_queue):
            return

        queue = self.fuzzy_queue if fuzzy else self.bm25_queue

        if not queue:
            if fuzzy:
                self.fuzzy_queue_started_at = time.monotonic()
            else:
                self.bm25_queue_started_at = time.monotonic()

        queue.append({
            'analyzed_item_name': analyzed_item_name,
            'candidates': candidates,
            'listing_id': listing_id
        })

        if len(queue) >= BATCH_SIZE:
            self.process_queue(fuzzy=fuzzy)

    def retry_with_fuzzy(self, analyzed_item_name: str, listing_id: int):
        candidates = self.find_fuzzy_candidates(analyzed_item_name, 10)

        if not candidates:
            update_listing_status(listing_id, "UNRESOLVED")
            return

        self.enqueue_resolution(analyzed_item_name, listing_id, candidates, fuzzy=True)

    def resolve(self, analyzed_item_name: str, listing_id: int):
        if any(item["listing_id"] == listing_id for item in self.bm25_queue + self.fuzzy_queue):
            return

        candidates = self.find_candidates(analyzed_item_name, 10)

        if not candidates:
            self.retry_with_fuzzy(analyzed_item_name, listing_id)
            return

        # check top candidate
        if candidates[0]['name'].lower() == analyzed_item_name.lower():
            update_listing(listing_id, candidates[0]['name'], candidates[0]['id'], 'RESOLVED')
        else:
            # else, resolve with gemini
            self.enqueue_resolution(analyzed_item_name, listing_id, candidates)

def main():
    logger.info("Service Started")
    item_resolver = ItemResolver()
    last_poll = 0

    while True:
        if time.monotonic() - last_poll >= 5:
            analyzed_listings = get_analyzed_listings(100)
            last_poll = time.monotonic()

            for listing in analyzed_listings:
                item_resolver.resolve(listing["analyzed_item_name"], listing['id'])

        if item_resolver.bm25_queue and (
            len(item_resolver.bm25_queue) >= BATCH_SIZE
            or time.monotonic() - item_resolver.bm25_queue_started_at >= MAX_BATCH_WAIT
        ):
            item_resolver.process_queue()

        if item_resolver.fuzzy_queue and (
            len(item_resolver.fuzzy_queue) >= BATCH_SIZE
            or time.monotonic() - item_resolver.fuzzy_queue_started_at >= MAX_FAILED_BATCH_WAIT
        ):
            item_resolver.process_queue(fuzzy=True)

        time.sleep(1)

if __name__ == "__main__":
    main()
