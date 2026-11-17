"""
Node 2: Customer Identity & Context Resolver (SQLite Powered).
File: backend/app/agents/lead_responder/customer_resolver.py

Responsibilities:
1. Accepts standardized output from Node 1 (inbound_event).
2. Looks up the contact in SQLite `contacts` table (by Phone or Email).
3. Pulls existing conversation history from the `messages` table.
4. If they are a completely new lead:
   - Inserts them into `new_inbound_leads` table.
   - Registers them in `contacts` with is_cold_inbound=1.
5. Emits enriched customer context dict + past conversation history for Node 3 & Node 4.
"""

from typing import Any, Dict, List, Optional
from backend.app.agents.lead_responder.sqlite_store import SQLiteContactStore


class CustomerResolver:
    """Resolves an incoming SMS or Email event against the SQLite database."""

    def __init__(self, store: Optional[Any] = None):
        self.store = store or SQLiteContactStore()

    def resolve_customer(self, inbound_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enriches Node 1's standardized inbound payload with contact identity,
        outreach type (with/without demo), timezone, past message history,
        and automatically handles new leads in the `new_inbound_leads` table.
        """
        channel = inbound_event.get("channel", "sms")
        sender_id = inbound_event.get("sender_id") or inbound_event.get("from_number") or ""
        recipient_id = inbound_event.get("recipient_id") or inbound_event.get("to_number") or ""
        reply_text = inbound_event.get("reply_text") or ""
        received_at = inbound_event.get("received_at")

        # 1. Check if contact already exists in `contacts` table
        existing_contact = None
        if hasattr(self.store, "find_by_identifier"):
            existing_contact = self.store.find_by_identifier(sender_id)

        is_new_lead = existing_contact is None
        past_messages: List[Dict[str, Any]] = []

        if not is_new_lead and existing_contact:
            # EXISTING CONTACT: Save inbound message once & fetch past conversation history (Fix 6)
            contact = existing_contact
            if reply_text and hasattr(self.store, "append_message"):
                self.store.append_message(
                    contact_id=contact["contact_id"],
                    channel=channel,
                    direction="inbound",
                    sender="lead",
                    text=reply_text,
                    timestamp=received_at,
                )
            if hasattr(self.store, "get_conversation_messages"):
                past_messages = self.store.get_conversation_messages(contact["contact_id"], limit=10)
        else:
            # COMPLETELY NEW LEAD: Record in `new_inbound_leads` table!
            if hasattr(self.store, "record_new_inbound_lead"):
                self.store.record_new_inbound_lead(
                    identifier=sender_id,
                    channel=channel,
                    sender_id=recipient_id,
                    first_message=reply_text,
                    received_at=received_at,
                )
                contact = self.store.find_by_identifier(sender_id) or {
                    "contact_id": f"con_inbound_{sender_id}",
                    "name": f"New Prospect ({sender_id})",
                    "company": "Direct Inbound Prospect",
                    "role": "Prospect",
                    "industry": None,
                    "matched_service": None,
                    "identified_problem": None,
                    "outreach_context": "Direct inbound inquiry",
                    "timezone": "CST",
                    "has_demo": 0,
                    "is_cold_inbound": 1,
                }
            else:
                contact = self.store.get_or_create_inbound_contact(sender_id, recipient_id)
            past_messages = []

        # 2. Extract Outreach Category (With Demo vs Without Demo)
        has_demo = bool(contact.get("has_demo", False))
        demo_title = contact.get("demo_title")
        demo_url = contact.get("demo_url")

        demo_summary = None
        has_viewed_demo = False
        if has_demo:
            has_viewed_demo = True
            demo_summary = {
                "title": demo_title,
                "url": demo_url,
                "has_clicked": True,
            }

        return {
            "customer_id": contact.get("contact_id"),
            "name": contact.get("name"),
            "company": contact.get("company"),
            "role": contact.get("role"),
            "industry": contact.get("industry"),
            "matched_service": contact.get("matched_service"),
            "identified_problem": contact.get("identified_problem"),
            "outreach_context": contact.get("outreach_context"),
            "timezone": contact.get("timezone", "CST"),
            "email": contact.get("email") or (sender_id if channel == "email" else ""),
            "phone": contact.get("phone") or (sender_id if channel == "sms" else ""),
            "channel": channel,
            "our_sender_id": recipient_id,
            "inbound_message": reply_text,
            "received_at": received_at,
            "subject": inbound_event.get("subject"),
            "thread_id": inbound_event.get("thread_id"),
            "has_demo": has_demo,
            "demo_sent": demo_summary,
            "has_viewed_demo": has_viewed_demo,
            "is_new_lead": is_new_lead,
            "is_cold_inbound": bool(contact.get("is_cold_inbound", False)),
            "is_suppressed": bool(contact.get("is_suppressed", False)),
            "suppression_reason": contact.get("suppression_reason"),
            "notes": contact.get("notes", ""),
            "conversation_history": past_messages,
        }
