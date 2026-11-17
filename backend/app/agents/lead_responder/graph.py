"""
LangGraph Lead Responder Workflow (Enterprise Production Architecture).
File: backend/app/agents/lead_responder/graph.py

Unified 5-Node StateGraph connecting:
- Node 1: node_ingest (SipLink SMS & Email Ingestion, Authenticity, Deduplication, Quote Stripping)
- Node 2: node_customer_context (SQLite Identity, Industry, Matched Service, Previous Research Resolver)
- Node 3: node_safety_check (STOP/Opt-out, Wrong Number, Disinterest, Option 3 OOO Plan)
- Node 4: node_memory (Relevant Turns, Isolated Customer Facts & Provenance Tracking)
- Node 5: node_llm_draft (Grounded Drafter, Approved Knowledge, Safe Unknowns, message_drafts Persistence)

Run directly to test:
    python -m backend.app.agents.lead_responder.graph
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.app.agents.lead_responder.customer_resolver import CustomerResolver
from backend.app.agents.lead_responder.llm_drafter import LLMDrafter
from backend.app.agents.lead_responder.memory_manager import MemoryManager
from backend.app.agents.lead_responder.node_1_email_sms import node_1_receive_inbound
from backend.app.agents.lead_responder.safety_checker import SafetyChecker
from backend.app.agents.lead_responder.sqlite_store import SQLiteContactStore

# Shared Store Instance
store = SQLiteContactStore()
resolver = CustomerResolver(store=store)
safety = SafetyChecker()
memory = MemoryManager(store=store)
drafter = LLMDrafter(store=store)

OUR_SENDER_NUMBERS = ["14158201488", "14158201489"]
OUR_EMAIL_DOMAINS = ["adople.ai", "enterprise-ai.com"]


# ==============================================================================
# 1. UNIFIED LANGGRAPH STATE DEFINITION
# ==============================================================================

class LeadResponderState(TypedDict, total=False):
    """Unified state dictionary passed across all nodes and edges in LangGraph."""

    # Raw Ingest Inputs
    raw_payload: Dict[str, Any]
    our_sender_numbers: List[str]
    our_email_domains: List[str]

    # Node 1: Ingest Outputs
    channel: str                          # 'sms' or 'email'
    status: str                           # 'accepted', 'skipped_duplicate', etc.
    is_valid_lead_msg: bool
    sender_id: str                        # normalized phone or email
    sender_phone: Optional[str]
    sender_email: Optional[str]
    recipient_id: str
    reply_text: str                       # Cleaned message without quotes/signatures
    subject: Optional[str]
    thread_id: Optional[str]
    received_at: str

    # Node 2: Customer, Industry & Outreach Context
    customer_id: str
    name: str
    company: str
    role: str
    industry: Optional[str]               # Fix 4: e.g. Healthcare, Financial Services
    matched_service: Optional[str]        # Fix 4: e.g. AI Referral Intake & EMR Parser
    identified_problem: Optional[str]     # Fix 5: Prior Agent 4 research problem
    outreach_context: Optional[str]       # Fix 5: Prior outreach context
    timezone: str
    has_demo: bool                        # Type A (With Demo) vs Type B (Without Demo)
    demo_sent: Optional[Dict[str, Any]]
    has_viewed_demo: bool
    is_new_lead: bool                     # True if brand new -> added to new_inbound_leads
    is_cold_inbound: bool
    notes: str

    # Node 3: Safety & Compliance Outputs
    action: str                           # 'proceed_to_reply', 'halt_opt_out', 'halt_ooo', etc.
    is_safe_to_proceed: bool
    stop_reason: Optional[str]            # 'explicit_opt_out', 'not_interested', 'wrong_number', etc.
    is_ooo: bool
    ooo_plan: Optional[Dict[str, Any]]    # Option 3 Plan
    safety_detail: str

    # Node 4: Conversational Memory Outputs
    memory_facts: Dict[str, Any]
    conversation_history: List[Dict[str, Any]]
    messages_for_llm: List[Dict[str, Any]]
    formatted_transcript: str

    # Node 5: LLM Drafter & Approval Outputs
    intent: str                           # 'meeting_request', 'security_question', etc.
    customer_request_summary: str
    reasoning: str
    draft_channel: str
    draft_subject: Optional[str]
    draft_reply: str                      # Final grounded AI draft text
    proposed_meeting_time: Optional[str]
    requires_human_approval: bool         # Always True
    draft_id: Optional[str]               # Fix 15: Logged in message_drafts table
    run_id: str                           # Fix 15: Logged in agent_runs table
    model_used: str                       # Dynamically from config


# ==============================================================================
# 2. NODE DEFINITIONS (PURE STATE WORKERS)
# ==============================================================================

def node_ingest(state: LeadResponderState) -> Dict[str, Any]:
    """Node 1: Auto-detects SMS vs Email, checks authenticity, strips quotes, dedups."""
    raw = state.get("raw_payload", {})
    senders = state.get("our_sender_numbers") or OUR_SENDER_NUMBERS
    domains = state.get("our_email_domains") or OUR_EMAIL_DOMAINS

    ingest_out = node_1_receive_inbound(
        raw_payload=raw,
        our_sender_numbers=senders,
        our_email_domains=domains,
    )

    return {
        "channel": ingest_out.get("channel", "sms"),
        "status": ingest_out.get("status"),
        "is_valid_lead_msg": bool(ingest_out.get("is_valid_lead_msg", False)),
        "sender_id": ingest_out.get("sender_id", ""),
        "sender_phone": ingest_out.get("sender_phone"),
        "sender_email": ingest_out.get("sender_email"),
        "recipient_id": ingest_out.get("recipient_id", ""),
        "reply_text": ingest_out.get("reply_text", ""),
        "subject": ingest_out.get("subject"),
        "thread_id": ingest_out.get("thread_id"),
        "received_at": ingest_out.get("received_at", datetime.now(timezone.utc).isoformat()),
    }


def node_customer_context(state: LeadResponderState) -> Dict[str, Any]:
    """Node 2: Looks up contact in SQLite, loads industry, matched service, and research context."""
    ctx = resolver.resolve_customer(state)

    return {
        "customer_id": ctx.get("customer_id", ""),
        "name": ctx.get("name", "Prospect"),
        "company": ctx.get("company", "Independent Account"),
        "role": ctx.get("role", "Prospect"),
        "industry": ctx.get("industry"),
        "matched_service": ctx.get("matched_service"),
        "identified_problem": ctx.get("identified_problem"),
        "outreach_context": ctx.get("outreach_context"),
        "timezone": ctx.get("timezone", "CST"),
        "has_demo": bool(ctx.get("has_demo", False)),
        "demo_sent": ctx.get("demo_sent"),
        "has_viewed_demo": bool(ctx.get("has_viewed_demo", False)),
        "is_new_lead": bool(ctx.get("is_new_lead", False)),
        "is_cold_inbound": bool(ctx.get("is_cold_inbound", False)),
        "notes": ctx.get("notes", ""),
    }


def node_safety_check(state: LeadResponderState) -> Dict[str, Any]:
    """Node 3: Safety filter for STOP / opt-out, wrong number, disinterest, and Option 3 OOO."""
    ctx = dict(state)
    if not ctx.get("inbound_message"):
        ctx["inbound_message"] = state.get("reply_text", "")

    eval_res = safety.evaluate(ctx, contact_store=store)

    is_safe = bool(eval_res.get("is_safe_to_proceed", False))
    stop_reason = eval_res.get("stop_reason")
    action = eval_res.get("action", "proceed_to_reply")

    # Fix 7 & 8: Reason-specific handling
    if action == "halt_opt_out":
        if state.get("customer_id"):
            store.suppress_contact(state["customer_id"], "opt_out")
    elif action == "halt_not_interested":
        if state.get("customer_id"):
            store.suppress_contact(state["customer_id"], "not_interested")
    elif action == "halt_wrong_number":
        sender_id = state.get("sender_id") or state.get("sender_phone") or state.get("sender_email") or ""
        if sender_id:
            store.invalidate_identifier(sender_id)
    elif action == "halt_ooo":
        # Record OOO plan; do not suppress contact.
        pass

    return {
        "action": action,
        "is_safe_to_proceed": is_safe,
        "stop_reason": stop_reason,
        "is_ooo": bool(eval_res.get("is_ooo", False)),
        "ooo_plan": eval_res.get("ooo_plan"),
        "safety_detail": eval_res.get("detail", ""),
    }


def node_memory(state: LeadResponderState) -> Dict[str, Any]:
    """Node 4: Loads relevant conversation turns, retrieves isolated customer facts & tracks provenance."""
    mem_out = memory.load_memory_and_thread(
        customer_context=state,
        current_inbound_text=state.get("reply_text", ""),
    )

    return {
        "memory_facts": mem_out.get("memory_facts", {}),
        "conversation_history": mem_out.get("conversation_history", []),
        "messages_for_llm": mem_out.get("messages_for_llm", []),
        "formatted_transcript": mem_out.get("formatted_transcript", ""),
    }


def node_llm_draft(state: LeadResponderState) -> Dict[str, Any]:
    """Node 5: Invokes LLM Drafter with knowledge retrieval & persists to message_drafts and agent_runs."""
    draft_out = drafter.draft_response(
        customer_context=state,
        memory_facts=state.get("memory_facts", {}),
        conversation_history=state.get("conversation_history", []),
        current_inbound_text=state.get("reply_text", ""),
    )

    return {
        "intent": draft_out.get("intent", "general"),
        "customer_request_summary": draft_out.get("customer_request_summary", ""),
        "reasoning": draft_out.get("reasoning", ""),
        "draft_channel": draft_out.get("draft_channel", state.get("channel", "sms")),
        "draft_subject": draft_out.get("draft_subject"),
        "draft_reply": draft_out.get("draft_reply", ""),
        "proposed_meeting_time": draft_out.get("proposed_meeting_time"),
        "requires_human_approval": True,
        "draft_id": draft_out.get("draft_id"),
        "run_id": draft_out.get("run_id", ""),
        "model_used": draft_out.get("model_used", drafter.model),
    }


# ==============================================================================
# 3. CONDITIONAL ROUTING EDGES
# ==============================================================================

def route_after_ingest(state: LeadResponderState) -> str:
    """If noise, echo, duplicate, or invalid payload -> Stop. Else -> Context."""
    if not state.get("is_valid_lead_msg", False):
        return END
    return "node_customer_context"


def route_after_safety(state: LeadResponderState) -> str:
    """If opt-out STOP, disinterest, wrong number, or OOO detected -> Halt. Else -> Load memory and draft."""
    if not state.get("is_safe_to_proceed", False):
        return END
    if state.get("is_ooo", False):
        return END
    return "node_memory"


# ==============================================================================
# 4. COMPILE STATEGRAPH WORKFLOW
# ==============================================================================

def build_lead_responder_graph():
    """Builds and compiles the unified 5-Node LangGraph workflow."""
    workflow = StateGraph(LeadResponderState)

    # Add Nodes
    workflow.add_node("node_ingest", node_ingest)
    workflow.add_node("node_customer_context", node_customer_context)
    workflow.add_node("node_safety_check", node_safety_check)
    workflow.add_node("node_memory", node_memory)
    workflow.add_node("node_llm_draft", node_llm_draft)

    # Add Edges
    workflow.add_edge(START, "node_ingest")

    # Conditional: Ingest -> Context OR END
    workflow.add_conditional_edges(
        "node_ingest",
        route_after_ingest,
        {
            "node_customer_context": "node_customer_context",
            END: END,
        },
    )

    workflow.add_edge("node_customer_context", "node_safety_check")

    # Conditional: Safety -> Memory OR END (if STOP or OOO)
    workflow.add_conditional_edges(
        "node_safety_check",
        route_after_safety,
        {
            "node_memory": "node_memory",
            END: END,
        },
    )

    workflow.add_edge("node_memory", "node_llm_draft")
    workflow.add_edge("node_llm_draft", END)

    return workflow.compile()


# Compiled Singleton Application
agent_graph = build_lead_responder_graph()


def run_lead_responder(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute Agent 6 inbound lead processing through draft creation."""
    initial_state: LeadResponderState = {
        "raw_payload": raw_payload,
        "our_sender_numbers": OUR_SENDER_NUMBERS,
        "our_email_domains": OUR_EMAIL_DOMAINS,
    }
    return agent_graph.invoke(initial_state)


# ==============================================================================
# 5. STANDALONE VERIFICATION RUNNER
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "═" * 75)
    print("🚀 TESTING UNIFIED LANGGRAPH LEAD RESPONDER AGENT (AGENT 6)")
    print("═" * 75)

    test_payload = {
        "from": "sarah.jenkins@metrohealth.org",
        "to": "sales@adople.ai",
        "subject": "Re: AI Patient Intake Demo",
        "body_plain": "Hi team, we reviewed the demo. Can we schedule a 15-minute call this Thursday at 2pm CST?",
    }

    print("\nInput Event: Inbound email from Dr. Sarah Jenkins (Metro Health Clinic)")
    final_state = run_lead_responder(test_payload)

    print("\n[LANGGRAPH FINAL OUTPUT STATE]")
    print(f"  Channel:        {final_state.get('channel')}")
    print(f"  Customer:       {final_state.get('name')} ({final_state.get('company')})")
    print(f"  Industry:       {final_state.get('industry')}")
    print(f"  Matched Service:{final_state.get('matched_service')}")
    print(f"  Outreach Type:  {'WITH DEMO' if final_state.get('has_demo') else 'WITHOUT DEMO'}")
    print(f"  Timezone:       {final_state.get('timezone')}")
    print(f"  Intent:         {final_state.get('intent')}")
    print(f"  Meeting Slot:   {final_state.get('proposed_meeting_time')}")
    print(f"  Approval Req:   {final_state.get('requires_human_approval')}")
    print(f"  Draft ID:       {final_state.get('draft_id')} (Logged in SQLite message_drafts table)")
    print(f"  Run ID:         {final_state.get('run_id')} (Logged in SQLite agent_runs table)")
    print(f"  Model:          {final_state.get('model_used')}")
    print("\n[DRAFT REPLY READY FOR HUMAN REVIEW]:")
    print(f"\"{final_state.get('draft_reply')}\"")
    print("═" * 75 + "\n")
