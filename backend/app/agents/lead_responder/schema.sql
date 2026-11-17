-- =============================================================================
-- Enterprise Sales Agent Platform: Production SQLite Schema
-- File: backend/app/agents/lead_responder/schema.sql
-- Converted from PostgreSQL to SQLite 3
-- =============================================================================

PRAGMA foreign_keys = ON;

-- 1. ACCOUNTS: Companies we target
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    industry TEXT,
    website TEXT,
    domain TEXT UNIQUE,
    country TEXT DEFAULT 'US',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 2. CONTACTS: Individual prospects and inbound leads
CREATE TABLE IF NOT EXISTS contacts (
    contact_id TEXT PRIMARY KEY,
    account_id TEXT REFERENCES accounts(account_id),
    name TEXT,
    role TEXT,
    timezone TEXT DEFAULT 'CST',
    lead_source TEXT NOT NULL DEFAULT 'unknown'
        CHECK (lead_source IN (
            'industry_outreach',
            'direct_sms',
            'direct_email',
            'website',
            'partner_referral',
            'unknown'
        )),
    lead_status TEXT NOT NULL DEFAULT 'new'
        CHECK (lead_status IN (
            'new', 'engaged', 'qualified',
            'disqualified', 'customer'
        )),
    notes TEXT,
    crm_contact_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 3. CONTACT IDENTIFIERS: Phone and email identities
CREATE TABLE IF NOT EXISTS contact_identifiers (
    identifier_id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL REFERENCES contacts(contact_id),
    channel TEXT NOT NULL CHECK (channel IN ('sms', 'email')),
    value_normalized TEXT NOT NULL,
    is_verified INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'invalid', 'unverified')),
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(channel, value_normalized)
);

-- 4. AI SERVICES: Solutions our company offers
CREATE TABLE IF NOT EXISTS ai_services (
    service_id TEXT PRIMARY KEY,
    service_name TEXT NOT NULL,
    industry_tags TEXT,               -- Stored as JSON array or string
    description TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 5. DEMO ASSETS: Existing hosted demos
CREATE TABLE IF NOT EXISTS demo_assets (
    demo_id TEXT PRIMARY KEY,
    service_id TEXT REFERENCES ai_services(service_id),
    contact_id TEXT REFERENCES contacts(contact_id),
    demo_title TEXT NOT NULL,
    demo_url TEXT,
    demo_description TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN (
            'draft', 'validated', 'approved',
            'expired', 'disabled'
        )),
    expires_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 6. OUTREACH CONTEXT: Information from previous agents
CREATE TABLE IF NOT EXISTS outreach_contexts (
    outreach_id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL REFERENCES contacts(contact_id),
    service_id TEXT REFERENCES ai_services(service_id),
    demo_id TEXT REFERENCES demo_assets(demo_id),
    source_agent TEXT DEFAULT 'agent4',
    research_summary TEXT,
    identified_problem TEXT,
    why_now TEXT,
    source_evidence TEXT,            -- Stored as JSON
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN (
            'proposed', 'reviewed', 'active', 'closed'
        )),
    created_at TEXT DEFAULT (datetime('now'))
);

-- 7. CHANNEL ACCOUNTS: Our sending/receiving identities
CREATE TABLE IF NOT EXISTS channel_accounts (
    channel_account_id TEXT PRIMARY KEY,
    channel TEXT NOT NULL CHECK (channel IN ('sms', 'email')),
    provider TEXT NOT NULL,          -- 'siplink', 'sendgrid', 'graph'
    address TEXT NOT NULL,           -- phone number or email address
    is_active INTEGER DEFAULT 1,
    UNIQUE(provider, channel, address)
);

-- 8. CONVERSATIONS: Customer conversation threads
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL REFERENCES contacts(contact_id),
    channel_account_id TEXT NOT NULL REFERENCES channel_accounts(channel_account_id),
    provider_thread_key TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN (
            'active', 'pending_review',
            'human_owned', 'closed', 'suppressed'
        )),
    assigned_user_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    last_message_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(channel_account_id, provider_thread_key)
);

-- 9. INBOUND EVENTS: Incoming webhook/event records
CREATE TABLE IF NOT EXISTS inbound_events (
    event_id TEXT PRIMARY KEY,
    channel_account_id TEXT NOT NULL REFERENCES channel_accounts(channel_account_id),
    provider_event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT,                     -- Stored as JSON
    status TEXT NOT NULL DEFAULT 'received'
        CHECK (status IN (
            'received', 'processing',
            'processed', 'ignored', 'failed'
        )),
    received_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT,
    UNIQUE(channel_account_id, provider_event_id)
);

-- 10. MESSAGES: Actual inbound/outbound messages
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    channel_account_id TEXT NOT NULL REFERENCES channel_accounts(channel_account_id),
    inbound_event_id TEXT REFERENCES inbound_events(event_id),
    provider_message_id TEXT,
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    body TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'received'
        CHECK (delivery_status IN (
            'received', 'submitted', 'delivered',
            'failed', 'send_unknown'
        )),
    created_at TEXT DEFAULT (datetime('now')),
    provider_timestamp TEXT
);

-- Prevent duplicate provider message records
CREATE UNIQUE INDEX IF NOT EXISTS ux_provider_message
ON messages(channel_account_id, provider_message_id)
WHERE provider_message_id IS NOT NULL;

-- 11. NEW INBOUND LEADS: Unknown/direct inquiries
CREATE TABLE IF NOT EXISTS new_inbound_leads (
    lead_id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL REFERENCES contacts(contact_id),
    first_message_id TEXT NOT NULL UNIQUE REFERENCES messages(message_id),
    source TEXT NOT NULL CHECK (source IN ('direct_sms', 'direct_email', 'website')),
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewed', 'converted', 'rejected')),
    received_at TEXT DEFAULT (datetime('now'))
);

-- 12. SUPPRESSION ENTRIES: STOP / negative / invalid
CREATE TABLE IF NOT EXISTS suppression_entries (
    suppression_id TEXT PRIMARY KEY,
    contact_id TEXT REFERENCES contacts(contact_id),
    identifier_id TEXT REFERENCES contact_identifiers(identifier_id),
    scope TEXT NOT NULL DEFAULT 'all' CHECK (scope IN ('all', 'sms', 'email')),
    reason TEXT NOT NULL CHECK (reason IN ('opt_out', 'not_interested', 'wrong_number', 'bot', 'manual_block', 'other')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    cleared_at TEXT,
    cleared_by TEXT,
    CHECK (contact_id IS NOT NULL OR identifier_id IS NOT NULL)
);

-- 13. KNOWLEDGE ARTICLES: Approved company information
CREATE TABLE IF NOT EXISTS knowledge_articles (
    article_id TEXT PRIMARY KEY,
    service_id TEXT REFERENCES ai_services(service_id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_reference TEXT,
    access_level TEXT NOT NULL DEFAULT 'internal' CHECK (access_level IN ('response_safe', 'internal', 'restricted')),
    approval_status TEXT NOT NULL DEFAULT 'draft' CHECK (approval_status IN ('draft', 'approved', 'retired')),
    approved_at TEXT,
    valid_until TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 14. MEMORY FACTS: Customer-specific memory
CREATE TABLE IF NOT EXISTS memory_facts (
    memory_id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL REFERENCES contacts(contact_id),
    conversation_id TEXT REFERENCES conversations(conversation_id),
    source_message_id TEXT REFERENCES messages(message_id),
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,          -- Stored as JSON
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'deleted')),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 15. AGENT RUNS: Every AI processing execution
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    trigger_message_id TEXT NOT NULL REFERENCES messages(message_id),
    agent_name TEXT NOT NULL DEFAULT 'agent4',
    detected_intent TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'waiting_for_review', 'completed', 'blocked', 'failed', 'cancelled')),
    context_version INTEGER,
    error_details TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 16. MESSAGE DRAFTS: Generated responses awaiting human review
CREATE TABLE IF NOT EXISTS message_drafts (
    draft_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    run_id TEXT REFERENCES agent_runs(run_id),
    contact_id TEXT REFERENCES contacts(contact_id),
    channel TEXT NOT NULL CHECK (channel IN ('sms', 'email')),
    draft_subject TEXT,
    draft_body TEXT NOT NULL,
    proposed_meeting_time TEXT,
    intent TEXT,
    status TEXT NOT NULL DEFAULT 'pending_review' CHECK (status IN ('pending_review', 'approved', 'rejected', 'edited', 'sent')),
    requires_human_approval INTEGER NOT NULL DEFAULT 1,
    reviewer_notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_contacts_acc ON contacts(account_id);
CREATE INDEX IF NOT EXISTS idx_ident_val ON contact_identifiers(value_normalized);
CREATE INDEX IF NOT EXISTS idx_conv_contact ON conversations(contact_id);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_mem_contact ON memory_facts(contact_id);
CREATE INDEX IF NOT EXISTS idx_supp_ident ON suppression_entries(identifier_id);
CREATE INDEX IF NOT EXISTS idx_draft_conv ON message_drafts(conversation_id);
CREATE INDEX IF NOT EXISTS idx_draft_run ON message_drafts(run_id);
