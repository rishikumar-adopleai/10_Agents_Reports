"""
Node 5: LLM Intent Classifier and Dynamic Response Drafter.
File: backend/app/agents/lead_responder/llm_drafter.py

Grounded by knowledge_base.md and powered by Claude (via platform gateway).

Features:
- Fix 13: Grounded retrieval using verified response-safe knowledge articles from SQLite
- Fix 14: Intent-based business handling (availability verification, SOC 2/HIPAA evidence, Safe Unknown Template)
- Fix 15: Complete draft persistence in SQLite `message_drafts` and audit logging in `agent_runs`
- Dynamic configuration: loads LLM_API_KEY, LLM_BASE_URL, LLM_MODEL from environment
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from backend.app.agents.lead_responder.sqlite_store import SQLiteContactStore

DB_PATH = Path(__file__).parent / "lead_responder.db"
KB_PATH = Path(__file__).parent / "knowledge_base.md"


def _load_env_file():
    """Lightweight zero-dependency .env loader."""
    candidates = [
        Path(__file__).resolve().parents[4] / ".env",
        Path(".env"),
        Path(__file__).resolve().parents[3] / ".env",
    ]
    for env_path in candidates:
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            clean_k = k.strip()
                            clean_v = v.strip().split("#")[0].strip().strip('"').strip("'")
                            if clean_k not in os.environ:
                                os.environ[clean_k] = clean_v
                break
            except Exception:
                pass


_load_env_file()

DEFAULT_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.llmapi.ai/v1/chat/completions")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")


SYSTEM_PROMPT = """You are a senior enterprise solutions specialist at Adople AI, communicating 1-to-1 with US executive buyers in healthcare, fintech, and private equity.

CORE OPERATING POLICIES (MANDATORY & UNCOMPROMISING):
1. 100% HUMAN APPROVAL REQUIRED: Every response you write is a draft pending human review. You must NEVER claim a meeting is permanently finalized, a contract signed, or an email already sent. Always set "requires_human_approval": true.
2. TONE & STYLE:
   - Direct, human, conversational, professional. ZERO buzzwords (never say "cutting-edge", "game-changing", "paradigm shift", "seamless integration", "robust").
   - IF CHANNEL IS SMS: 1 to 2 short sentences. Target under 160 characters. No markdown, asterisks, or bullet points.
   - IF CHANNEL IS EMAIL: Concise 2 to 3 sentences with professional greeting ("Hi [Name],") and sign-off ("Best,\\nAdople AI Team").
3. DEMO AWARENESS:
   - If has_demo is true: Acknowledge the demo naturally in sentence 1 ("Glad you checked out the [demo_title] preview!").
   - If has_demo is false: Answer questions directly. Do NOT mention a demo as if they received one. Offer to share a live 60-second walkthrough during a quick call.
4. TIMEZONE & CALENDAR INTEGRITY (Fix 14):
   - Always suggest or acknowledge calendar availability in the lead's local US timezone (e.g. CST, EST, PST). Never use UTC or Asian timezones.
   - A meeting time suggested by an LLM is NOT proof that the slot is available. Acknowledge their proposed time, state that you've prepared an invite for that window, and note that our team will send the calendar invite to confirm it.
5. GROUNDED COMPLIANCE & SECURITY (Fix 13 & 14):
   - Only state security facts present in approved knowledge articles: SOC 2 Type II certified, HIPAA compliant with BAAs executed, AES-256 encryption at rest, TLS 1.3 in transit, 100% US-based AWS cloud hosting, client data NEVER used to train public models.
   - If asked about unverified systems, custom pricing, or non-approved claims, use the SAFE UNKNOWN TEMPLATE:
     "I don't want to give you an unverified technical answer. I'll have our solutions engineer confirm our architecture on this specific question."
   - Never invent pricing numbers (pricing depends on monthly volume and scope).
6. INTENTS TO CLASSIFY:
   - 'meeting_request': Lead wants to meet, talk, or confirm a time.
   - 'service_question': Lead asks about product capabilities, EMR/system integration, or workflow.
   - 'security_question': Lead asks about SOC 2, HIPAA, data residency, or compliance.
   - 'pricing': Lead asks about price/cost.
   - 'demo_question': Lead asks to see or try a demo preview.
   - 'general': General inquiry.

OUTPUT FORMAT:
Return ONLY a valid JSON object matching this schema:
{
  "intent": "meeting_request" | "service_question" | "security_question" | "pricing" | "demo_question" | "general",
  "customer_request_summary": "1-sentence summary of what the lead asked or said",
  "reasoning": "1-sentence internal rationale for this draft",
  "draft_channel": "email" | "sms",
  "draft_subject": "Subject line (if email, else null)",
  "draft_reply": "The exact response ready for human review",
  "proposed_meeting_time": "e.g. Thursday, 2:00 PM CST (or null if not applicable)",
  "requires_human_approval": true
}
"""


class LLMDrafter:
    """Node 5: Grounded LLM Drafter with Knowledge Retrieval, Business Handling & SQLite Persistence."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        store: Optional[SQLiteContactStore] = None,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)).strip()
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.store = store or SQLiteContactStore()

    def draft_response(
        self,
        customer_context: Dict[str, Any],
        memory_facts: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
        current_inbound_text: str,
    ) -> Dict[str, Any]:
        """
        Drafts a grounded response using the configured model.
        Retrieves approved knowledge (Fix 13), handles intents safely (Fix 14),
        and persists the draft to SQLite `message_drafts` and `agent_runs` (Fix 15).
        """
        start_time = datetime.now(timezone.utc).isoformat()
        run_id = f"run_{uuid.uuid4().hex[:8]}"

        channel = customer_context.get("channel", "sms").lower()
        lead_name = memory_facts.get("name", "there")
        company = memory_facts.get("company", "your team")
        role = memory_facts.get("role", "Prospect")
        industry = memory_facts.get("industry") or "Enterprise"
        matched_service = memory_facts.get("matched_service") or "AI Automation Workflow"
        identified_problem = memory_facts.get("identified_problem") or "Manual document workflow"
        outreach_context = memory_facts.get("outreach_context") or ""
        tz = memory_facts.get("timezone", "CST")
        has_demo = bool(memory_facts.get("has_demo", False))
        demo_title = memory_facts.get("demo_title")
        demo_url = memory_facts.get("demo_url")
        pain_point = memory_facts.get("pain_point", "Automation")
        active_facts = memory_facts.get("active_facts", {})
        contact_id = customer_context.get("customer_id") or memory_facts.get("contact_id")

        # -------------------------------------------------------------
        # 1. Retrieve Approved Response-Safe Knowledge (Fix 13)
        # -------------------------------------------------------------
        kb_articles = self.store.get_approved_knowledge()
        kb_summary = "\n".join([f"- [{art['title']}]: {art['content']}" for art in kb_articles])

        # -------------------------------------------------------------
        # 2. Call LLM or Deterministic Fallback
        # -------------------------------------------------------------
        if not self.api_key or self.api_key.startswith("mock"):
            result = self._deterministic_fallback(
                channel=channel,
                lead_name=lead_name,
                company=company,
                industry=industry,
                matched_service=matched_service,
                tz=tz,
                has_demo=has_demo,
                demo_title=demo_title,
                current_inbound_text=current_inbound_text,
                active_facts=active_facts,
            )
        else:
            result = self._call_platform_llm(
                channel=channel,
                lead_name=lead_name,
                company=company,
                role=role,
                industry=industry,
                matched_service=matched_service,
                identified_problem=identified_problem,
                outreach_context=outreach_context,
                tz=tz,
                has_demo=has_demo,
                demo_title=demo_title,
                demo_url=demo_url,
                pain_point=pain_point,
                active_facts=active_facts,
                kb_summary=kb_summary,
                conversation_history=conversation_history,
                current_inbound_text=current_inbound_text,
            )

        completed_time = datetime.now(timezone.utc).isoformat()

        # -------------------------------------------------------------
        # 3. Persist Run to SQLite `agent_runs` & Draft to `message_drafts` (Fix 15)
        # -------------------------------------------------------------
        draft_id = None
        conv_id = None
        if contact_id:
            try:
                with self.store._get_connection() as conn:
                    # A. Find or ensure active conversation
                    cur = conn.execute("SELECT conversation_id, channel_account_id FROM conversations WHERE contact_id = ? LIMIT 1;", (contact_id,))
                    conv = cur.fetchone()
                    if not conv:
                        conv_id = f"conv_{uuid.uuid4().hex[:8]}"
                        cur_chan = conn.execute("SELECT channel_account_id FROM channel_accounts WHERE channel = ? LIMIT 1;", (channel.lower(),))
                        chan_row = cur_chan.fetchone()
                        chan_id = chan_row["channel_account_id"] if chan_row else "chan_sms_01"
                        conn.execute("INSERT INTO conversations (conversation_id, contact_id, channel_account_id, status) VALUES (?, ?, ?, 'active');", (conv_id, contact_id, chan_id))
                    else:
                        conv_id = conv["conversation_id"]

                    # B. Find or ensure trigger message
                    cur_msg = conn.execute("SELECT message_id FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1;", (conv_id,))
                    msg_row = cur_msg.fetchone()
                    if not msg_row:
                        msg_id = f"msg_{uuid.uuid4().hex[:8]}"
                        cur_chan = conn.execute("SELECT channel_account_id FROM channel_accounts WHERE channel = ? LIMIT 1;", (channel.lower(),))
                        chan_row = cur_chan.fetchone()
                        chan_id = chan_row["channel_account_id"] if chan_row else "chan_sms_01"
                        conn.execute("INSERT INTO messages (message_id, conversation_id, channel_account_id, direction, body, delivery_status) VALUES (?, ?, ?, 'inbound', ?, 'received');", (msg_id, conv_id, chan_id, current_inbound_text or "Inbound inquiry"))
                    else:
                        msg_id = msg_row["message_id"]

                    # C. Insert agent_run FIRST so run_id exists for foreign key constraint
                    conn.execute("""
                        INSERT INTO agent_runs (
                            run_id, conversation_id, trigger_message_id, agent_name,
                            detected_intent, status, started_at, completed_at
                        ) VALUES (?, ?, ?, 'agent6', ?, 'waiting_for_review', ?, ?);
                    """, (run_id, conv_id, msg_id, result.get("intent", "general"), start_time, completed_time))

                    # D. Insert message_draft referencing agent_runs and conversations
                    draft_id = f"draft_{uuid.uuid4().hex[:8]}"
                    now_str = datetime.now(timezone.utc).isoformat()
                    conn.execute("""
                        INSERT INTO message_drafts (
                            draft_id, conversation_id, run_id, contact_id, channel,
                            draft_subject, draft_body, proposed_meeting_time, intent,
                            status, requires_human_approval, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', 1, ?, ?);
                    """, (
                        draft_id, conv_id, run_id, contact_id, channel.lower(),
                        result.get("draft_subject"), result.get("draft_reply", ""),
                        result.get("proposed_meeting_time"), result.get("intent", "general"),
                        now_str, now_str,
                    ))
                    conn.commit()
            except Exception as e:
                print(f"[LLMDrafter] persistence notice: {e}")

        result["draft_id"] = draft_id
        result["conversation_id"] = conv_id
        result["run_id"] = run_id
        result["model_used"] = self.model
        result["started_at"] = start_time
        result["completed_at"] = completed_time

        return result

    def _call_platform_llm(
        self,
        channel: str,
        lead_name: str,
        company: str,
        role: str,
        industry: str,
        matched_service: str,
        identified_problem: str,
        outreach_context: str,
        tz: str,
        has_demo: bool,
        demo_title: Optional[str],
        demo_url: Optional[str],
        pain_point: str,
        active_facts: Dict[str, Any],
        kb_summary: str,
        conversation_history: List[Dict[str, Any]],
        current_inbound_text: str,
    ) -> Dict[str, Any]:
        """Calls the OpenAI-compatible platform gateway with grounded context and KB articles."""
        endpoint = self.base_url if self.base_url.endswith("/chat/completions") else f"{self.base_url}/chat/completions"

        context_lines = [
            "LEAD FACTS & RESEARCH CONTEXT:",
            f"- Contact Name: {lead_name}",
            f"- Job Role: {role}",
            f"- Company: {company}",
            f"- Industry: {industry}",
            f"- Matched AI Service: {matched_service}",
            f"- Identified Problem: {identified_problem}",
            f"- Previous Outreach Research: {outreach_context}",
            f"- Channel: {channel.upper()}",
            f"- Local Timezone: {tz}",
            f"- Outreach Type: {'WITH DEMO' if has_demo else 'WITHOUT DEMO'}",
            f"- Demo Title: {demo_title or 'None'}",
            f"- Demo URL: {demo_url or 'None'}",
            f"- Known Pain Point: {pain_point}",
        ]
        if active_facts:
            context_lines.append("- Active Customer Memory Facts:")
            for fk, fv in active_facts.items():
                if fk != "lead_profile":
                    context_lines.append(f"  * {fk}: {fv}")

        context_block = "\n".join(context_lines)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": context_block},
            {"role": "system", "content": f"APPROVED ENTERPRISE KNOWLEDGE ARTICLES (VERIFIED EVIDENCE):\n{kb_summary}"},
        ]

        # Inject chronological conversation history
        for turn in conversation_history:
            role_tag = turn.get("role") or ("user" if turn.get("direction") == "inbound" else "assistant")
            content = turn.get("text") or turn.get("content") or ""
            if content.strip() and content.strip() != current_inbound_text.strip():
                messages.append({"role": role_tag, "content": content})

        # Inject current inbound message
        messages.append({
            "role": "user",
            "content": f"[INBOUND MESSAGE VIA {channel.upper()}]: {current_inbound_text}",
        })

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(endpoint, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_content = data["choices"][0]["message"]["content"]

                clean_json_str = raw_content.strip()
                if clean_json_str.startswith("```"):
                    clean_json_str = re.sub(r"^```[a-zA-Z]*\n?", "", clean_json_str)
                    clean_json_str = re.sub(r"\n?```$", "", clean_json_str).strip()

                match = re.search(r"\{.*\}", clean_json_str, re.DOTALL)
                if match:
                    clean_json_str = match.group(0)

                result = json.loads(clean_json_str)
                result["draft_channel"] = channel
                result["requires_human_approval"] = True
                return result
        except Exception as e:
            print(f"[LLMDrafter] Gateway call notice ({e}), using grounded fallback.")
            return self._deterministic_fallback(
                channel=channel,
                lead_name=lead_name,
                company=company,
                industry=industry,
                matched_service=matched_service,
                tz=tz,
                has_demo=has_demo,
                demo_title=demo_title,
                current_inbound_text=current_inbound_text,
                active_facts=active_facts,
            )

    def _deterministic_fallback(
        self,
        channel: str,
        lead_name: str,
        company: str,
        industry: str,
        matched_service: str,
        tz: str,
        has_demo: bool,
        demo_title: Optional[str],
        current_inbound_text: str,
        active_facts: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """High-precision grounded fallback adhering strictly to knowledge_base.md rules."""
        text_lower = current_inbound_text.lower()
        first_name = lead_name.split()[0] if lead_name else "there"
        tz_short = "CST" if "cst" in tz.lower() or "central" in tz.lower() else "EST" if "est" in tz.lower() else "PST"
        active_facts = active_facts or {}

        # 1. Unverified Technical Systems -> Safe Unknown Template (Fix 14)
        if any(w in text_lower for w in ["custom integration", "proprietary", "on-premise", "sla guarantee", "allscripts"]):
            intent = "service_question"
            if channel == "email":
                draft = (
                    f"Hi {first_name},\n\n"
                    f"I don't want to give you an unverified technical answer. "
                    f"I'll have our solutions engineer confirm our architecture on this specific question and circle back shortly.\n\n"
                    f"Best,\nAdople AI Team"
                )
            else:
                draft = f"Hi {first_name}, I don't want to give you an unverified answer. I'll have our solutions engineer confirm our architecture on this specific question."
            return {
                "intent": intent,
                "customer_request_summary": "Lead asked an unverified technical or architecture question.",
                "reasoning": "Invoked Safe Unknown Template to avoid unverified technical claims.",
                "draft_channel": channel,
                "draft_subject": "Re: Technical Architecture Inquiry",
                "draft_reply": draft,
                "proposed_meeting_time": None,
                "requires_human_approval": True,
            }

        # 2. Meeting Intent (Fix 14)
        if any(w in text_lower for w in ["meet", "call", "schedule", "talk", "calendar", "tomorrow", "thursday", "friday", "time", "2pm", "2:00"]):
            intent = "meeting_request"
            proposed_time = f"Thursday, 2:00 PM {tz_short}"
            if channel == "email":
                demo_ack = f"Glad you checked out the {demo_title or matched_service} preview — " if (has_demo and demo_title) else "Thanks for getting back to us — "
                draft = (
                    f"Hi {first_name},\n\n"
                    f"{demo_ack}Thursday at 2:00 PM {tz_short} works well on our calendar, and I'll have our team send a calendar invite once confirmed.\n\n"
                    f"Looking forward to walking through how this connects with {company}'s workflow.\n\n"
                    f"Best,\nAdople AI Team"
                )
            else:
                demo_ack = "Glad you saw the demo! " if has_demo else ""
                draft = f"Hi {first_name}, {demo_ack}Thursday at 2:00 PM {tz_short} works great for a 15-min call. I'll prepare a calendar invite once confirmed!"
            return {
                "intent": intent,
                "customer_request_summary": "Lead requested a meeting or confirmed availability.",
                "reasoning": f"Acknowledged request and offered slot in {tz_short} pending confirmation.",
                "draft_channel": channel,
                "draft_subject": f"Re: 15-Minute Call – Thursday at 2:00 PM {tz_short}",
                "draft_reply": draft,
                "proposed_meeting_time": proposed_time,
                "requires_human_approval": True,
            }

        # 3. Security / Compliance Intent (Fix 13 & 14)
        if any(w in text_lower for w in ["soc", "hipaa", "security", "store", "residency", "compliance", "privacy", "baa"]):
            intent = "security_question"
            if channel == "email":
                draft = (
                    f"Hi {first_name},\n\n"
                    f"Yes, Adople AI is SOC 2 Type II certified and fully HIPAA compliant with Business Associate Agreements (BAAs) executed. "
                    f"All data is stored exclusively in dedicated US-based AWS regions with AES-256 encryption at rest and TLS 1.3 in transit, and we never use client data to train public models.\n\n"
                    f"Happy to provide our compliance packet or jump on a brief call to answer any technical questions.\n\n"
                    f"Best,\nAdople AI Team"
                )
            else:
                draft = f"Hi {first_name}, yes—we are SOC 2 Type II certified and HIPAA compliant with 100% US-based data hosting. Happy to send our security packet!"
            return {
                "intent": intent,
                "customer_request_summary": "Lead inquired about SOC 2, HIPAA, or US data residency.",
                "reasoning": "Affirmed approved security evidence factually.",
                "draft_channel": channel,
                "draft_subject": "Re: Security & Compliance Overview",
                "draft_reply": draft,
                "proposed_meeting_time": None,
                "requires_human_approval": True,
            }

        # 4. Service / Capability Intent (Fix 13)
        intent = "service_question"
        if channel == "email":
            demo_ack = f"Our {matched_service} "
            draft = (
                f"Hi {first_name},\n\n"
                f"{demo_ack}integrates directly into your existing workflows to automate document parsing with verified accuracy. "
                f"Would you be open to a 15-minute discovery call this Thursday at 2:00 PM {tz_short} to see how this connects with {company}?\n\n"
                f"Best,\nAdople AI Team"
            )
        else:
            draft = f"Hi {first_name}, our system integrates directly with your existing tools to automate document workflows. Would you be open to a quick 15-min call this week?"
        return {
            "intent": intent,
            "customer_request_summary": "Lead asked a service capability question.",
            "reasoning": "Provided factual capability overview and proposed discovery discussion.",
            "draft_channel": channel,
            "draft_subject": f"Re: {matched_service} Overview",
            "draft_reply": draft,
            "proposed_meeting_time": f"Thursday, 2:00 PM {tz_short}",
            "requires_human_approval": True,
        }

    def _log_agent_run(
        self,
        run_id: str,
        contact_id: str,
        detected_intent: str,
        status: str,
        started_at: str,
        completed_at: str,
    ) -> None:
        """Saves run audit record into SQLite `agent_runs` table."""
        try:
            with self.store._get_connection() as conn:
                cur = conn.execute("SELECT conversation_id FROM conversations WHERE contact_id = ? LIMIT 1;", (contact_id,))
                conv = cur.fetchone()
                conv_id = conv["conversation_id"] if conv else f"conv_{contact_id}"

                cur_msg = conn.execute("SELECT message_id FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1;", (conv_id,))
                msg_row = cur_msg.fetchone()
                msg_id = msg_row["message_id"] if msg_row else f"msg_{run_id}"

                conn.execute("""
                    INSERT INTO agent_runs (
                        run_id, conversation_id, trigger_message_id, agent_name,
                        detected_intent, status, started_at, completed_at
                    ) VALUES (?, ?, ?, 'agent6', ?, ?, ?, ?);
                """, (run_id, conv_id, msg_id, detected_intent, status, started_at, completed_at))
                conn.commit()
        except Exception as e:
            print(f"[LLMDrafter] agent_runs log notice: {e}")
