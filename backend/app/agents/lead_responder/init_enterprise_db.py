"""
Enterprise Database Initializer for SQLite.
File: backend/app/agents/lead_responder/init_enterprise_db.py

Initializes all 15 tables from schema.sql and seeds:
1. Channel Accounts (Our SMS sender + Email sender)
2. AI Services (Healthcare Intake + FinTech Loan Extraction)
3. Target Accounts & Contacts (Dr. Sarah Jenkins, Alex Murphy, David Patel)
4. Contact Identifiers (Phones and Emails)
5. Demo Assets (Type A with demo)
6. Outreach Contexts (Links contact to demo / outreach type)
"""

import os
import shutil
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "lead_responder.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
BACKUP_PATH = Path(__file__).parent / "lead_responder.db.bak"


def init_database():
    # 1. Backup old database if exists
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, BACKUP_PATH)
        os.remove(DB_PATH)
        print(f"Backed up old database to: {BACKUP_PATH.name}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")

    # 2. Execute schema.sql
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        sql_script = f.read()
    conn.executescript(sql_script)
    print("Executed schema.sql: All 15 enterprise tables created successfully!")

    # 3. Seed Channel Accounts (Our sending identities)
    conn.executescript("""
        INSERT INTO channel_accounts (channel_account_id, channel, provider, address, is_active)
        VALUES 
            ('chan_sms_01', 'sms', 'siplink', '14158201488', 1),
            ('chan_email_01', 'email', 'sendgrid', 'sales@adople.ai', 1);
            
        -- Seed AI Services
        INSERT INTO ai_services (service_id, service_name, industry_tags, description, is_active)
        VALUES 
            ('serv_intake', 'AI Referral Intake & EMR Parser', '["healthcare", "clinic"]', 'Automates inbound patient referrals and clinical document extraction.', 1),
            ('serv_lending', 'Commercial Loan Document Extraction Workflow', '["fintech", "banking"]', 'Parses commercial balance sheets and credit reports into underwriting models.', 1),
            ('serv_portfolio', 'Private Equity Portfolio Automation', '["finance", "private_equity"]', 'Automates portfolio monitoring and fund reporting.', 1);

        -- Seed Accounts
        INSERT INTO accounts (account_id, company_name, industry, website, domain, country)
        VALUES 
            ('acc_metro', 'Metro Health Clinic', 'Healthcare', 'https://metrohealth.org', 'metrohealth.org', 'US'),
            ('acc_omni', 'OmniCorp FinTech', 'Financial Services', 'https://omnicorp.com', 'omnicorp.com', 'US'),
            ('acc_apex', 'Apex Capital', 'Private Equity', 'https://apexcap.com', 'apexcap.com', 'US');

        -- Seed Contacts
        INSERT INTO contacts (contact_id, account_id, name, role, timezone, lead_source, lead_status, notes)
        VALUES 
            ('con_001', 'acc_metro', 'Dr. Sarah Jenkins', 'VP Clinical Operations', 'CST', 'industry_outreach', 'engaged', 'Met at HIMSS. Looking to reduce intake backlog.'),
            ('con_002', 'acc_omni', 'Alex Murphy', 'Head of IT', 'CST', 'industry_outreach', 'new', 'Interested in SOC 2 compliance and US data residency.'),
            ('con_003', 'acc_apex', 'David Patel', 'Managing Director', 'EST', 'industry_outreach', 'new', 'Outreach sent on portfolio automation. No demo sent.');

        -- Seed Contact Identifiers (Phone & Email)
        INSERT INTO contact_identifiers (identifier_id, contact_id, channel, value_normalized, is_verified)
        VALUES 
            ('ident_001_p', 'con_001', 'sms', '15125550199', 1),
            ('ident_001_e', 'con_001', 'email', 'sarah.jenkins@metrohealth.org', 1),
            ('ident_002_p', 'con_002', 'sms', '12145558900', 1),
            ('ident_002_e', 'con_002', 'email', 'amurphy@omnicorp.com', 1),
            ('ident_003_p', 'con_003', 'sms', '14155552345', 1),
            ('ident_003_e', 'con_003', 'email', 'dpatel@apexcap.com', 1);

        -- Seed Demo Assets (Type A: with demo)
        INSERT INTO demo_assets (demo_id, service_id, contact_id, demo_title, demo_url, demo_description, status)
        VALUES 
            ('demo_001', 'serv_intake', 'con_001', 'AI Referral Intake & EMR Parser', 'https://sipl.io/j9x2', 'Interactive 60s preview of referral parser.', 'approved'),
            ('demo_002', 'serv_lending', 'con_002', 'Loan Document Extraction Workflow', 'https://sipl.io/omni88', 'Interactive loan doc parsing workflow.', 'approved');

        -- Seed Outreach Contexts (Links Contact to Outreach Type, Matched Service & Prior Research)
        INSERT INTO outreach_contexts (outreach_id, contact_id, service_id, demo_id, source_agent, identified_problem, why_now, research_summary, status)
        VALUES 
            ('outreach_001', 'con_001', 'serv_intake', 'demo_001', 'agent4', 
             'Possible manual referral processing & outpatient clinic backlog', 
             'Expanding clinical intake staffing across Houston outpatient network',
             'Previous Agent 4 research: Clinic expanding footprint; physician referral backlog high.', 
             'active'),
            ('outreach_002', 'con_002', 'serv_lending', 'demo_002', 'agent4', 
             'Manual commercial loan file underwriting turnaround times', 
             'Expanding commercial loan originations portfolio',
             'Previous Agent 4 research: Looking to automate balance sheet and tax return extraction.', 
             'active'),
            ('outreach_003', 'con_003', 'serv_portfolio', NULL, 'agent4', 
             'Manual portfolio company quarterly financial roll-ups', 
             'New fund close requiring streamlined reporting to LPs',
             'Previous Agent 4 research: Multi-entity reporting roll-up automation.', 
             'active');

        -- Seed Knowledge Articles (Approved response-safe facts for Node 5)
        INSERT INTO knowledge_articles (article_id, service_id, title, content, access_level, approval_status, approved_at)
        VALUES 
            ('art_hipaa', 'serv_intake', 'HIPAA Compliance & BAA Execution', 
             'Adople AI is fully HIPAA compliant. Business Associate Agreements (BAAs) are executed for all healthcare deployments. Data is stored exclusively in dedicated US-based AWS regions with zero training on public models.', 
             'response_safe', 'approved', datetime('now')),
            ('art_soc2', NULL, 'SOC 2 Type II Certification', 
             'Adople AI holds SOC 2 Type II certification. Systems feature AES-256 encryption at rest, TLS 1.3 in transit, and continuous third-party compliance auditing.', 
             'response_safe', 'approved', datetime('now')),
            ('art_emr', 'serv_intake', 'EMR Integration Capabilities', 
             'Direct bidirectional integration with Epic Systems, Oracle Cerner, and AthenaHealth via FHIR REST APIs and HL7 feeds.', 
             'response_safe', 'approved', datetime('now'));

        -- Seed Conversations
        INSERT INTO conversations (conversation_id, contact_id, channel_account_id, provider_thread_key, status, version)
        VALUES 
            ('conv_001', 'con_001', 'chan_sms_01', 'sms_15125550199', 'active', 1),
            ('conv_002', 'con_002', 'chan_sms_01', 'sms_12145558900', 'active', 1),
            ('conv_003', 'con_003', 'chan_email_01', 'email_dpatel@apexcap.com', 'active', 1);

        -- Seed initial outreach messages
        INSERT INTO messages (message_id, conversation_id, channel_account_id, direction, body, delivery_status, provider_timestamp)
        VALUES 
            ('msg_out_001', 'conv_001', 'chan_sms_01', 'outbound', 'Hi Dr. Sarah, saw Metro Health is expanding intake staffing. Built a 60s interactive preview for your team: https://sipl.io/j9x2', 'delivered', datetime('now', '-1 day')),
            ('msg_out_002', 'conv_002', 'chan_sms_01', 'outbound', 'Alex, quick demo showing automated commercial loan document extraction: https://sipl.io/omni88', 'delivered', datetime('now', '-2 days')),
            ('msg_out_003', 'conv_003', 'chan_email_01', 'outbound', 'David, following up regarding automated portfolio extraction for Apex Capital funds.', 'delivered', datetime('now', '-3 days'));
    """)

    conn.commit()
    conn.close()
    print("Database seeding completed! All 15 tables are now live with sample data.")


if __name__ == "__main__":
    init_database()
