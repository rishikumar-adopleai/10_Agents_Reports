"""
Node 4: Enterprise Customer Memory & Relevant Conversation Context Manager.
File: backend/app/agents/lead_responder/memory_manager.py

Responsibilities:
1. Fix 10: Retrieves relevant memory (recent turns + verified facts) rather than unbounded raw dump.
2. Fix 11: Enforces strict customer memory isolation (isolated by contact_id).
3. Fix 12: Tracks memory sources and supports fact superseding (e.g., document volume = 500/day).
4. Produces structured context payload ready for Node 5 (LLM Drafter).
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.agents.lead_responder.sqlite_store import SQLiteContactStore

DB_PATH = Path(__file__).parent / "lead_responder.db"

# Extraction patterns for lead-provided facts
DOC_VOLUME_REGEX = re.compile(
    r"(\b\d[\d,]*\b)\s*(?:documents?|docs?|referrals?|claims?|files?|charts?|loans?|cases?)\s*(?:per|\/|a)\s*(?:day|month|week|year)",
    re.IGNORECASE,
)
SYSTEM_REGEX = re.compile(
    r"\b(epic|cerner|oracle cerner|athenahealth|athena|meditech|allscripts|salesforce|hubspot)\b",
    re.IGNORECASE,
)


class MemoryManager:
    """Manages scoped private memory, provenance tracking, and relevant conversation transcripts."""

    def __init__(self, store: Optional[SQLiteContactStore] = None):
        self.store = store or SQLiteContactStore()

    def load_memory_and_thread(
        self,
        customer_context: Dict[str, Any],
        current_inbound_text: str,
    ) -> Dict[str, Any]:
        """
        Loads recent messages from SQLite, extracts newly stated facts with provenance,
        retrieves active scoped customer memory, and formats a relevant transcript.
        """
        ctx = customer_context or {}
        contact_id = ctx.get("customer_id") or ""
        name = ctx.get("name") or "Prospect"
        company = ctx.get("company") or "Organization"
        role = ctx.get("role") or "Decision Maker"
        industry = ctx.get("industry") or "Enterprise"
        matched_service = ctx.get("matched_service") or "Enterprise AI Workflow Automation"
        identified_problem = ctx.get("identified_problem")
        outreach_context = ctx.get("outreach_context")
        phone = ctx.get("phone") or ""
        email = ctx.get("email") or ""
        channel = ctx.get("channel", "sms").lower()
        notes = ctx.get("notes") or ""
        has_demo = bool(ctx.get("has_demo", False))
        demo_sent = ctx.get("demo_sent") or {}
        demo_title = demo_sent.get("title") if demo_sent else None
        demo_url = demo_sent.get("url") if demo_sent else None

        # ----------------------------------------------------------------------
        # 1. Fact Extraction & Provenance Tracking (Fix 12)
        # ----------------------------------------------------------------------
        if contact_id and current_inbound_text:
            # Check for document/case volume
            vol_match = DOC_VOLUME_REGEX.search(current_inbound_text)
            if vol_match:
                self.store.save_memory_fact(
                    contact_id=contact_id,
                    fact_key="document_volume",
                    fact_value=vol_match.group(0),
                )

            # Check for existing system or EMR
            sys_match = SYSTEM_REGEX.search(current_inbound_text)
            if sys_match:
                self.store.save_memory_fact(
                    contact_id=contact_id,
                    fact_key="current_system",
                    fact_value=sys_match.group(0).title(),
                )

        # Retrieve all verified active facts isolated strictly for this customer (Fix 11)
        active_facts: Dict[str, Any] = {}
        if contact_id:
            active_facts = self.store.get_active_memory_facts(contact_id)

        # ----------------------------------------------------------------------
        # 2. Synthesize Scoped Contact Memory Facts
        # ----------------------------------------------------------------------
        resolved_tz = ctx.get("timezone") or self._infer_timezone(phone, notes)
        pain_point = identified_problem or self._extract_pain_point(notes, demo_title)

        memory_facts: Dict[str, Any] = {
            "contact_id": contact_id,
            "name": name,
            "company": company,
            "role": role,
            "industry": industry,
            "matched_service": matched_service,
            "identified_problem": identified_problem,
            "outreach_context": outreach_context,
            "channel": channel,
            "phone": phone,
            "email": email,
            "timezone": resolved_tz,
            "has_demo": has_demo,
            "demo_title": demo_title,
            "demo_url": demo_url,
            "pain_point": pain_point,
            "is_cold_inbound": bool(ctx.get("is_cold_inbound", False)),
            "active_facts": active_facts,
        }

        # Persist lead profile fact
        if contact_id:
            self.store.save_memory_fact(contact_id, "lead_profile", {
                "name": name,
                "company": company,
                "role": role,
                "industry": industry,
                "timezone": resolved_tz,
            })

        # ----------------------------------------------------------------------
        # 3. Retrieve Relevant Messages (Last 10 turns - Fix 10)
        # ----------------------------------------------------------------------
        raw_db_messages: List[Dict[str, Any]] = []
        if contact_id:
            raw_db_messages = self.store.get_conversation_messages(contact_id, limit=10)

        full_turns: List[Dict[str, str]] = []
        llm_messages: List[Dict[str, str]] = []

        for msg in raw_db_messages:
            direction = msg.get("direction", "")
            body = msg.get("text") or msg.get("body") or ""
            timestamp = msg.get("timestamp") or ""

            if direction == "outbound":
                role = "assistant"
                label = "Us (Outbound Outreach)"
            elif direction == "inbound":
                role = "user"
                label = f"Lead ({name})"
            else:
                role = "system"
                label = "System Event"

            full_turns.append({
                "direction": label,
                "role": role,
                "text": body,
                "timestamp": timestamp,
            })
            llm_messages.append({
                "role": role,
                "content": body,
            })

        # Ensure latest incoming message is present in turns
        if current_inbound_text and (not full_turns or full_turns[-1]["text"].strip() != current_inbound_text.strip()):
            full_turns.append({
                "direction": f"Lead ({name})",
                "role": "user",
                "text": current_inbound_text,
                "timestamp": ctx.get("received_at") or datetime.now(timezone.utc).isoformat(),
            })
            llm_messages.append({
                "role": "user",
                "content": current_inbound_text,
            })

        # ----------------------------------------------------------------------
        # 4. Format Clean Multi-Line Human-Readable Transcript
        # ----------------------------------------------------------------------
        lines = [
            "═" * 70,
            f"RELEVANT CONTEXT: {name} ({company}) - Industry: {industry}",
            f"Matched Service: {matched_service}",
            f"Timezone: {resolved_tz} | Outreach: {'WITH DEMO (' + str(demo_title) + ')' if has_demo else 'WITHOUT DEMO'}",
        ]
        if active_facts:
            lines.append("Verified Customer Facts (Active Memory):")
            for fk, fv in active_facts.items():
                if fk != "lead_profile":
                    lines.append(f"  * {fk}: {fv}")
        lines.append("═" * 70)

        for t in full_turns:
            lines.append(f"[{t['timestamp']}] {t['direction']}:")
            lines.append(f"  {t['text']}")
            lines.append("")

        formatted_transcript = "\n".join(lines).strip()

        return {
            "memory_facts": memory_facts,
            "conversation_history": full_turns,
            "messages_for_llm": llm_messages,
            "formatted_transcript": formatted_transcript,
        }

    @staticmethod
    def _infer_timezone(phone: str, notes: str) -> str:
        """Infers US timezone from explicit notes or phone area codes."""
        notes_lower = notes.lower()
        if re.search(r"\b(est|eastern)\b", notes_lower):
            return "America/New_York (EST)"
        if re.search(r"\b(cst|central|texas)\b", notes_lower):
            return "America/Chicago (CST)"
        if re.search(r"\b(pst|pacific)\b", notes_lower):
            return "America/Los_Angeles (PST)"

        clean_phone = phone.strip()
        if clean_phone.startswith("1512") or clean_phone.startswith("1214") or clean_phone.startswith("1713") or clean_phone.startswith("1832"):
            return "America/Chicago (CST)"
        if clean_phone.startswith("1415") or clean_phone.startswith("1650") or clean_phone.startswith("1408") or clean_phone.startswith("1206"):
            return "America/Los_Angeles (PST)"
        if clean_phone.startswith("1212") or clean_phone.startswith("1646") or clean_phone.startswith("1617") or clean_phone.startswith("1216"):
            return "America/New_York (EST)"

        return "America/Chicago (CST)"

    @staticmethod
    def _extract_pain_point(notes: str, demo_title: Optional[str]) -> str:
        notes_lower = notes.lower()
        if "intake backlog" in notes_lower or "clinic" in notes_lower:
            return "Referral fax intake volume, outpatient backlog & EMR integration"
        if "soc2" in notes_lower or "security" in notes_lower:
            return "Security compliance, SOC 2 certification & US data residency"
        if "underwriting" in notes_lower or "loan" in notes_lower:
            return "Commercial loan review turnaround & balance sheet extraction"
        if demo_title:
            return f"Workflow automation for {demo_title}"
        return "Manual document processing & operational efficiency"
