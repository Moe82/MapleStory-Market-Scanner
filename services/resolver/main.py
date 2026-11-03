
"""Retrieve potential MapleStory item matches from the items table"""

import psycopg
import time
import re
import heapq
from rank_bm25 import BM25Okapi
from database.accessors.items import get_all_items
from database.accessors.item_listings import get_analyzed_listings, update_listing, update_listing_status
from gemini_resolver import resolve_with_gemini
from shared.logging import logger


BATCH_SIZE = 10
MAX_BATCH_WAIT = 10


class ItemResolver:
    def __init__(self):
        self.items = get_all_items()
        self.names = [item["name"] for item in self.items]
        self.queue = []
        self.queue_started_at = None
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


    def process_queue(self):
        try:
            results = resolve_with_gemini(self.queue)
        except ValueError:
            logger.exception("Gemini resolver returned an invalid response. Marking batch unresolved.")
            for item in self.queue:
                update_listing_status(item["listing_id"],"FAILED")
            self.queue = []
            self.queue_started_at = None
            return

        for result in results.resolutions:
            original_name = self.queue[result.id - 1]["analyzed_item_name"]
            if result.item_id is None:
                print(f"Unresolved: {original_name}")
                update_listing_status(result.listing_id,"UNRESOLVED")
                continue
            print(f"Resolved: {original_name} -> {result.item_name}")
            update_listing(result.listing_id, result.item_name, result.item_id, 'RESOLVED')
        self.queue = []
        self.queue_started_at = None


    def enqueue_resolution(self, analyzed_item_name: str, listing_id: int, candidates):
        if any(item["listing_id"] == listing_id for item in self.queue):
            return
        if not self.queue:
            self.queue_started_at = time.monotonic()
        self.queue.append({
                'analyzed_item_name': analyzed_item_name,
                'candidates': candidates,
                'listing_id': listing_id
                })
        if len(self.queue) >= BATCH_SIZE:
            self.process_queue()

    def resolve(self, analyzed_item_name: str, listing_id:int):
        if any(item["listing_id"] == listing_id for item in self.queue):
            return
        candidates = self.find_candidates(analyzed_item_name, 10)
        if not candidates:
            update_listing_status(listing_id, "UNRESOLVED")
            return
        # check top candidate
        if candidates[0]['name'].lower() == analyzed_item_name.lower():
            update_listing(listing_id,candidates[0]['name'],candidates[0]['id'], 'RESOLVED')
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

        if item_resolver.queue and (
            len(item_resolver.queue) >= BATCH_SIZE
            or time.monotonic() - item_resolver.queue_started_at >= MAX_BATCH_WAIT
        ):
            item_resolver.process_queue()

        time.sleep(1)

if __name__ == "__main__":
    main()
