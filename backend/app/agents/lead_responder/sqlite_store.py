"""
Enterprise SQLite Contact and Conversation Store (15-Table Architecture).
File: backend/app/agents/lead_responder/sqlite_store.py

Implements relational storage across:
- accounts, contacts, contact_identifiers
- demo_assets, outreach_contexts, channel_accounts
- conversations, messages, new_inbound_leads
- suppression_entries, memory_facts, agent_runs
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.agents.lead_responder.node_1_email_sms import normalize_email, normalize_phone

DB_PATH = Path(__file__).parent / "lead_responder.db"


class SQLiteContactStore:
    """Production Store backed by the 15-table SQLite relational database."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def create_or_update_contact(
        self,
        name: str,
        company: str,
        email: str = "",
        phone: str = "",
        role: str = "Prospect",
        industry: str = "Healthcare",
        timezone: str = "CST",
        notes: str = "",
        has_demo: int = 0,
        demo_title: Optional[str] = None,
        demo_url: Optional[str] = None,
        initial_outreach: Optional[str] = None,
        contact_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates or updates a contact across the relational tables: accounts, contacts, identifiers, demos."""
        cid = contact_id or f"con_{uuid.uuid4().hex[:8]}"
        aid = f"acc_{uuid.uuid4().hex[:8]}"
        clean_email = normalize_email(email) if email else None
        clean_phone = normalize_phone(phone) if phone else None
        now_str = datetime.now(timezone_utc if (timezone_utc := getattr(timezone, "utc", None)) else None).isoformat()

        with self._get_connection() as conn:
            # 1. Insert Account
            conn.execute("""
                INSERT INTO accounts (account_id, company_name, industry)
                VALUES (?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET company_name = excluded.company_name, industry = excluded.industry;
            """, (aid, company, industry))

            # 2. Insert Contact
            conn.execute("""
                INSERT INTO contacts (contact_id, account_id, name, role, timezone, lead_source, lead_status, notes)
                VALUES (?, ?, ?, ?, ?, 'industry_outreach', 'new', ?)
                ON CONFLICT(contact_id) DO UPDATE SET
                    name = excluded.name, role = excluded.role, timezone = excluded.timezone, notes = excluded.notes;
            """, (cid, aid, name, role, timezone, notes))

            # 3. Insert Identifiers (Email and Phone)
            if clean_email:
                conn.execute("""
                    INSERT INTO contact_identifiers (identifier_id, contact_id, channel, value_normalized, is_verified)
                    VALUES (?, ?, 'email', ?, 1)
                    ON CONFLICT(channel, value_normalized) DO NOTHING;
                """, (f"ident_{uuid.uuid4().hex[:8]}", cid, clean_email))

            if clean_phone:
                conn.execute("""
                    INSERT INTO contact_identifiers (identifier_id, contact_id, channel, value_normalized, is_verified)
                    VALUES (?, ?, 'sms', ?, 1)
                    ON CONFLICT(channel, value_normalized) DO NOTHING;
                """, (f"ident_{uuid.uuid4().hex[:8]}", cid, clean_phone))

            # 4. Insert Demo & Outreach Context
            demo_id = None
            if has_demo and (demo_title or demo_url):
                demo_id = f"demo_{uuid.uuid4().hex[:8]}"
                conn.execute("""
                    INSERT INTO demo_assets (demo_id, contact_id, demo_title, demo_url, status)
                    VALUES (?, ?, ?, ?, 'approved');
                """, (demo_id, cid, demo_title or "Interactive AI Preview", demo_url or "https://sipl.io/preview"))

            serv_id = "serv_intake" if "health" in industry.lower() else "serv_lending" if ("fin" in industry.lower() or "bank" in industry.lower()) else "serv_portfolio"
            problem = f"Manual {industry.lower()} document processing and operational backlogs"
            summary = f"Prior Agent 4 research for {company}: evaluating automation solutions for {industry} workflows."

            conn.execute("""
                INSERT INTO outreach_contexts (outreach_id, contact_id, service_id, demo_id, source_agent, identified_problem, research_summary, status)
                VALUES (?, ?, ?, ?, 'agent4', ?, ?, 'active');
            """, (f"outreach_{uuid.uuid4().hex[:8]}", cid, serv_id, demo_id, problem, summary))

            # 5. Insert initial conversation & outreach message if supplied
            if initial_outreach:
                channel_pref = "email" if clean_email else "sms"
                cur = conn.execute("SELECT channel_account_id FROM channel_accounts WHERE channel = ? LIMIT 1;", (channel_pref,))
                row = cur.fetchone()
                chan_id = row["channel_account_id"] if row else "chan_sms_01"
                conv_id = f"conv_{uuid.uuid4().hex[:8]}"
                conn.execute("""
                    INSERT INTO conversations (conversation_id, contact_id, channel_account_id, status)
                    VALUES (?, ?, ?, 'active');
                """, (conv_id, cid, chan_id))
                conn.execute("""
                    INSERT INTO messages (message_id, conversation_id, channel_account_id, direction, body, delivery_status)
                    VALUES (?, ?, ?, 'outbound', ?, 'delivered');
                """, (f"msg_{uuid.uuid4().hex[:8]}", conv_id, chan_id, initial_outreach))

            conn.commit()

        return self.find_by_identifier(clean_email or clean_phone or cid) or {
            "contact_id": cid,
            "name": name,
            "company": company,
            "email": clean_email,
            "phone": clean_phone,
            "has_demo": has_demo,
            "demo_title": demo_title,
        }

    def find_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Unified finder: Matches phone or email against contact_identifiers,
        joining contacts, accounts, outreach_contexts, and ai_services to resolve:
        - industry & matched_service (Fix 4)
        - previous-agent research & outreach_context (Fix 5)
        - demo assets (Type A with demo vs Type B without demo)
        """
        clean_val = normalize_email(identifier) if "@" in identifier else normalize_phone(identifier)
        if not clean_val:
            return None

        query = """
            SELECT 
                c.contact_id,
                c.account_id,
                c.name,
                c.role,
                c.timezone,
                c.lead_source,
                c.lead_status,
                c.notes,
                a.company_name,
                a.industry,
                oc.demo_id,
                oc.service_id,
                oc.identified_problem,
                oc.why_now,
                oc.research_summary,
                s.service_name as matched_service,
                da.demo_title,
                da.demo_url
            FROM contact_identifiers ci
            JOIN contacts c ON ci.contact_id = c.contact_id
            LEFT JOIN accounts a ON c.account_id = a.account_id
            LEFT JOIN outreach_contexts oc ON oc.contact_id = c.contact_id
            LEFT JOIN ai_services s ON oc.service_id = s.service_id
            LEFT JOIN demo_assets da ON oc.demo_id = da.demo_id
            WHERE (ci.value_normalized = ? OR ci.value_normalized LIKE ?)
              AND ci.status != 'invalid'
            LIMIT 1;
        """
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (clean_val, f"%{clean_val[-10:]}"))
            row = cur.fetchone()
            if not row:
                return None

            data = dict(row)
            data["company"] = data.get("company_name") or "Direct Inbound Account"
            data["has_demo"] = 1 if data.get("demo_id") else 0
            
            # Infer matched_service from industry if not explicitly set
            if not data.get("matched_service") and data.get("industry"):
                ind_lower = data["industry"].lower()
                if "health" in ind_lower or "clinic" in ind_lower:
                    data["matched_service"] = "AI Referral Intake & EMR Parser"
                elif "fin" in ind_lower or "bank" in ind_lower or "loan" in ind_lower:
                    data["matched_service"] = "Commercial Loan Document Extraction Workflow"
                elif "equity" in ind_lower or "capital" in ind_lower:
                    data["matched_service"] = "Private Equity Portfolio Automation"

            data["outreach_context"] = data.get("research_summary") or (
                f"Previous outreach for {data['company']} regarding {data.get('matched_service', 'automation')}"
            )

            # Look up associated phone and email identifiers
            cur.execute("SELECT channel, value_normalized FROM contact_identifiers WHERE contact_id = ? AND status != 'invalid';", (data["contact_id"],))
            for id_row in cur.fetchall():
                if id_row["channel"] == "email" and not data.get("email"):
                    data["email"] = id_row["value_normalized"]
                elif id_row["channel"] == "sms" and not data.get("phone"):
                    data["phone"] = id_row["value_normalized"]

            if not data.get("email") and "@" in clean_val:
                data["email"] = clean_val
            if not data.get("phone") and "@" not in clean_val:
                data["phone"] = clean_val

            # Check suppression table
            cur.execute("SELECT reason FROM suppression_entries WHERE contact_id = ? AND is_active = 1 LIMIT 1;", (data["contact_id"],))
            supp = cur.fetchone()
            data["is_suppressed"] = 1 if supp else 0
            data["suppression_reason"] = supp["reason"] if supp else None
            return data

    def find_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        return self.find_by_identifier(phone)

    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self.find_by_identifier(email)

    def record_new_inbound_lead(
        self,
        identifier: str,
        channel: str,
        sender_id: str,
        first_message: str,
        received_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Registers a brand-new unknown lead into:
        1. accounts (New prospect account)
        2. contacts
        3. contact_identifiers
        4. conversations
        5. messages
        6. new_inbound_leads (Dedicated new leads table!)
        """
        clean_val = normalize_email(identifier) if "@" in identifier else normalize_phone(identifier)
        channel_clean = channel.lower()
        now_str = datetime.now(timezone.utc).isoformat()
        rec_time = received_at or now_str

        account_id = f"acc_{uuid.uuid4().hex[:8]}"
        contact_id = f"con_{uuid.uuid4().hex[:8]}"
        ident_id = f"ident_{uuid.uuid4().hex[:8]}"
        conv_id = f"conv_{uuid.uuid4().hex[:8]}"
        msg_id = f"msg_{uuid.uuid4().hex[:8]}"
        lead_id = f"lead_{uuid.uuid4().hex[:8]}"

        with self._get_connection() as conn:
            # Get default channel account
            cur = conn.execute("SELECT channel_account_id FROM channel_accounts WHERE channel = ? LIMIT 1;", (channel_clean,))
            row = cur.fetchone()
            channel_acc_id = row["channel_account_id"] if row else "chan_sms_01"

            # 1. Create account
            conn.execute("""
                INSERT INTO accounts (account_id, company_name, industry)
                VALUES (?, ?, 'Direct Inbound Prospect');
            """, (account_id, f"Inbound Account ({clean_val})"))

            # 2. Create contact
            conn.execute("""
                INSERT INTO contacts (contact_id, account_id, name, role, timezone, lead_source, lead_status, notes)
                VALUES (?, ?, ?, 'Inbound Prospect', 'CST', ?, 'new', 'Direct inbound inquiry.');
            """, (contact_id, account_id, f"New Prospect ({clean_val})", f"direct_{channel_clean}"))

            # 3. Create identifier
            conn.execute("""
                INSERT INTO contact_identifiers (identifier_id, contact_id, channel, value_normalized, is_verified)
                VALUES (?, ?, ?, ?, 1);
            """, (ident_id, contact_id, channel_clean, clean_val))

            # 4. Create conversation
            conn.execute("""
                INSERT INTO conversations (conversation_id, contact_id, channel_account_id, provider_thread_key, status)
                VALUES (?, ?, ?, ?, 'active');
            """, (conv_id, contact_id, channel_acc_id, f"{channel_clean}_{clean_val}"))

            # 5. Create first message
            conn.execute("""
                INSERT INTO messages (message_id, conversation_id, channel_account_id, direction, body, delivery_status, provider_timestamp)
                VALUES (?, ?, ?, 'inbound', ?, 'received', ?);
            """, (msg_id, conv_id, channel_acc_id, first_message, rec_time))

            # 6. Insert into new_inbound_leads table!
            conn.execute("""
                INSERT INTO new_inbound_leads (lead_id, contact_id, first_message_id, source, status, received_at)
                VALUES (?, ?, ?, ?, 'new', ?);
            """, (lead_id, contact_id, msg_id, f"direct_{channel_clean}", rec_time))

            conn.commit()

        return {
            "lead_id": lead_id,
            "contact_id": contact_id,
            "identifier": clean_val,
            "channel": channel_clean,
            "first_message": first_message,
            "status": "new",
        }

    def suppress_contact(self, contact_id: str, reason: str, scope: str = "all") -> None:
        """Inserts an active suppression entry for a contact (e.g. STOP / opt-out)."""
        supp_id = f"supp_{uuid.uuid4().hex[:8]}"
        now_str = datetime.now(timezone.utc).isoformat()
        
        # Normalize to SQLite CHECK constraint: ('opt_out', 'not_interested', 'wrong_number', 'bot', 'manual_block', 'other')
        clean_reason = str(reason or "").lower().strip()
        if clean_reason in {"explicit_opt_out", "opt_out", "stop", "unsubscribe"}:
            clean_reason = "opt_out"
        elif clean_reason in {"negative_reply", "not_interested", "disinterest"}:
            clean_reason = "not_interested"
        elif clean_reason in {"wrong_number", "wrong_contact"}:
            clean_reason = "wrong_number"
        elif clean_reason not in {"opt_out", "not_interested", "wrong_number", "bot", "manual_block", "other"}:
            clean_reason = "other"

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO suppression_entries (suppression_id, contact_id, scope, reason, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?);
            """, (supp_id, contact_id, scope, clean_reason, now_str))
            # Also update conversation status
            conn.execute("UPDATE conversations SET status = 'suppressed' WHERE contact_id = ?;", (contact_id,))
            conn.commit()

    def invalidate_identifier(self, identifier: str) -> bool:
        """Fix 8: Marks a specific phone or email invalid when lead says 'wrong number'."""
        clean_val = normalize_email(identifier) if "@" in identifier else normalize_phone(identifier)
        if not clean_val:
            return False
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE contact_identifiers 
                SET status = 'invalid' 
                WHERE value_normalized = ? OR value_normalized LIKE ?;
            """, (clean_val, f"%{clean_val[-10:]}"))
            conn.commit()
            return True

    def is_duplicate_event(self, provider_event_id: Optional[str] = None, payload_hash: Optional[str] = None) -> bool:
        """Fix 2: DB-level deduplication check against inbound_events."""
        if not provider_event_id and not payload_hash:
            return False
        with self._get_connection() as conn:
            if provider_event_id:
                cur = conn.execute("SELECT 1 FROM inbound_events WHERE provider_event_id = ? LIMIT 1;", (provider_event_id,))
                if cur.fetchone():
                    return True
            if payload_hash:
                cur = conn.execute("SELECT 1 FROM inbound_events WHERE payload_hash = ? LIMIT 1;", (payload_hash,))
                if cur.fetchone():
                    return True
        return False

    def record_inbound_event(
        self,
        provider_event_id: Optional[str],
        channel: str,
        raw_payload: str,
        payload_hash: str,
        channel_account_id: Optional[str] = None,
    ) -> str:
        """Records raw incoming event into inbound_events table."""
        event_id = f"evt_{uuid.uuid4().hex[:10]}"
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO inbound_events (event_id, channel_account_id, provider_event_id, payload_hash, raw_payload, processed_status, received_at)
                VALUES (?, ?, ?, ?, ?, 'processed', ?);
            """, (event_id, channel_account_id or "chan_sms_01", provider_event_id, payload_hash, raw_payload, now_str))
            conn.commit()
        return event_id

    def save_message_draft(
        self,
        conversation_id: str,
        run_id: str,
        contact_id: str,
        channel: str,
        draft_body: str,
        draft_subject: Optional[str] = None,
        proposed_meeting_time: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> str:
        """Fix 15: Persists generated AI draft into message_drafts table pending human review."""
        draft_id = f"draft_{uuid.uuid4().hex[:8]}"
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO message_drafts (
                    draft_id, conversation_id, run_id, contact_id, channel,
                    draft_subject, draft_body, proposed_meeting_time, intent,
                    status, requires_human_approval, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', 1, ?, ?);
            """, (draft_id, conversation_id, run_id, contact_id, channel.lower(), draft_subject, draft_body, proposed_meeting_time, intent, now_str, now_str))
            conn.commit()
        return draft_id

    def get_approved_knowledge(self, service_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fix 13: Retrieves approved, response-safe knowledge articles."""
        with self._get_connection() as conn:
            if service_id:
                cur = conn.execute("""
                    SELECT article_id, service_id, title, content, source_reference
                    FROM knowledge_articles
                    WHERE access_level = 'response_safe'
                      AND approval_status = 'approved'
                      AND (service_id = ? OR service_id IS NULL);
                """, (service_id,))
            else:
                cur = conn.execute("""
                    SELECT article_id, service_id, title, content, source_reference
                    FROM knowledge_articles
                    WHERE access_level = 'response_safe'
                      AND approval_status = 'approved';
                """)
            return [dict(r) for r in cur.fetchall()]

    def save_memory_fact(
        self,
        contact_id: str,
        fact_key: str,
        fact_value: Any,
        source_message_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """Fix 12: Saves memory fact with provenance, superseding outdated facts."""
        mem_id = f"mem_{uuid.uuid4().hex[:8]}"
        now_str = datetime.now(timezone.utc).isoformat()
        val_str = json.dumps(fact_value) if isinstance(fact_value, (dict, list)) else str(fact_value)
        with self._get_connection() as conn:
            # Mark previous active fact as superseded
            conn.execute("""
                UPDATE memory_facts
                SET status = 'superseded', updated_at = ?
                WHERE contact_id = ? AND fact_key = ? AND status = 'active';
            """, (now_str, contact_id, fact_key))

            # Insert new active fact
            conn.execute("""
                INSERT INTO memory_facts (
                    memory_id, contact_id, conversation_id, source_message_id,
                    fact_key, fact_value, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?);
            """, (mem_id, contact_id, conversation_id, source_message_id, fact_key, val_str, now_str, now_str))
            conn.commit()
        return mem_id

    def get_active_memory_facts(self, contact_id: str) -> Dict[str, Any]:
        """Fix 10 & 11: Retrieves active facts isolated strictly by contact_id."""
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT fact_key, fact_value, source_message_id, updated_at
                FROM memory_facts
                WHERE contact_id = ? AND status = 'active'
                ORDER BY updated_at ASC;
            """, (contact_id,))
            facts = {}
            for row in cur.fetchall():
                key = row["fact_key"]
                val = row["fact_value"]
                try:
                    facts[key] = json.loads(val)
                except Exception:
                    facts[key] = val
            return facts

    def append_message(
        self,
        contact_id: str,
        channel: str,
        direction: str,
        sender: str,
        text: str,
        timestamp: Optional[str] = None,
        provider_message_id: Optional[str] = None,
    ) -> None:
        """Appends a turn to messages table under the active conversation."""
        clean_text = str(text or "").strip()
        if not clean_text:
            return

        now_str = timestamp or datetime.now(timezone.utc).isoformat()
        msg_id = f"msg_{uuid.uuid4().hex[:10]}"
        channel_clean = channel.lower()

        with self._get_connection() as conn:
            # Find active conversation
            cur = conn.execute("SELECT conversation_id, channel_account_id FROM conversations WHERE contact_id = ? LIMIT 1;", (contact_id,))
            conv = cur.fetchone()
            if not conv:
                # Create a conversation thread
                conv_id = f"conv_{uuid.uuid4().hex[:8]}"
                cur_chan = conn.execute("SELECT channel_account_id FROM channel_accounts WHERE channel = ? LIMIT 1;", (channel_clean,))
                chan_row = cur_chan.fetchone()
                chan_id = chan_row["channel_account_id"] if chan_row else "chan_sms_01"
                conn.execute("""
                    INSERT INTO conversations (conversation_id, contact_id, channel_account_id, status)
                    VALUES (?, ?, ?, 'active');
                """, (conv_id, contact_id, chan_id))
            else:
                conv_id = conv["conversation_id"]
                chan_id = conv["channel_account_id"]

            # Prevent duplicate insertion if identical to last message
            cur_last = conn.execute("SELECT body, direction FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1;", (conv_id,))
            last = cur_last.fetchone()
            if last and last["body"] == clean_text and last["direction"] == direction:
                return

            conn.execute("""
                INSERT INTO messages (message_id, conversation_id, channel_account_id, provider_message_id, direction, body, delivery_status, provider_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, 'received', ?);
            """, (msg_id, conv_id, chan_id, provider_message_id, direction, clean_text, now_str))

            # Update conversation last_message_at
            conn.execute("UPDATE conversations SET last_message_at = ?, version = version + 1 WHERE conversation_id = ?;", (now_str, conv_id))
            conn.commit()

    def get_conversation_messages(self, contact_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves chronological message history for a contact from the messages table."""
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT 
                    m.message_id,
                    m.direction,
                    m.body as text,
                    m.delivery_status,
                    m.created_at as timestamp,
                    ca.channel,
                    CASE WHEN m.direction = 'inbound' THEN 'lead' ELSE 'us' END as sender
                FROM messages m
                JOIN conversations c ON m.conversation_id = c.conversation_id
                JOIN channel_accounts ca ON m.channel_account_id = ca.channel_account_id
                WHERE c.contact_id = ?
                ORDER BY m.created_at ASC
                LIMIT ?;
            """, (contact_id, limit))
            return [dict(r) for r in cur.fetchall()]

    def get_new_inbound_leads(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetches all newly recorded leads from new_inbound_leads table."""
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT 
                    nl.lead_id,
                    nl.source,
                    nl.status,
                    nl.received_at,
                    c.name,
                    ci.value_normalized as identifier,
                    m.body as first_message
                FROM new_inbound_leads nl
                JOIN contacts c ON nl.contact_id = c.contact_id
                JOIN contact_identifiers ci ON c.contact_id = ci.contact_id
                JOIN messages m ON nl.first_message_id = m.message_id
                ORDER BY nl.received_at DESC
                LIMIT ?;
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]
