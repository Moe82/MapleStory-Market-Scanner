BEGIN;

ALTER TABLE item_listings
    RENAME COLUMN observed_at TO message_observed_at;

ALTER TABLE item_listings
    RENAME COLUMN created_at TO message_processed_at;

ALTER TABLE item_listings
    ADD COLUMN message_resolved_at TIMESTAMPTZ;

COMMIT;