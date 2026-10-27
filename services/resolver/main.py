
"""Retrieve potential MapleStory item matches from the items table"""

import psycopg
import time
import re
from rank_bm25 import BM25Okapi
from database.accessors.items import get_all_items
from database.accessors.item_listings import get_analyzed_listings, update_listing, mark_listing_unresolved
from gemini_resolver import resolve_with_gemini

BATCH_SIZE = 10


class ItemResolver:
    def __init__(self):
        self.items = get_all_items()
        self.names = [item["name"] for item in self.items]
        self.queue = []
        self.bm25 = BM25Okapi([re.findall(r"[a-z]+", name.lower()) for name in self.names])

    
    def find_candidates(self, item: str, limit: int = 10) -> list[dict]:
        """Find catalog items whose names most closely match an (AI analyzed) item name."""

        # find the closest matches
        query_tokens = set(re.findall(r"[a-z]+", item.lower()))
        scores = self.bm25.get_scores(list(query_tokens))

        matches = sorted(
            enumerate(scores),
            key=lambda match: (
                len(query_tokens & set(re.findall(r"[a-z]+", self.names[match[0]].lower()))),
                match[1],
            ),
            reverse=True,
        )[:limit]

        return [
            {
                **self.items[index],
                "similarity": round(float(score), 2),
            }
            for index, score in matches
            if score > 0
        ]


    def process_queue(self):
        results = resolve_with_gemini(self.queue)
        for result in results.resolutions:
            original_name = self.queue[result.id - 1]["analyzed_item_name"]
            if result.item_id is None:
                print(f"Unresolved: {original_name}")
                mark_listing_unresolved(result.listing_id)
                continue
            print(f"Resolved: {original_name} -> {result.item_name}")
            update_listing(result.listing_id, result.item_name, result.item_id, 'RESOLVED')
        self.queue = []
        time.sleep(300)
    def enqueue_resolution(self, analyzed_item_name: str, listing_id: int, candidates):
        if any(item["listing_id"] == listing_id for item in self.queue):
            return
        self.queue.append({
                'analyzed_item_name': analyzed_item_name,
                'candidates': candidates,
                'listing_id': listing_id
                })
        if len(self.queue) >= BATCH_SIZE:
            self.process_queue()

    def resolve(self, analyzed_item_name: str, listing_id:int):
        candidates = self.find_candidates(analyzed_item_name, 10)
        if not candidates:
            mark_listing_unresolved(listing_id)
            return
        # check top candidate
        if candidates[0]['name'].lower() == analyzed_item_name.lower():
            update_listing(listing_id,candidates[0]['name'],candidates[0]['id'], 'RESOLVED')
        else:
            # else, resolve with gemini
            self.enqueue_resolution(analyzed_item_name, listing_id, candidates)

def main():
    # item_resolver = ItemResolver()

    # for item in item_resolver.find_candidates("Wand Scroll 60%", 10):
    #     print(f"{item['similarity']:6.2f} | {item['id']} | {item['name']}")

    print("MapleStory Resolver running.")
    item_resolver = ItemResolver()
    while True:
        analyzed_listings = get_analyzed_listings(100)
        for listing in analyzed_listings:
            item_resolver.resolve(listing["analyzed_item_name"], listing['id'])

if __name__ == "__main__":
    main()
