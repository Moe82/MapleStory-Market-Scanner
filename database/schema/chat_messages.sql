CREATE TABLE chat_messages (
    id BIGSERIAL PRIMARY KEY,
    raw_text TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'PENDING',
            'ANALYZED',
            'FAILED'
        ))
);