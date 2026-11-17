"""
Live Inbound Webhook Trigger for 24/7 Lead Responder (Nodes 1, 2, and 3).
Connects:
- Node 1: Unified Ingest & Deduplication (SMS & Email)
- Node 2: SQLite Customer Resolver (With Demo vs Without Demo)
- Node 3: Safety & Stop Filter (with SQLite Suppression & Option 3 OOO)
- Plus: Direct POST /contacts endpoint to add any new contact from Postman!

Run in your terminal:
    python -m backend.app.agents.lead_responder.live_inbound_trigger
"""

import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from backend.app.agents.lead_responder.customer_resolver import CustomerResolver
from backend.app.agents.lead_responder.llm_drafter import LLMDrafter
from backend.app.agents.lead_responder.memory_manager import MemoryManager
from backend.app.agents.lead_responder.node_1_email_sms import node_1_receive_inbound
from backend.app.agents.lead_responder.safety_checker import SafetyChecker
from backend.app.agents.lead_responder.sqlite_store import SQLiteContactStore

PORT = 8765
OUR_SENDER_NUMBERS = ["14158201488", "14158201489"]
OUR_EMAIL_DOMAINS = ["adople.ai", "enterprise-ai.com"]


class InboundWebhookHandler(BaseHTTPRequestHandler):
    store = SQLiteContactStore()
    resolver = CustomerResolver(store=store)
    safety = SafetyChecker()
    memory = MemoryManager(store=store)
    drafter = LLMDrafter(store=store)

    def do_GET(self):
        """Health check endpoint for Postman or browser."""
        self._send_response(200, {
            "status": "online",
            "service": "24/7 Lead Responder (Nodes 1-3 Live)",
            "database": "SQLite (lead_responder.db)",
            "port": PORT,
            "endpoints": [
                "POST /contacts        -> Add/Register a new contact",
                "POST /webhook         -> Send inbound SMS / Email event",
            ],
            "supported_channels": ["sms", "email"]
        })

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length).decode("utf-8")

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            self._send_response(400, {"error": "Invalid JSON format in request body"})
            return

        # -------------------------------------------------------------
        # ROUTE 1: Direct Contact Creation Endpoint (/contacts)
        # -------------------------------------------------------------
        if self.path.startswith("/contacts") or self.path.startswith("/contact"):
            print("\n" + "═" * 75)
            print(">>> [POST /contacts] ADDING NEW CONTACT VIA POSTMAN!")
            print("═" * 75)

            contact_id = payload.get("contact_id") or f"con_{uuid.uuid4().hex[:8]}"
            name = payload.get("name", "New Lead")
            email = payload.get("email", "")
            phone = payload.get("phone", "")
            company = payload.get("company", "Independent Account")
            role = payload.get("role", "Prospect")
            timezone = payload.get("timezone", "CST")
            notes = payload.get("notes", "")
            has_demo = int(payload.get("has_demo", 0))
            demo_title = payload.get("demo_title")
            demo_url = payload.get("demo_url")

            industry = payload.get("industry", "Healthcare")

            saved = self.store.create_or_update_contact(
                name=name,
                company=company,
                email=email,
                phone=phone,
                role=role,
                industry=industry,
                timezone=timezone,
                notes=notes,
                has_demo=has_demo,
                demo_title=demo_title,
                demo_url=demo_url,
                initial_outreach=payload.get("initial_outreach"),
                contact_id=contact_id,
            )

            print(f"✅ Contact successfully saved into SQLite:")
            print(f"   ID:       {saved.get('contact_id')}")
            print(f"   Name:     {saved.get('name')}")
            print(f"   Email:    {saved.get('email')}")
            print(f"   Phone:    {saved.get('phone')}")
            print(f"   Has Demo: {bool(saved.get('has_demo'))} ({saved.get('demo_title')})")
            print("═" * 75 + "\n")

            self._send_response(201, {
                "status": "success",
                "message": "Contact created successfully in SQLite database",
                "contact": saved
            })
            return

        # -------------------------------------------------------------
        # ROUTE 2: Inbound Lead Message Webhook (/webhook) -> Runs LangGraph
        # -------------------------------------------------------------
        print("\n" + "═" * 75)
        print(">>> [PORT 8765] INBOUND WEBHOOK HIT FROM POSTMAN! (EXECUTING LANGGRAPH)")
        print("═" * 75)

        from backend.app.agents.lead_responder.graph import run_lead_responder

        final_state = run_lead_responder(payload)

        status = final_state.get("status", "processed")
        is_valid = final_state.get("is_valid_lead_msg", False)
        is_safe = final_state.get("is_safe_to_proceed", False)
        is_ooo = final_state.get("is_ooo", False)
        action = final_state.get("action", "")

        print(f"\n[LANGGRAPH EXECUTION COMPLETED]")
        print(f"  Channel:        {final_state.get('channel')}")
        print(f"  Ingest Status:  {status}")
        print(f"  Customer:       {final_state.get('name')} ({final_state.get('company')})")
        print(f"  Industry:       {final_state.get('industry')}")
        print(f"  Matched Service:{final_state.get('matched_service')}")
        print(f"  Action:         {action}")

        if not is_valid:
            print(f"  ⚠️ Filtered: {status}")
            print("═" * 75 + "\n")
            self._send_response(200, {
                "triggered": False,
                "step": "node_1_ingest",
                "status": status,
                "final_state": final_state,
            })
            return

        if not is_safe and not is_ooo:
            stop_reason = final_state.get("stop_reason")
            print(f"  🛑 Safety Stop: {stop_reason} (Action: {action})")
            print("═" * 75 + "\n")
            self._send_response(200, {
                "triggered": False,
                "step": "node_3_safety_stop",
                "action": action,
                "stop_reason": stop_reason,
                "customer": f"{final_state.get('name')} ({final_state.get('company')})",
                "final_state": final_state,
            })
            return

        if is_ooo:
            plan = final_state.get("ooo_plan", {})
            print(f"  🏖️ OOO Plan Triggered: Return date={plan.get('return_date')}")
            print("═" * 75 + "\n")
            self._send_response(200, {
                "triggered": True,
                "step": "node_3_ooo_plan",
                "status": "ooo_handled",
                "action": "halt_ooo",
                "ooo_plan": plan,
                "final_state": final_state,
            })
            return

        # Draft ready
        print(f"  Intent:         {final_state.get('intent')}")
        print(f"  Proposed Slot:  {final_state.get('proposed_meeting_time')}")
        print(f"  Draft ID:       {final_state.get('draft_id')} (Saved to message_drafts)")
        print(f"  Run ID:         {final_state.get('run_id')} (Saved to agent_runs)")
        print(f"  Draft Reply:\n\"{final_state.get('draft_reply')}\"")
        print("═" * 75 + "\n")

        self._send_response(200, {
            "triggered": True,
            "status": "ai_draft_ready_for_review",
            "step": "node_5_llm_draft_complete",
            "intent": final_state.get("intent"),
            "customer_request_summary": final_state.get("customer_request_summary"),
            "reasoning": final_state.get("reasoning"),
            "draft_channel": final_state.get("draft_channel"),
            "draft_subject": final_state.get("draft_subject"),
            "draft_reply": final_state.get("draft_reply"),
            "proposed_meeting_time": final_state.get("proposed_meeting_time"),
            "requires_human_approval": True,
            "draft_id": final_state.get("draft_id"),
            "run_id": final_state.get("run_id"),
            "model_used": final_state.get("model_used"),
            "customer": {
                "customer_id": final_state.get("customer_id"),
                "name": final_state.get("name"),
                "company": final_state.get("company"),
                "industry": final_state.get("industry"),
                "matched_service": final_state.get("matched_service"),
                "identified_problem": final_state.get("identified_problem"),
                "outreach_context": final_state.get("outreach_context"),
                "timezone": final_state.get("timezone"),
                "has_demo": final_state.get("has_demo"),
                "demo_sent": final_state.get("demo_sent"),
            },
            "memory_facts": final_state.get("memory_facts"),
        })

    def _send_response(self, code: int, body: Dict[str, Any]):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body, indent=2).encode("utf-8"))

    def log_message(self, format, *args):
        pass


def run_server(port: int = PORT):
    server = ThreadingHTTPServer(("0.0.0.0", port), InboundWebhookHandler)
    print("═" * 75)
    print(f"🟢 24/7 LEAD RESPONDER - SQLITE BACKED PIPELINE RUNNING ON PORT {port}")
    print(f"👉 POST /contacts  -> Add a new contact to SQLite")
    print(f"👉 POST /webhook   -> Inbound SMS or Email lead message")
    print("Press Ctrl+C to stop.")
    print("═" * 75)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    run_server()
