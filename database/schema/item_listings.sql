CREATE TABLE item_listings (
    id BIGSERIAL PRIMARY KEY,

    message_id BIGINT NOT NULL
        REFERENCES chat_messages(id),

    raw_text TEXT NOT NULL,
    analyzed_item_name TEXT,
    extra_info JSONB,
    resolved_item_name TEXT,
    resolved_item_id BIGINT,

    status TEXT NOT NULL DEFAULT 'UNANALYZED'
        CHECK (status IN ('UNANALYZED', 'ANALYZED', 'RESOLVED', 'UNRESOLVED','REVIEW', 'FAILED')),

    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);