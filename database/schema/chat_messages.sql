CREATE TABLE chat_messages (
    id BIGSERIAL PRIMARY KEY,
    raw_text TEXT NOT NULL,
    screenshot_filename TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN (
            'PENDING',
            'ANALYZED',
            'RESOLVED',
            'FAILED'
        ))
);